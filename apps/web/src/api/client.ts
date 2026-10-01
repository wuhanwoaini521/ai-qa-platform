import {
  ApplyRepairPayload,
  AIFailureDiagnosisResponse,
  AIStatusResponse,
  AIProviderSettings,
  AIProviderSettingsUpdate,
  AIProviderConnectionResult,
  AITraceEvent,
  AIUsageSummary,
  Breakpoint,
  DebugSessionBootstrap,
  AutomationBinding,
  AutomationBindingCreate,
  BranchInfo,
  CollectedTest,
  DecisionConnectionResult,
  DecisionRequest,
  DecisionResult,
  DashboardStats,
  FailureRecord,
  FailureAnalysisRun,
  FailureRecurrenceItem,
  FileNode,
  FlakyTestItem,
  GenerateAutomationResponse,
  GitBranchCreateRequest,
  GitChangedFile,
  GitCommitInfo,
  GitCommitRequest,
  GitDiffResult,
  GitPushResult,
  IntegrationAuditEntry,
  JiraBugDraft,
  JiraBugDraftRequest,
  JiraCreateBugRequest,
  JiraCreateBugResponse,
  JiraImportRequest,
  JevSettings,
  JevSettingsUpdate,
  JiraIssue,
  LocatorRepairProposal,
  LocatorSemanticReviewResponse,
  PRChecksSummary,
  PRDiagnosisRequest,
  PRDiagnosisResponse,
  Project,
  ProjectCreate,
  PRSummarySuggestionRequest,
  PRSummarySuggestionResponse,
  PullRequestCreateRequest,
  PullRequestInfo,
  QAChatRequest,
  QAChatResponse,
  Requirement,
  RequirementAnalysisDTO,
  RequirementCreate,
  RunnerHealthStatus,
  RunnerProfile,
  RunnerProfileCreate,
  RunnerProfileUpdate,
  TestCase,
  TestCaseCreate,
  TestCaseGenerationItem,
  TestDesign,
  TestDesignCreate,
  TestDesignSuggestion,
  TestHistoryResponse,
  TestRailCase,
  TestRailPublishPreview,
  TestRailPublishRequest,
  TestRailPublishResponse,
  TestRun,
  TestRunCreate,
  ImpactAnalysisRequest,
  ImpactAnalysisResult,
  QualityCoverageSummary,
  QualityRiskMatrix,
  Release,
  ReleaseCreate,
  ReleaseGateReport,
  ReleaseUpdate,
  User,
  UserCreate,
  UserUpdate,
  Team,
  TeamCreate,
  TeamMember,
  TeamUpdate,
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreatedResponse,
  LoginResponse,
  SecurityAuditLogEntry,
  ClusterStatusSummary,
  ExecutionJob,
  Worker,
  WorkerCreate,
  WorkspaceValidationResult,
  AgentTask,
  AgentTaskEvent,
  AgentTaskType,
  Workspace,
  RecorderStep,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
const TOKEN_STORAGE_KEY = 'ai-qa.auth-token';

let authToken: string | null = (() => {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
})();

let unauthorizedHandler: (() => void) | null = null;

/** Stores the bearer token used by every subsequent request. Pass `null` to sign out. */
export function setAuthToken(token: string | null): void {
  authToken = token;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    /* storage unavailable: the token stays in memory for this session only */
  }
}

type StreamKind = 'run' | 'task' | 'recorder' | 'debug';

export class EventStreamError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'EventStreamError';
  }

  get retryable(): boolean {
    return this.status < 400 || this.status >= 500 || this.status === 408 || this.status === 429;
  }
}

async function createStreamTicket(kind: StreamKind, resourceId: string): Promise<string> {
  const response = await request<{ stream_ticket: string }>(
    '/auth/stream-ticket',
    { method: 'POST', body: JSON.stringify({ kind, resource_id: resourceId }) },
  );
  return response.stream_ticket;
}

function streamUrl(path: string, afterId?: string): string {
  const url = new URL(`${BASE_URL}/api${path}`, window.location.origin);
  if (afterId) url.searchParams.set('after', afterId);
  return url.toString();
}

function openEventStream(
  path: string,
  kind: StreamKind,
  resourceId: string,
  onEvent: (event: MessageEvent<string>) => void,
  onError?: (error: Event | Error) => void,
  reconnectFromEventId = false,
): () => void {
  let stopped = false;
  let controller: AbortController | null = null;
  let reconnectTimer: number | null = null;
  let reconnectDelay = 500;
  let lastEventId = '';

  const scheduleReconnect = () => {
    if (stopped || reconnectTimer !== null) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      void connect();
    }, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 5000);
  };

  const connect = async () => {
    try {
      const ticket = await createStreamTicket(kind, resourceId);
      if (stopped) return;
      const abortController = new AbortController();
      controller = abortController;
      const headers: Record<string, string> = { Accept: 'text/event-stream', Authorization: `Bearer ${ticket}` };
      if (reconnectFromEventId && lastEventId) headers['Last-Event-ID'] = lastEventId;
      const response = await fetch(streamUrl(path, reconnectFromEventId ? lastEventId : undefined), {
        headers,
        signal: abortController.signal,
      });
      if (!response.ok) {
        if (response.status === 401) {
          setAuthToken(null);
          unauthorizedHandler?.();
        }
        throw new EventStreamError(`Stream request failed (${response.status}).`, response.status);
      }
      if (!response.body) throw new Error('Stream response body is unavailable.');
      reconnectDelay = 500;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      let dataLines: string[] = [];
      let eventName = '';
      let eventId = '';
      const dispatch = () => {
        if (!dataLines.length) {
          eventName = '';
          return;
        }
        if (eventId && !eventId.includes('\0')) lastEventId = eventId;
        onEvent(new MessageEvent<string>(eventName || 'message', {
          data: dataLines.join('\n'),
          lastEventId,
        }));
        dataLines = [];
        eventName = '';
      };
      const consumeFrame = (frame: string) => {
        for (const line of frame.split(/\r?\n/)) {
          if (!line || line.startsWith(':')) continue;
          const separator = line.indexOf(':');
          const field = separator < 0 ? line : line.slice(0, separator);
          const value = separator < 0 ? '' : line.slice(separator + 1).replace(/^ /, '');
          if (field === 'data') dataLines.push(value);
          else if (field === 'event') eventName = value;
          else if (field === 'id') eventId = value;
        }
        dispatch();
      };

      try {
        while (!stopped && !abortController.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          pending += decoder.decode(value, { stream: true });
          let boundary: number;
          while ((boundary = pending.search(/\r?\n\r?\n/)) >= 0) {
            const separator = pending.match(/\r?\n\r?\n/)?.[0] ?? '\n\n';
            consumeFrame(pending.slice(0, boundary));
            pending = pending.slice(boundary + separator.length);
          }
        }
        pending += decoder.decode();
        if (pending.trim()) consumeFrame(pending);
      } finally {
        reader.releaseLock();
      }
      if (controller === abortController) controller = null;
      if (!stopped) scheduleReconnect();
    } catch (error) {
      if (controller?.signal.aborted || stopped) return;
      controller = null;
      const originalError = error instanceof Error ? error : new Error(String(error));
      const apiStatus = originalError.message.match(/API Error \[(\d{3})\]/)?.[1];
      const streamError = apiStatus
        ? new EventStreamError(originalError.message, Number(apiStatus))
        : originalError;
      if (streamError instanceof EventStreamError && !streamError.retryable) {
        stopped = true;
        onError?.(streamError);
        return;
      }
      onError?.(streamError);
      scheduleReconnect();
    }
  };

  void connect();
  return () => {
    stopped = true;
    controller?.abort();
    controller = null;
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  };
}

/** Registers the handler invoked when the API rejects a request with 401. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/** True when a bearer token is present; used by the app shell to decide between login and routes. */
export function hasAuthToken(): boolean {
  return authToken !== null;
}

export async function getRecorderSocketUrl(sessionId: string): Promise<string> {
  const base = BASE_URL || window.location.origin;
  const url = new URL(`/api/recorder/sessions/${encodeURIComponent(sessionId)}/stream`, base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export async function getDebugSocketUrl(sessionId: string): Promise<string> {
  const base = BASE_URL || window.location.origin;
  const url = new URL(`/api/debug/sessions/${encodeURIComponent(sessionId)}/stream`, base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}/api${endpoint}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    setAuthToken(null);
    if (unauthorizedHandler) {
      unauthorizedHandler();
    }
  }

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error [${response.status}]: ${errorBody || response.statusText}`);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return response.json();
}

async function streamAITraceRequest(
  path: string,
  data: unknown,
  onEvent: (event: AITraceEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const response = await fetch(`${BASE_URL}/api${path}`, {
    method: 'POST',
    headers,
    body: data === undefined ? undefined : JSON.stringify(data),
    signal,
  });
  if (response.status === 401) {
    setAuthToken(null);
    unauthorizedHandler?.();
  }
  if (!response.ok) {
    throw new Error(`API Error [${response.status}]: ${(await response.text()) || response.statusText}`);
  }
  if (!response.body) throw new Error('Streaming response body is unavailable.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  const dispatch = (frame: string) => {
    let eventName = '';
    const dataLines: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
    }
    if (!dataLines.length) return;
    let event: AITraceEvent;
    try {
      event = JSON.parse(dataLines.join('\n')) as AITraceEvent;
    } catch {
      throw new Error(`Invalid AI stream event: ${eventName || 'unknown'}`);
    }
    if (!event.type && eventName) event.type = eventName;
    onEvent(event);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = pending.search(/\r?\n\r?\n/)) >= 0) {
        const separator = pending.match(/\r?\n\r?\n/)?.[0] ?? '\n\n';
        dispatch(pending.slice(0, boundary));
        pending = pending.slice(boundary + separator.length);
      }
    }
    pending += decoder.decode();
    if (pending.trim()) dispatch(pending);
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export const api = {
  createStreamTicket,
  streamQAAssistant: (data: QAChatRequest, onEvent: (event: AITraceEvent) => void, signal: AbortSignal) =>
    streamAITraceRequest('/qa-assistant/chat/stream', data, onEvent, signal),
  streamFailureDiagnosis: (id: string, onEvent: (event: AITraceEvent) => void, signal: AbortSignal) =>
    streamAITraceRequest(`/failures/${encodeURIComponent(id)}/diagnose-ai/stream`, undefined, onEvent, signal),
  streamFailureWorkflow: (id: string, onEvent: (event: AITraceEvent) => void, signal: AbortSignal) =>
    streamAITraceRequest(`/failures/${encodeURIComponent(id)}/analyze/stream`, undefined, onEvent, signal),
  getFailureAnalyses: (id: string) => request<FailureAnalysisRun[]>(`/failures/${encodeURIComponent(id)}/analyses`),
  linkFailureVerification: (id: string, analysisId: string, runId: string) => request(
    `/failures/${encodeURIComponent(id)}/analyses/${encodeURIComponent(analysisId)}/verification?run_id=${encodeURIComponent(runId)}`,
    { method: 'POST' },
  ),
  getWorkspaces: (projectId: string) => request<Workspace[]>(`/workspaces?project_id=${encodeURIComponent(projectId)}`),
  getTasks: (projectId?: string) => request<AgentTask[]>(`/tasks${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  getTask: (taskId: string) => request<AgentTask>(`/tasks/${encodeURIComponent(taskId)}`),
  createTask: (data: { type: AgentTaskType; goal: string; project_id?: string; workspace_id?: string; inputs?: Record<string, unknown> }) =>
    request<AgentTask>('/tasks', { method: 'POST', body: JSON.stringify(data) }),
  decideTaskApproval: (taskId: string, approved: boolean, comment = '') =>
    request<AgentTask>(`/tasks/${encodeURIComponent(taskId)}/approval`, { method: 'POST', body: JSON.stringify({ approved, comment }) }),
  cancelTask: (taskId: string) => request<AgentTask>(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }),
  replanTask: (taskId: string, instructions: string) =>
    request<AgentTask>(`/tasks/${encodeURIComponent(taskId)}/replan?instructions=${encodeURIComponent(instructions)}`, { method: 'POST' }),
  streamTaskEvents: (taskId: string, onEvent: (event: AgentTaskEvent) => void, onError?: (error: Event | Error) => void) => {
    let closeStream: () => void = () => {};
    closeStream = openEventStream(
      `/tasks/${encodeURIComponent(taskId)}/events`,
      'task',
      taskId,
      (event) => {
        try {
          const parsed = JSON.parse(event.data) as AgentTaskEvent;
          onEvent(parsed);
          if (['task.completed', 'task.failed', 'task.blocked', 'task.cancelled'].includes(parsed.type)) closeStream();
        } catch (error) {
          console.error('Failed to parse task event', error);
        }
      },
      onError,
      true,
    );
    return () => closeStream();
  },
    createRecorderSession: (projectId: string, startUrl: string, recoveredSteps: RecorderStep[] = []) =>
      request<{ id: string; project_id: string; state: string; url: string; requested_url: string; navigation_error: string | null }>('/recorder/sessions', {
      method: 'POST', body: JSON.stringify({ project_id: projectId, start_url: startUrl, recovered_steps: recoveredSteps }),
    }),
    getRecorderSession: (sessionId: string) =>
      request<{ id: string; project_id: string; state: string; url: string; requested_url: string; navigation_error: string | null; steps: RecorderStep[] }>(`/recorder/sessions/${encodeURIComponent(sessionId)}`),
  generateRecorderCode: (sessionId: string, payload: { case_name: string; file_path: string; test_name: string; steps: RecorderStep[] }) =>
    request<{ code: string; project_id: string }>(`/recorder/sessions/${encodeURIComponent(sessionId)}/generate`, {
      method: 'POST', body: JSON.stringify(payload),
    }),
  closeRecorderSession: (sessionId: string) =>
    request<{ closed: boolean }>(`/recorder/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  // Dashboard
  getDashboardStats: () => request<DashboardStats>('/dashboard/stats'),

  // Projects
  getProjects: () => request<Project[]>('/projects'),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (data: ProjectCreate) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateProject: (id: string, data: Partial<Project>) =>
    request<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Requirements
  getRequirements: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : '';
    return request<Requirement[]>(`/requirements${query}`);
  },
  getRequirement: (id: string) => request<Requirement>(`/requirements/${id}`),
  createRequirement: (data: RequirementCreate) =>
    request<Requirement>('/requirements', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateRequirement: (id: string, data: Partial<Requirement>) =>
    request<Requirement>(`/requirements/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Test Designs
  getTestDesigns: (requirementId: string) =>
    request<TestDesign[]>(`/test-designs?requirement_id=${requirementId}`),
  createTestDesign: (data: TestDesignCreate) =>
    request<TestDesign>('/test-designs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Test Cases
  getTestCases: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : '';
    return request<TestCase[]>(`/test-cases${query}`);
  },
  getTestCase: (id: string) => request<TestCase>(`/test-cases/${id}`),
  createTestCase: (data: TestCaseCreate) =>
    request<TestCase>('/test-cases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateTestCase: (id: string, data: Partial<TestCase>) =>
    request<TestCase>(`/test-cases/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getAutomationBinding: (testCaseId: string) =>
    request<AutomationBinding | null>(`/test-cases/${testCaseId}/binding`),
  saveAutomationBinding: (testCaseId: string, data: AutomationBindingCreate) =>
    request<AutomationBinding>(`/test-cases/${testCaseId}/binding`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  generateAutomation: (testCaseId: string, groundKnowledge = true) =>
    request<GenerateAutomationResponse>(
      `/test-cases/${testCaseId}/generate-automation?ground_knowledge=${groundKnowledge}`,
      { method: 'POST' }
    ),

  // Automation Workspace & Studio
  getBreakpoints: (workspaceId: string) =>
    request<Breakpoint[]>(`/workspaces/${encodeURIComponent(workspaceId)}/breakpoints`),
  upsertBreakpoint: (workspaceId: string, input: Pick<Breakpoint, 'file_path' | 'line_number' | 'enabled' | 'source'>) =>
    request<Breakpoint>(`/workspaces/${encodeURIComponent(workspaceId)}/breakpoints`, {
      method: 'PUT', body: JSON.stringify(input),
    }),
  deleteBreakpoint: (workspaceId: string, breakpointId: string) =>
    request<void>(`/workspaces/${encodeURIComponent(workspaceId)}/breakpoints/${encodeURIComponent(breakpointId)}`, {
      method: 'DELETE',
    }),
  createDebugSession: (workspaceId: string, nodeid: string) =>
    request<DebugSessionBootstrap>('/debug/sessions', {
      method: 'POST', body: JSON.stringify({ workspace_id: workspaceId, nodeid }),
    }),
  closeDebugSession: (sessionId: string) =>
    request<{ closed: boolean }>(`/debug/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  getWorkspaceFiles: (workspaceId: string) =>
    request<FileNode[]>(`/workspaces/${workspaceId}/files`),
  readWorkspaceFile: (workspaceId: string, path: string) =>
    request<{ path: string; content: string }>(
      `/workspaces/${workspaceId}/file?path=${encodeURIComponent(path)}`
    ),
  writeWorkspaceFile: (workspaceId: string, path: string, content: string) =>
    request<{ status: string; path: string }>(`/workspaces/${workspaceId}/file`, {
      method: 'PUT',
      body: JSON.stringify({ path, content }),
    }),
  createWorkspaceFile: (workspaceId: string, path: string, content = '') =>
    request<{ status: string; path: string }>(`/workspaces/${workspaceId}/files/create`, {
      method: 'POST',
      body: JSON.stringify({ path, is_directory: false, content }),
    }),
  createWorkspaceDirectory: (workspaceId: string, path: string) =>
    request<{ status: string; path: string }>(`/workspaces/${workspaceId}/files/create`, {
      method: 'POST',
      body: JSON.stringify({ path, is_directory: true }),
    }),
  renameWorkspaceFile: (workspaceId: string, oldPath: string, newPath: string) =>
    request<{ status: string; old_path: string; new_path: string }>(
      `/workspaces/${workspaceId}/files/rename`,
      {
        method: 'PATCH',
        body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
      }
    ),
  deleteWorkspaceFile: (workspaceId: string, path: string) =>
    request<{ status: string; path: string }>(
      `/workspaces/${workspaceId}/files/delete?path=${encodeURIComponent(path)}`,
      { method: 'DELETE' }
    ),
  getWorkspaceDiff: (workspaceId: string) =>
    request<GitDiffResult>(`/workspaces/${workspaceId}/diff`),
  commitWorkspace: (workspaceId: string, message: string, author?: string) =>
    request<{ status: string; commit_hash: string }>(`/workspaces/${workspaceId}/commit`, {
      method: 'POST',
      body: JSON.stringify({ message, author: author || 'AI QA Platform <qa@platform.local>' }),
    }),
  validateWorkspace: async (workspaceId: string) => {
    const report = await request<{
      valid: boolean;
      issues: Array<{
        file: string;
        line: number;
        column: number;
        severity: 'ERROR' | 'WARNING' | 'INFO';
        code?: string | null;
        source: string;
        message: string;
      }>;
    }>(`/workspaces/${workspaceId}/validate`, { method: 'POST' });
    const issues = report.issues.map((issue) => ({
      file: issue.file,
      line: issue.line,
      column: issue.column,
      message: issue.message,
      severity: issue.severity.toLowerCase() as 'error' | 'warning' | 'info',
      rule_id: issue.code || issue.source,
    }));
    return {
      is_valid: report.valid,
      error_count: issues.filter((issue) => issue.severity === 'error').length,
      warning_count: issues.filter((issue) => issue.severity === 'warning').length,
      issues,
    } satisfies WorkspaceValidationResult;
  },
  collectWorkspaceTests: async (workspaceId: string) => {
    const report = await request<{
      tests: Array<{
        nodeid: string;
        file: string;
        test_name: string;
        line: number | null;
        markers: string[];
      }>;
    }>(`/workspaces/${workspaceId}/collect`, { method: 'POST' });
    return report.tests.map((test): CollectedTest => ({
      nodeid: test.nodeid,
      name: test.test_name,
      path: test.file,
      line: test.line ?? 0,
      markers: test.markers,
      docstring: '',
    }));
  },
  bootstrapWorkspace: (workspaceId: string) =>
    request<{ status: string; workspace_id: string }>(`/workspaces/${workspaceId}/bootstrap`, {
      method: 'POST',
    }),

  // Test Execution Runs
  getTestRuns: (projectId?: string, limit = 50) => {
    const query = projectId ? `?project_id=${projectId}&limit=${limit}` : `?limit=${limit}`;
    return request<TestRun[]>(`/runs${query}`);
  },
  getTestRun: (id: string) => request<TestRun>(`/runs/${id}`),
  createTestRun: (data: TestRunCreate) =>
    request<TestRun>('/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  cancelTestRun: (id: string) =>
    request<TestRun>(`/runs/${id}/cancel`, {
      method: 'POST',
    }),

  // Runners Platform (Gate 7)
  getRunners: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : '';
    return request<RunnerProfile[]>(`/runners${query}`);
  },
  getRunnerProfiles: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : '';
    return request<RunnerProfile[]>(`/runners${query}`);
  },
  getRunner: (id: string) => request<RunnerProfile>(`/runners/${id}`),
  createRunner: (data: RunnerProfileCreate) =>
    request<RunnerProfile>('/runners', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  createRunnerProfile: (data: RunnerProfileCreate) =>
    request<RunnerProfile>('/runners', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateRunner: (id: string, data: RunnerProfileUpdate) =>
    request<RunnerProfile>(`/runners/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteRunner: (id: string) =>
    request<{ status: string; id: string }>(`/runners/${id}`, { method: 'DELETE' }),
  checkRunnerHealth: (id: string) => request<RunnerHealthStatus>(`/runners/${id}/health`),
  getRunnerHealth: (id: string) => request<RunnerHealthStatus>(`/runners/${id}/health`),
  getExternalArtifacts: async (runId: string) => {
    const run = await request<TestRun>(`/runs/${runId}`);
    return run.external_artifacts || [];
  },

  downloadArtifact: async (artifactId: string): Promise<Blob> => {
    const response = await fetch(`${BASE_URL}/api/artifacts/${artifactId}/download`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!response.ok) {
      throw new Error(`Artifact download failed [${response.status}]`);
    }
    return response.blob();
  },

  // Failure Intelligence & Locator Healing (Phase 5 & 6)
  getFailures: (projectId?: string, limit = 50) => {
    const query = projectId ? `?project_id=${projectId}&limit=${limit}` : `?limit=${limit}`;
    return request<FailureRecord[]>(`/failures${query}`);
  },
  getFailure: (id: string) => request<FailureRecord>(`/failures/${id}`),
  diagnoseFailure: (id: string) =>
    request<FailureRecord>(`/failures/${id}/diagnose`, { method: 'POST' }),
  diagnoseFailureAI: (id: string) =>
    request<AIFailureDiagnosisResponse>(`/failures/${id}/diagnose-ai`, { method: 'POST' }),
  generateRepairProposal: (id: string) =>
    request<LocatorRepairProposal>(`/failures/${id}/repair-proposal`, { method: 'POST' }),
  reviewSemanticRepair: (id: string, candidateLocator?: string) => {
    const q = candidateLocator ? `?candidate_locator=${encodeURIComponent(candidateLocator)}` : '';
    return request<LocatorSemanticReviewResponse>(`/failures/${id}/semantic-review${q}`, { method: 'POST' });
  },
  getSemanticLocatorReview: (id: string, _oldLocator?: string, candidateLocator?: string) => {
    const q = candidateLocator ? `?candidate_locator=${encodeURIComponent(candidateLocator)}` : '';
    return request<LocatorSemanticReviewResponse>(`/failures/${id}/semantic-review${q}`, { method: 'POST' });
  },
  getFailureRecurrence: (id: string) =>
    request<FailureRecurrenceItem[]>(`/failures/${id}/recurrence`),
  applyRepair: (id: string, data: ApplyRepairPayload, workspaceId: string) =>
    request<{ status: string; file_path: string }>(
      `/failures/${id}/apply-repair?workspace_id=${encodeURIComponent(workspaceId)}`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),

  // Flaky Intelligence & History (Phase 6)
  getFlakyTests: (projectId?: string, minScore = 0.0, classification?: string) => {
    let query = `?min_score=${minScore}`;
    if (projectId) query += `&project_id=${projectId}`;
    if (classification) query += `&classification=${classification}`;
    return request<FlakyTestItem[]>(`/flaky${query}`);
  },
  getTestHistory: (nodeid: string, projectId: string, limit = 20) =>
    request<TestHistoryResponse>(
      `/flaky/history?nodeid=${encodeURIComponent(nodeid)}&project_id=${projectId}&limit=${limit}`
    ),

  // Production AI Services (Phase 5)
  getAIStatus: () => request<AIStatusResponse>('/ai/status'),
  getAIUsage: (limit = 50) => request<AIUsageSummary>(`/ai/usage?limit=${limit}`),
  getAIProviderSettings: () => request<AIProviderSettings>('/ai/settings'),
  saveAIProviderSettings: (data: AIProviderSettingsUpdate) =>
    request<AIProviderSettings>('/ai/settings', { method: 'PUT', body: JSON.stringify(data) }),
  testAIProviderConnection: (data: AIProviderSettingsUpdate) =>
    request<AIProviderConnectionResult>('/ai/test-connection', { method: 'POST', body: JSON.stringify(data) }),
  getJevSettings: () => request<JevSettings>('/decision/settings'),
  saveJevSettings: (payload: JevSettingsUpdate) =>
    request<JevSettings>('/decision/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  testJevConnection: (payload: JevSettingsUpdate) =>
    request<DecisionConnectionResult>('/decision/test-connection', { method: 'POST', body: JSON.stringify(payload) }),
  chooseDecision: (payload: DecisionRequest) =>
    request<DecisionResult>('/decision/choose', { method: 'POST', body: JSON.stringify(payload) }),
  analyzeRequirement: (requirementId: string) =>
    request<RequirementAnalysisDTO>(`/ai/requirements/${requirementId}/analyze`, { method: 'POST' }),
  generateTestDesigns: (requirementId: string) =>
    request<TestDesignSuggestion[]>(`/ai/requirements/${requirementId}/generate-designs`, { method: 'POST' }),
  generateTestCases: (testDesignId: string) =>
    request<TestCaseGenerationItem[]>(`/ai/test-designs/${testDesignId}/generate-cases`, { method: 'POST' }),

  // QA Assistant Sidecar
  askQAAssistant: (data: QAChatRequest) =>
    request<QAChatResponse>('/qa-assistant/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Git & Source Control Workflow (Phase 8)
  getGitStatus: (workspaceId: string) =>
    request<GitChangedFile[]>(`/workspaces/${workspaceId}/git/status`),
  getGitBranches: (workspaceId: string) =>
    request<BranchInfo[]>(`/workspaces/${workspaceId}/git/branches`),
  getCurrentBranch: (workspaceId: string) =>
    request<string>(`/workspaces/${workspaceId}/git/current-branch`),
  createBranch: (workspaceId: string, data: GitBranchCreateRequest) =>
    request<string>(`/workspaces/${workspaceId}/git/branch`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  switchBranch: (workspaceId: string, data: GitBranchCreateRequest) =>
    request<string>(`/workspaces/${workspaceId}/git/switch-branch`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  commitGitChanges: (workspaceId: string, data: GitCommitRequest) =>
    request<string>(`/workspaces/${workspaceId}/git/commit`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  pushGitBranch: (workspaceId: string, branch?: string, remote = 'origin') =>
    request<GitPushResult>(
      `/workspaces/${workspaceId}/git/push?remote=${encodeURIComponent(remote)}${branch ? `&branch=${encodeURIComponent(branch)}` : ''}`,
      {
        method: 'POST',
      }
    ),
  getGitLog: (workspaceId: string, limit = 15) =>
    request<GitCommitInfo[]>(`/workspaces/${workspaceId}/git/log?limit=${limit}`),

  // Pull Request & GitHub Checks (Phase 8)
  suggestPRSummary: (workspaceId: string, data: PRSummarySuggestionRequest) =>
    request<PRSummarySuggestionResponse>(`/workspaces/${workspaceId}/pr/suggest-summary`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  createPullRequest: (workspaceId: string, data: PullRequestCreateRequest) =>
    request<PullRequestInfo>(`/workspaces/${workspaceId}/pr/create`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getPRChecks: (workspaceId: string, prNumber: number) =>
    request<PRChecksSummary>(`/workspaces/${workspaceId}/pr/${prNumber}/checks`),
  diagnosePRFailure: (workspaceId: string, data: PRDiagnosisRequest) =>
    request<PRDiagnosisResponse>(`/workspaces/${workspaceId}/pr/diagnose`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Jira Integration (Phase 9)
  searchJiraIssues: (query = '', limit = 20) =>
    request<JiraIssue[]>(`/jira/issues?query=${encodeURIComponent(query)}&limit=${limit}`),
  getJiraIssue: (key: string) => request<JiraIssue>(`/jira/issues/${encodeURIComponent(key)}`),
  importJiraIssues: (data: JiraImportRequest) =>
    request<Requirement[]>('/jira/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  generateJiraBugDraft: (data: JiraBugDraftRequest) =>
    request<JiraBugDraft>('/jira/bug-draft', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  createJiraBug: (data: JiraCreateBugRequest) =>
    request<JiraCreateBugResponse>('/jira/create-bug', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // TestRail Integration (Phase 9)
  getTestRailCases: (suiteId = 'S101', limit = 50) =>
    request<TestRailCase[]>(`/testrail/cases?suite_id=${encodeURIComponent(suiteId)}&limit=${limit}`),
  getTestRailCase: (caseId: string) =>
    request<TestRailCase>(`/testrail/cases/${encodeURIComponent(caseId)}`),
  previewTestRailPublish: (runId: string, suiteId = 'S101') =>
    request<TestRailPublishPreview>(
      `/testrail/runs/${encodeURIComponent(runId)}/preview?suite_id=${encodeURIComponent(suiteId)}`
    ),
  publishTestRailResults: (data: TestRailPublishRequest) =>
    request<TestRailPublishResponse>('/testrail/publish', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Integration Audit (Phase 9)
  getIntegrationAudits: (system?: string, limit = 50) => {
    const query = system ? `?system=${encodeURIComponent(system)}&limit=${limit}` : `?limit=${limit}`;
    return request<IntegrationAuditEntry[]>(`/audit/integrations${query}`);
  },

  // Quality Intelligence & Coverage (Phase 10)
  getQualityCoverage: (projectId: string) =>
    request<QualityCoverageSummary>(`/quality/coverage?project_id=${encodeURIComponent(projectId)}`),
  getQualityRiskMatrix: (projectId: string) =>
    request<QualityRiskMatrix>(`/quality/risk-matrix?project_id=${encodeURIComponent(projectId)}`),
  analyzeImpact: (projectId: string, data: ImpactAnalysisRequest) =>
    request<ImpactAnalysisResult>('/quality/impact-analysis', {
      method: 'POST',
      body: JSON.stringify({ ...data, project_id: projectId }),
    }),

  // Releases & Release Gate (Phase 10)
  getReleases: (projectId: string) =>
    request<Release[]>(`/releases?project_id=${encodeURIComponent(projectId)}`),
  getRelease: (releaseId: string) =>
    request<Release>(`/releases/${encodeURIComponent(releaseId)}`),
  createRelease: (data: ReleaseCreate) =>
    request<Release>('/releases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateRelease: (releaseId: string, data: ReleaseUpdate) =>
    request<Release>(`/releases/${encodeURIComponent(releaseId)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteRelease: (releaseId: string) =>
    request<{ success: boolean }>(`/releases/${encodeURIComponent(releaseId)}`, {
      method: 'DELETE',
    }),
  evaluateReleaseGate: (releaseId: string) =>
    request<ReleaseGateReport>(`/releases/${encodeURIComponent(releaseId)}/gate-evaluate`, {
      method: 'POST',
    }),

  // Identity, RBAC & Enterprise Security (Phase 11)
  login: (email: string, password: string) =>
    request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  getCurrentUserProfile: () => request<LoginResponse>('/auth/me'),
  getApiKeys: () => request<ApiKey[]>('/auth/api-keys'),
  createApiKey: (data: ApiKeyCreate) =>
    request<ApiKeyCreatedResponse>('/auth/api-keys', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteApiKey: (keyId: string) =>
    request<{ success: boolean }>(`/auth/api-keys/${encodeURIComponent(keyId)}`, {
      method: 'DELETE',
    }),

  // User Management (Phase 11)
  getUsers: (limit = 100) => request<User[]>(`/users?limit=${limit}`),
  getUser: (userId: string) => request<User>(`/users/${encodeURIComponent(userId)}`),
  createUser: (data: UserCreate) =>
    request<User>('/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateUser: (userId: string, data: UserUpdate) =>
    request<User>(`/users/${encodeURIComponent(userId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteUser: (userId: string) =>
    request<{ success: boolean }>(`/users/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
    }),

  // Team Management (Phase 11)
  getTeams: (limit = 100) => request<Team[]>(`/teams?limit=${limit}`),
  getTeam: (teamId: string) => request<Team>(`/teams/${encodeURIComponent(teamId)}`),
  createTeam: (data: TeamCreate) =>
    request<Team>('/teams', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateTeam: (teamId: string, data: TeamUpdate) =>
    request<Team>(`/teams/${encodeURIComponent(teamId)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteTeam: (teamId: string) =>
    request<{ success: boolean }>(`/teams/${encodeURIComponent(teamId)}`, {
      method: 'DELETE',
    }),
  addTeamMember: (teamId: string, userId: string, role = 'MEMBER') =>
    request<TeamMember>(`/teams/${encodeURIComponent(teamId)}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role }),
    }),
  removeTeamMember: (teamId: string, userId: string) =>
    request<{ success: boolean }>(
      `/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`,
      {
        method: 'DELETE',
      }
    ),

  // Security Audit (Phase 11)
  getSecurityAudits: (actorId?: string, action?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (actorId) params.append('actor_id', actorId);
    if (action) params.append('action', action);
    params.append('limit', String(limit));
    return request<SecurityAuditLogEntry[]>(`/audit/security?${params.toString()}`);
  },

  // Distributed Execution & Workers (Phase 12)
  getWorkers: () => request<Worker[]>('/workers'),
  getClusterStatus: () => request<ClusterStatusSummary>('/workers/cluster-status'),
  registerWorker: (data: WorkerCreate) =>
    request<Worker>('/workers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteWorker: (workerId: string) =>
    request<{ success: boolean }>(`/workers/${encodeURIComponent(workerId)}`, {
      method: 'DELETE',
    }),
  getJobs: (runId?: string, projectId?: string, status?: string, limit = 100) => {
    const params = new URLSearchParams();
    if (runId) params.append('run_id', runId);
    if (projectId) params.append('project_id', projectId);
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    return request<ExecutionJob[]>(`/jobs?${params.toString()}`);
  },
  cancelJob: (jobId: string) =>
    request<ExecutionJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    }),

  // SSE Event Stream for Live Test Runs
  streamRunEvents: (
    runId: string,
    onEvent: (event: any) => void,
    onError?: (err: any) => void
  ): (() => void) => {
    let closeStream: () => void = () => {};
    closeStream = openEventStream(
      `/runs/${encodeURIComponent(runId)}/events`,
      'run',
      runId,
      (event) => {
        try {
          const parsed = JSON.parse(event.data);
          onEvent(parsed);
          if (['RUN_FINISHED', 'RUN_ERROR', 'RUN_CANCELLED'].includes(parsed.type)) closeStream();
        } catch (error) {
          console.error('Failed to parse SSE event data', error);
        }
      },
      onError,
    );
    return () => closeStream();
  },
};
