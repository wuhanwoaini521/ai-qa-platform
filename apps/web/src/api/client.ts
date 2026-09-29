import {
  ApplyRepairPayload,
  AIFailureDiagnosisResponse,
  AIStatusResponse,
  AIUsageSummary,
  AutomationBinding,
  AutomationBindingCreate,
  BranchInfo,
  CollectedTest,
  DashboardStats,
  FailureRecord,
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

/** Appends the session token for the routes whose client cannot send an Authorization header. */
function withAccessToken(path: string): string {
  if (!authToken) {
    return path;
  }
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}access_token=${encodeURIComponent(authToken)}`;
}

/** Registers the handler invoked when the API rejects a request with 401. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/** True when a bearer token is present; used by the app shell to decide between login and routes. */
export function hasAuthToken(): boolean {
  return authToken !== null;
}

export function getRecorderSocketUrl(sessionId: string): string {
  const base = BASE_URL || window.location.origin;
  const url = new URL(`/api/recorder/sessions/${encodeURIComponent(sessionId)}/stream`, base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (authToken) url.searchParams.set('access_token', authToken);
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

export const api = {
  createRecorderSession: (projectId: string, startUrl: string, recoveredSteps: RecorderStep[] = []) =>
    request<{ id: string; project_id: string; state: string; url: string }>('/recorder/sessions', {
      method: 'POST', body: JSON.stringify({ project_id: projectId, start_url: startUrl, recovered_steps: recoveredSteps }),
    }),
  getRecorderSession: (sessionId: string) =>
    request<{ id: string; project_id: string; state: string; url: string; steps: RecorderStep[] }>(`/recorder/sessions/${encodeURIComponent(sessionId)}`),
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
  validateWorkspace: (workspaceId: string) =>
    request<WorkspaceValidationResult>(`/workspaces/${workspaceId}/validate`),
  collectWorkspaceTests: (workspaceId: string) =>
    request<CollectedTest[]>(`/workspaces/${workspaceId}/collect`),
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
    const url = `${BASE_URL}/api${withAccessToken(`/runs/${runId}/events`)}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        onEvent(parsed);
      } catch (e) {
        console.error('Failed to parse SSE event data', e);
      }
    };

    eventSource.onerror = (err) => {
      if (onError) onError(err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  },
};
