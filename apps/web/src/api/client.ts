import {
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
  TestRun,
  TestRunCreate,
  WorkspaceValidationResult,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}/api${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error [${response.status}]: ${errorBody || response.statusText}`);
  }

  return response.json();
}

export const api = {
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
    request<{ status: string; path: string }>(`/workspaces/${workspaceId}/file`, {
      method: 'POST',
      body: JSON.stringify({ path, content }),
    }),
  createWorkspaceDirectory: (workspaceId: string, path: string) =>
    request<{ status: string; path: string }>(`/workspaces/${workspaceId}/directory`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  renameWorkspaceFile: (workspaceId: string, oldPath: string, newPath: string) =>
    request<{ status: string; old_path: string; new_path: string }>(
      `/workspaces/${workspaceId}/rename`,
      {
        method: 'POST',
        body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
      }
    ),
  deleteWorkspaceFile: (workspaceId: string, path: string) =>
    request<{ status: string; path: string }>(
      `/workspaces/${workspaceId}/file?path=${encodeURIComponent(path)}`,
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
  applyRepair: (id: string, data: any, workspaceId?: string) =>
    request<{ status: string; file_path: string }>(
      `/failures/${id}/apply-repair${workspaceId ? `?workspace_id=${workspaceId}` : ''}`,
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

  // SSE Event Stream for Live Test Runs
  streamRunEvents: (
    runId: string,
    onEvent: (event: any) => void,
    onError?: (err: any) => void
  ): (() => void) => {
    const url = `${BASE_URL}/api/runs/${runId}/events`;
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
