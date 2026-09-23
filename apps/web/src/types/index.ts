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
  binding?: AutomationBinding | null;
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

export interface AutomationBinding {
  id: string;
  test_case_id: string;
  framework_type: FrameworkType;
  test_file_path: string;
  test_node_id: string;
  status: AutomationStatus;
  last_generated_code?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationBindingCreate {
  framework_type?: FrameworkType;
  test_file_path: string;
  test_node_id: string;
  status?: AutomationStatus;
  last_generated_code?: string | null;
}

export interface GenerateAutomationResponse {
  test_case_id: string;
  target_file: string;
  suggested_code: string;
  grounded_knowledge: string[];
  page_objects: string[];
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

export interface ValidationIssue {
  file: string;
  line: number;
  column: number;
  message: string;
  severity: 'error' | 'warning' | 'info';
  rule_id: string;
}

export interface WorkspaceValidationResult {
  is_valid: boolean;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
}

export interface CollectedTest {
  nodeid: string;
  name: string;
  path: string;
  line: number;
  markers: string[];
  docstring: string;
}

export type TestRunStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'ERROR' | 'CANCELLED';

export interface TestRun {
  id: string;
  project_id: string;
  status: TestRunStatus;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  error_tests: number;
  duration_ms: number;
  triggered_by: string;
  target_nodeids?: string[];
  log_output: string;
  created_at: string;
  updated_at: string;
  executions: TestExecution[];
}

export interface TestRunCreate {
  project_id: string;
  target_nodeids?: string[];
  triggered_by?: string;
  timeout_seconds?: number;
}

export type TestExecutionStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'SKIPPED' | 'ERROR';

export interface TestExecution {
  id: string;
  test_run_id: string;
  test_case_id?: string | null;
  nodeid: string;
  status: TestExecutionStatus;
  duration_ms: number;
  stdout: string;
  stderr: string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export type FailureCategory =
  | 'LOCATOR_CHANGED'
  | 'TIMING_ISSUE'
  | 'ASSERTION_FAILURE'
  | 'ENVIRONMENT_ERROR'
  | 'UNKNOWN';

export interface FailureRecord {
  id: string;
  project_id: string;
  test_execution_id: string;
  nodeid: string;
  category: FailureCategory;
  error_message: string;
  stack_trace: string;
  suggested_action: string;
  is_resolved: boolean;
  created_at: string;
  updated_at: string;
}

export interface CandidateLocator {
  locator: string;
  confidence: number;
  strategy: string;
  reason: string;
}

export interface LocatorRepairProposal {
  target_file: string;
  line_number: number;
  broken_locator: string;
  proposed_locator: string;
  diff_preview: string;
  candidates: CandidateLocator[];
  confidence: number;
  explanation: string;
}

export interface ApplyRepairRequest {
  target_file: string;
  old_locator: string;
  new_locator: string;
}

export interface QAChatRequest {
  message: string;
  project_id?: string;
  current_file?: string;
  selected_code?: string;
  context_type?: 'chat' | 'explain' | 'generate' | 'refactor' | 'diagnose';
}

export interface QAChatResponse {
  reply: string;
  code_snippet?: string | null;
  suggested_actions: string[];
}

export interface DashboardStats {
  total_projects: number;
  total_requirements: number;
  total_test_cases: number;
  total_runs: number;
  runs_today: number;
  tests_executed_today: number;
  pass_rate: number;
  total_failures: number;
  recent_projects: Project[];
  recent_requirements: Requirement[];
  recent_test_cases: TestCase[];
  recent_runs: TestRun[];
}
