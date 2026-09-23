import {
  DashboardStats,
  FileNode,
  GitDiffResult,
  Project,
  ProjectCreate,
  Requirement,
  RequirementCreate,
  TestCase,
  TestCaseCreate,
  TestDesign,
  TestDesignCreate,
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
  getWorkspaceDiff: (workspaceId: string) =>
    request<GitDiffResult>(`/workspaces/${workspaceId}/diff`),
  bootstrapWorkspace: (workspaceId: string) =>
    request<{ status: string; workspace_id: string }>(`/workspaces/${workspaceId}/bootstrap`, {
      method: 'POST',
    }),
};
