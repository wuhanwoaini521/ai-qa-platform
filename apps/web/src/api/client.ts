import {
  ApplyRepairRequest,
  AutomationBinding,
  AutomationBindingCreate,
  CollectedTest,
  DashboardStats,
  FailureRecord,
  FileNode,
  GenerateAutomationResponse,
  GitDiffResult,
  LocatorRepairProposal,
  Project,
  ProjectCreate,
  QAChatRequest,
  QAChatResponse,
  Requirement,
  RequirementCreate,
  TestCase,
  TestCaseCreate,
  TestDesign,
  TestDesignCreate,
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

  // Failure Intelligence & Locator Healing
  getFailures: (projectId?: string, limit = 50) => {
    const query = projectId ? `?project_id=${projectId}&limit=${limit}` : `?limit=${limit}`;
    return request<FailureRecord[]>(`/failures${query}`);
  },
  getFailure: (id: string) => request<FailureRecord>(`/failures/${id}`),
  diagnoseFailure: (id: string) =>
    request<{
      failure_id: string;
      category: string;
      diagnosis: string;
      suggested_action: string;
      confidence: number;
    }>(`/failures/${id}/diagnose`, { method: 'POST' }),
  generateRepairProposal: (id: string) =>
    request<LocatorRepairProposal>(`/failures/${id}/repair-proposal`, { method: 'POST' }),
  applyRepair: (id: string, data: ApplyRepairRequest) =>
    request<{ status: string; failure_id: string; target_file: string }>(
      `/failures/${id}/apply-repair`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),

  // QA Assistant Sidecar
  askQAAssistant: (data: QAChatRequest) =>
    request<QAChatResponse>('/qa-assistant/chat', {
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
