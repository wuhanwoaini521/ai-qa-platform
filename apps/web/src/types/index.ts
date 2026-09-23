export type FrameworkType = 'playwright_python' | 'pytest_api' | 'custom';

export type RequirementStatus = 'DRAFT' | 'READY' | 'ARCHIVED';

export type TestDesignCategory = 'FUNCTIONAL' | 'BOUNDARY' | 'NEGATIVE' | 'ANALYTICS' | 'API' | 'UI';

export type TestCasePriority = 'P0' | 'P1' | 'P2' | 'P3';

export type AutomationStatus = 'MANUAL' | 'DRAFT' | 'AUTOMATED';

export type WorkspaceStatus = 'ACTIVE' | 'INITIALIZING' | 'ARCHIVED' | 'ERROR';

export interface Project {
  id: string;
  name: string;
  description: string;
  repository_url: string | null;
  default_branch: string;
  framework_type: FrameworkType;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  repository_url?: string | null;
  default_branch?: string;
  framework_type?: FrameworkType;
  bootstrap_workspace?: boolean;
}

export interface Requirement {
  id: string;
  project_id: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  status: RequirementStatus;
  created_at: string;
  updated_at: string;
}

export interface RequirementCreate {
  project_id: string;
  title: string;
  description?: string;
  acceptance_criteria?: string;
  status?: RequirementStatus;
}

export interface TestDesign {
  id: string;
  requirement_id: string;
  title: string;
  category: TestDesignCategory;
  description: string;
  risk: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TestDesignCreate {
  requirement_id: string;
  title: string;
  category?: TestDesignCategory;
  description?: string;
  risk?: string;
  status?: string;
}

export interface TestCase {
  id: string;
  project_id: string;
  requirement_id?: string | null;
  test_design_id?: string | null;
  title: string;
  preconditions: string;
  steps: string[];
  expected_result: string;
  priority: TestCasePriority;
  automation_status: AutomationStatus;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface TestCaseCreate {
  project_id: string;
  requirement_id?: string | null;
  test_design_id?: string | null;
  title: string;
  preconditions?: string;
  steps?: string[];
  expected_result?: string;
  priority?: TestCasePriority;
  automation_status?: AutomationStatus;
  tags?: string[];
}

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number | null;
  children?: FileNode[] | null;
}

export interface GitChangedFile {
  path: string;
  status: string;
  staged: boolean;
}

export interface GitDiffResult {
  diff: string;
  changed_files: GitChangedFile[];
}

export interface DashboardStats {
  total_projects: number;
  total_requirements: number;
  total_test_cases: number;
  total_runs: number;
  recent_projects: Project[];
  recent_requirements: Requirement[];
  recent_test_cases: TestCase[];
}
