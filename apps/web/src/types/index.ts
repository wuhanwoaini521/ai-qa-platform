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
  external_system?: string | null;
  external_id?: string | null;
  external_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementCreate {
  project_id: string;
  title: string;
  description?: string;
  acceptance_criteria?: string;
  status?: RequirementStatus;
  external_system?: string | null;
  external_id?: string | null;
  external_url?: string | null;
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
  external_system?: string | null;
  external_case_id?: string | null;
  external_url?: string | null;
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
  external_system?: string | null;
  external_case_id?: string | null;
  external_url?: string | null;
}

export type AutomationBindingStatus = 'DRAFT' | 'VALIDATED' | 'ACTIVE' | 'BROKEN';

export interface AutomationBinding {
  id: string;
  test_case_id: string;
  workspace_id: string;
  framework: FrameworkType;
  /** Pytest node id, e.g. tests/test_login.py::test_login_flow */
  nodeid: string;
  file_path: string;
  status: AutomationBindingStatus;
  created_at: string;
  updated_at: string;
}

export interface AutomationBindingCreate {
  test_case_id: string;
  workspace_id: string;
  nodeid: string;
  file_path: string;
  framework?: FrameworkType;
  status?: AutomationBindingStatus;
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

export type RunnerType = 'LOCAL' | 'JENKINS' | 'DOCKER' | 'GITHUB_ACTIONS';

export interface RunnerProfile {
  id: string;
  project_id?: string | null;
  name: string;
  type: RunnerType;
  enabled: boolean;
  config: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface RunnerProfileCreate {
  project_id?: string | null;
  name: string;
  type: RunnerType;
  enabled?: boolean;
  config?: Record<string, any>;
}

export interface RunnerProfileUpdate {
  name?: string;
  enabled?: boolean;
  config?: Record<string, any>;
}

export interface RunnerHealthStatus {
  runner_id: string;
  type: RunnerType;
  status: 'AVAILABLE' | 'AUTH_ERROR' | 'UNAVAILABLE' | 'TIMEOUT' | 'DISABLED';
  message: string;
  base_url?: string | null;
}

export interface ExternalArtifactReference {
  id: string;
  run_id: string;
  name: string;
  type: string; // ALLURE, HTML_REPORT, SCREENSHOT, TRACE, LOGS
  url: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export type TestRunStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'ERROR' | 'CANCELLED';

export interface TestRun {
  id: string;
  project_id: string;
  workspace_id: string;
  status: TestRunStatus;
  requested_by: string;
  triggered_by?: string;
  runner_type?: string;
  runner_profile_id?: string | null;
  external_job_id?: string | null;
  external_build_url?: string | null;
  queue_duration_ms?: number;
  environment: Record<string, string>;
  browser: string;
  markers: string[];
  nodeids: string[];
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  cancelled: number;
  total_tests?: number;
  passed_tests?: number;
  failed_tests?: number;
  duration_ms: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  executions: TestExecution[];
  external_artifacts?: ExternalArtifactReference[];
  log_output?: string;
}

export interface TestRunCreate {
  project_id: string;
  /** The API keys a workspace by project id, so this is the project's workspace id. */
  workspace_id: string;
  nodeids?: string[];
  markers?: string[];
  environment?: Record<string, string>;
  browser?: string;
  requested_by?: string;
  runner_type?: RunnerType;
  runner_profile_id?: string | null;
  parameters?: Record<string, any>;
}

export type TestExecutionStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'SKIPPED' | 'ERROR';

export interface TestExecution {
  id: string;
  run_id: string;
  nodeid: string;
  status: TestRunStatus;
  duration_ms: number;
  retry_count?: number;
  error_message?: string | null;
  stack_trace?: string | null;
  failure_category?: string | null;
  artifact_paths: string[];
  started_at?: string | null;
  finished_at?: string | null;
}

export type FailureCategory =
  | 'LOCATOR_CHANGED'
  | 'TIMING_ISSUE'
  | 'ASSERTION_FAILURE'
  | 'ENVIRONMENT_ERROR'
  | 'UNKNOWN';

export interface FailureRecord {
  id: string;
  run_id: string;
  execution_id: string;
  test_nodeid: string;
  test_name: string;
  classification: FailureCategory | string;
  exception_type: string;
  error_message: string;
  stack_trace: string;
  failing_locator?: string | null;
  screenshot_path?: string | null;
  trace_path?: string | null;
  dom_snapshot_path?: string | null;
  console_logs: string[];
  suggested_action?: string | null;
  repair_proposal?: Record<string, unknown> | null;
  created_at: string;
}

/** Body accepted by `POST /api/failures/{id}/apply-repair` (workspace_id goes in the query). */
export interface ApplyRepairPayload {
  file_path: string;
  old_code: string;
  new_code: string;
}

export interface CandidateLocator {
  selector?: string;
  locator?: string;
  confidence: number;
  strategy: string;
  reason?: string;
}

export interface LocatorRepairProposal {
  /** The locator currently in the code (the API's field name). */
  old_locator: string;
  proposed_locator: string;
  confidence: number;
  strategy: string;
  reason?: string;
  code_diff?: string;
  /** File the proposal targets; null when the failure has no bound workspace file. */
  file_path?: string | null;
  /** Always false from the API: applying a repair is a separate, human-triggered call. */
  applied: boolean;
  candidates?: CandidateLocator[];
}

export interface ApplyRepairRequest {
  file_path: string;
  old_code: string;
  new_code: string;
}

export interface QAChatRequest {
  action?: string;
  message?: string;
  project_id?: string;
  current_file?: string | null;
  selected_code?: string | null;
  context_type?: string;
  context?: {
    project_id: string;
    project_name?: string;
    requirement_title?: string | null;
    test_case_title?: string | null;
    current_file?: string | null;
    selected_code?: string | null;
    open_files?: string[];
    git_diff?: string | null;
    latest_validation?: any | null;
    latest_run_summary?: string | null;
  };
}

export interface QAChatResponse {
  response?: string;
  reply?: string;
  suggested_code?: string | null;
  code_snippet?: string | null;
  target_file?: string | null;
  action_type?: string;
  suggested_actions?: string[];
}

export type AIProviderHealth = 'AVAILABLE' | 'DISABLED' | 'AUTH_ERROR' | 'RATE_LIMITED' | 'TIMEOUT' | 'UNAVAILABLE';

export interface AIStatusResponse {
  provider: string;
  status: AIProviderHealth;
  message: string;
  model: string;
  base_url?: string | null;
}

export interface AIInvocationDTO {
  id: string;
  task: string;
  provider: string;
  model: string;
  started_at: string;
  duration_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  retry_count: number;
  fallback_used: boolean;
  status: string;
  error_type?: string | null;
  prompt_version?: string | null;
}

export interface AIUsageSummary {
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  invocations: AIInvocationDTO[];
}

export interface RequirementAnalysisDTO {
  summary: string;
  risks: string[];
  ambiguities: string[];
  suggested_test_dimensions: string[];
}

export interface TestDesignSuggestion {
  title: string;
  category: TestDesignCategory | string;
  description: string;
  risk: string;
}

export interface TestCaseGenerationItem {
  title: string;
  preconditions: string;
  steps: string[];
  expected_result: string;
  priority: TestCasePriority | string;
  tags: string[];
}

export type FlakyClassification = 'STABLE' | 'LIKELY_FLAKY' | 'PERSISTENT_FAILURE' | 'INSUFFICIENT_DATA';

export interface FlakyScore {
  sample_count: number;
  failure_rate: number;
  rerun_recovery_rate: number;
  alternation_rate: number;
  recent_instability: number;
  score: number;
  confidence: number;
  classification: FlakyClassification;
  main_failure_category?: string | null;
  last_failure_at?: string | null;
}

export interface TestTrend {
  sample_count: number;
  pass_count: number;
  fail_count: number;
  skip_count: number;
  average_duration_ms: number;
  p95_duration_ms: number;
  retry_count: number;
  failure_categories: Record<string, number>;
}

export interface FlakyTestItem {
  nodeid: string;
  test_name: string;
  project_id: string;
  test_case_id?: string | null;
  flaky_score: FlakyScore;
  trend: TestTrend;
}

export interface TestHistoryItem {
  id: string;
  run_id: string;
  nodeid: string;
  status: TestRunStatus;
  duration_ms: number;
  retry_count: number;
  failure_category?: string | null;
  error_message?: string | null;
  started_at?: string | null;
}

export interface TestHistoryResponse {
  nodeid: string;
  project_id: string;
  test_case_id?: string | null;
  executions: TestHistoryItem[];
  trend: TestTrend;
  flaky_score: FlakyScore;
}

export interface FailureRecurrenceItem {
  failure_id: string;
  run_id: string;
  nodeid: string;
  test_name: string;
  classification: string;
  error_message: string;
  created_at: string;
}

export interface AIFailureDiagnosisResponse {
  classification: string;
  root_cause: string;
  evidence: string[];
  hypotheses: string[];
  recommended_actions: string[];
  confidence: number;
}

export interface LocatorSemanticReviewResponse {
  is_semantically_equivalent: boolean;
  confidence: number;
  explanation: string;
  risk_warning?: string | null;
}

export interface DashboardStats {
  total_projects: number;
  total_requirements: number;
  total_test_cases: number;
  total_runs: number;
  runs_today: number;
  tests_executed_today: number;
  pass_rate_today: number;
  total_failures: number;
  flaky_tests_count: number;
  rerun_recovery_count: number;
  average_test_duration_ms: number;
  recent_projects: Project[];
  recent_requirements: Requirement[];
  recent_test_cases: TestCase[];
  recent_runs: TestRun[];
}

export interface BranchInfo {
  name: string;
  is_current: boolean;
  commit_sha: string;
  commit_message: string;
}

export interface GitCommitInfo {
  sha: string;
  message: string;
  author_name: string;
  author_email: string;
  date: string;
}

export interface GitCommitRequest {
  message: string;
  author_name?: string;
  author_email?: string;
}

export interface GitBranchCreateRequest {
  branch_name: string;
  checkout?: boolean;
}

export interface GitPushResult {
  success: boolean;
  branch: string;
  remote: string;
  message: string;
}

export type CheckStatus = 'QUEUED' | 'RUNNING' | 'PASSED' | 'FAILED' | 'CANCELLED';

export interface CheckRun {
  id: string;
  name: string;
  status: CheckStatus;
  conclusion?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  html_url?: string | null;
  failure_summary?: string | null;
  failure_logs?: string | null;
}

export interface PRChecksSummary {
  pr_number: number;
  pr_url: string;
  head_branch: string;
  overall_status: CheckStatus;
  checks: CheckRun[];
}

export interface PullRequestInfo {
  id: string;
  number: number;
  title: string;
  body: string;
  html_url: string;
  state: string;
  head_branch: string;
  base_branch: string;
  created_at: string;
  updated_at: string;
  checks_summary?: PRChecksSummary | null;
}

export interface PullRequestCreateRequest {
  title: string;
  body: string;
  head_branch?: string;
  base_branch?: string;
  requirement_ids?: string[];
  test_case_ids?: string[];
}

export interface PRSummarySuggestionRequest {
  requirement_ids?: string[];
  test_case_ids?: string[];
  include_diff?: boolean;
}

export interface PRSummarySuggestionResponse {
  title: string;
  body: string;
  summary_bullets: string[];
}

export interface PRDiagnosisRequest {
  check_run_id: string;
  failure_logs?: string;
}

export interface PRDiagnosisResponse {
  classification: string;
  summary: string;
  root_cause: string;
  suggested_fix: string;
  affected_files: string[];
}

// --- Phase 9: Jira, TestRail & Integration Audit ---
export interface JiraIssue {
  key: string;
  summary: string;
  description: string;
  acceptance_criteria: string;
  status: string;
  priority: string;
  labels: string[];
  url: string;
}

export interface JiraImportRequest {
  issue_keys: string[];
  project_id: string;
}

export interface JiraBugDraftRequest {
  failure_id: string;
  project_key?: string;
  issue_type?: string;
}

export interface JiraBugDraft {
  summary: string;
  project_key: string;
  issue_type: string;
  description: string;
  priority: string;
  environment: Record<string, string>;
  steps_to_reproduce: string[];
  expected_result: string;
  actual_result: string;
  error_trace: string;
  failure_id: string;
  run_id: string;
  artifact_urls: string[];
}

export interface JiraCreateBugRequest {
  draft: JiraBugDraft;
  confirm_publish?: boolean;
}

export interface JiraCreateBugResponse {
  key: string;
  url: string;
  status: string;
  published: boolean;
  message: string;
}

export interface TestRailCase {
  id: string;
  title: string;
  section: string;
  suite_id: string;
  url: string;
}

export interface TestRailPublishPreviewItem {
  test_nodeid: string;
  test_name: string;
  external_case_id?: string | null;
  pytest_status: string;
  mapped_testrail_status: string;
  comment: string;
}

export interface TestRailPublishPreview {
  run_id: string;
  suite_id: string;
  total_tests: number;
  mapped_tests: number;
  unmapped_tests: number;
  items: TestRailPublishPreviewItem[];
}

export interface TestRailPublishRequest {
  run_id: string;
  suite_id?: string;
  confirm_publish?: boolean;
  status_mapping?: Record<string, string>;
}

export interface TestRailPublishResponse {
  success: boolean;
  published: boolean;
  testrail_run_id?: string | null;
  total_published: number;
  message: string;
}

export interface IntegrationAuditEntry {
  id: string;
  system: string;
  action: string;
  target_id: string;
  user_id: string;
  status: string;
  details: Record<string, unknown>;
  created_at: string;
}

// --- Phase 10: Quality Intelligence, Coverage & Release Gate ---
export interface RequirementCoverageItem {
  requirement_id: string;
  title: string;
  test_design_count: number;
  test_case_count: number;
  automated_case_count: number;
  status: string;
  coverage_percentage: number;
  has_automation: boolean;
}

export interface QualityCoverageSummary {
  total_requirements: number;
  covered_requirements: number;
  requirement_coverage_pct: number;
  total_test_cases: number;
  manual_cases: number;
  draft_cases: number;
  automated_cases: number;
  automation_coverage_pct: number;
  executed_cases_recent: number;
  execution_coverage_pct: number;
  requirement_details: RequirementCoverageItem[];
}

export type QualityRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface QualityRiskItem {
  id: string;
  area: string;
  risk_level: QualityRiskLevel;
  score: number;
  reasons: string[];
  impacted_nodeids: string[];
  recommended_actions: string[];
}

export interface QualityRiskMatrix {
  project_id: string;
  overall_quality_score: number;
  overall_risk_level: QualityRiskLevel;
  risks: QualityRiskItem[];
  high_risk_count: number;
  unautomated_p0_count: number;
  flaky_test_count: number;
}

export interface ImpactAnalysisRequest {
  project_id: string;
  workspace_id?: string | null;
  changed_files?: string[];
}

export interface ImpactAnalysisResult {
  changed_files: string[];
  impacted_requirements: string[];
  impacted_test_cases: string[];
  recommended_regression_tests: string[];
  confidence_score: number;
  rationale: string[];
}

export type ReleaseStatus = 'PLANNED' | 'IN_QA' | 'PASSED' | 'BLOCKED' | 'RELEASED';

export interface Release {
  id: string;
  project_id: string;
  version: string;
  name: string;
  description: string;
  status: ReleaseStatus;
  target_date: string;
  pass_rate_threshold: number;
  max_allowed_flaky: number;
  quality_score: number;
  blockers: string[];
  created_at: string;
  updated_at: string;
}

export interface ReleaseCreate {
  project_id: string;
  version: string;
  name: string;
  description?: string;
  status?: ReleaseStatus;
  target_date?: string;
  pass_rate_threshold?: number;
  max_allowed_flaky?: number;
}

export interface ReleaseUpdate {
  name?: string;
  description?: string;
  status?: ReleaseStatus;
  target_date?: string;
  pass_rate_threshold?: number;
  max_allowed_flaky?: number;
  quality_score?: number;
  blockers?: string[];
}

export interface ReleaseGateReport {
  release_id: string;
  version: string;
  can_release: boolean;
  pass_rate: number;
  pass_rate_met: boolean;
  flaky_count: number;
  flaky_met: boolean;
  unautomated_p0_count: number;
  unautomated_p0_met: boolean;
  quality_score: number;
  blockers: string[];
  verdict: string;
}

// --- Phase 11: Identity, RBAC & Enterprise Security ---
export type UserRole = 'ADMIN' | 'QA_LEAD' | 'QA_ENGINEER' | 'VIEWER';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  avatar_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCreate {
  email: string;
  full_name: string;
  role?: UserRole;
  password?: string;
  is_active?: boolean;
}

export interface UserUpdate {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  avatar_url?: string | null;
}

export interface TeamMember {
  team_id: string;
  user_id: string;
  role: string;
  created_at: string;
}

export interface Team {
  id: string;
  name: string;
  description: string;
  member_count: number;
  members: TeamMember[];
  created_at: string;
  updated_at: string;
}

export interface TeamCreate {
  name: string;
  description?: string;
}

export interface TeamUpdate {
  name?: string;
  description?: string;
}

export interface ApiKey {
  id: string;
  user_id: string;
  name: string;
  key_prefix: string;
  expires_at?: string | null;
  last_used_at?: string | null;
  created_at: string;
}

export interface ApiKeyCreate {
  name: string;
  user_id?: string;
  expires_at?: string | null;
}

export interface ApiKeyCreatedResponse extends ApiKey {
  raw_api_key: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
  permissions: string[];
}

export interface SecurityAuditLogEntry {
  id: string;
  action: string;
  actor_id: string;
  actor_email: string;
  target_resource: string;
  ip_address: string;
  status: string;
  details: Record<string, any>;
  created_at: string;
}

// --- Phase 12: Distributed Execution & Workers ---
export type WorkerStatus = 'ONLINE' | 'BUSY' | 'OFFLINE' | 'LOST';

export interface Worker {
  id: string;
  hostname: string;
  ip_address: string;
  status: WorkerStatus;
  browsers: string[];
  os: string;
  max_concurrency: number;
  current_load: number;
  tags: string[];
  last_heartbeat_at: string;
  registered_at: string;
}

export interface WorkerCreate {
  hostname: string;
  ip_address?: string;
  status?: WorkerStatus;
  browsers?: string[];
  os?: string;
  max_concurrency?: number;
  tags?: string[];
}

export interface WorkerHeartbeatRequest {
  status?: WorkerStatus;
  current_load?: number;
  active_job_ids?: string[];
}

export type JobStatus = 'QUEUED' | 'ASSIGNED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface ExecutionJob {
  id: string;
  run_id: string;
  project_id: string;
  workspace_id: string;
  nodeids: string[];
  runner_type: string;
  browser: string;
  priority: number;
  status: JobStatus;
  assigned_worker_id?: string | null;
  retry_count: number;
  max_retries: number;
  error_message?: string | null;
  duration_ms: number;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutionJobCreate {
  run_id: string;
  project_id: string;
  workspace_id: string;
  nodeids: string[];
  runner_type?: string;
  browser?: string;
  priority?: number;
}

export interface ClusterStatusSummary {
  total_workers: number;
  online_workers: number;
  busy_workers: number;
  offline_workers: number;
  total_concurrency_capacity: number;
  used_concurrency: number;
  queued_jobs_count: number;
  running_jobs_count: number;
  workers: Worker[];
}

export interface ArtifactUploadResponse {
  artifact_id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  storage_type: string;
  storage_url: string;
}

export interface ArtifactDownloadInfo {
  artifact_id: string;
  filename: string;
  download_url: string;
  expires_in_seconds: number;
}




