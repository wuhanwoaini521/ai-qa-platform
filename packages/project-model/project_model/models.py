from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FrameworkType(str, Enum):
    PLAYWRIGHT_PYTHON = "playwright_python"
    PYTEST_API = "pytest_api"
    CUSTOM = "custom"


class RequirementStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class TestDesignCategory(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    BOUNDARY = "BOUNDARY"
    NEGATIVE = "NEGATIVE"
    ANALYTICS = "ANALYTICS"
    API = "API"
    UI = "UI"


class TestCasePriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class AutomationStatus(str, Enum):
    MANUAL = "MANUAL"
    DRAFT = "DRAFT"
    AUTOMATED = "AUTOMATED"


class WorkspaceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INITIALIZING = "INITIALIZING"
    ARCHIVED = "ARCHIVED"
    ERROR = "ERROR"


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


# --- Base Model ---
class EntityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Project Models ---
class ProjectBase(EntityBase):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    repository_url: str | None = Field(default=None, max_length=500)
    default_branch: str = Field(default="main", max_length=100)
    framework_type: FrameworkType = Field(default=FrameworkType.PLAYWRIGHT_PYTHON)


class ProjectCreate(ProjectBase):
    bootstrap_workspace: bool = Field(
        default=True, description="Automatically initialize starter workspace directory structure"
    )


class ProjectUpdate(EntityBase):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    repository_url: str | None = None
    default_branch: str | None = None
    framework_type: FrameworkType | None = None


class Project(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Requirement Models ---
class RequirementBase(EntityBase):
    project_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    acceptance_criteria: str = Field(default="", max_length=5000)
    status: RequirementStatus = Field(default=RequirementStatus.DRAFT)


class RequirementCreate(RequirementBase):
    pass


class RequirementUpdate(EntityBase):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    acceptance_criteria: str | None = None
    status: RequirementStatus | None = None


class Requirement(RequirementBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Test Design Models ---
class TestDesignBase(EntityBase):
    requirement_id: str
    title: str = Field(..., min_length=1, max_length=200)
    category: TestDesignCategory = Field(default=TestDesignCategory.FUNCTIONAL)
    description: str = Field(default="", max_length=3000)
    risk: str = Field(default="Medium", max_length=100)
    status: str = Field(default="DRAFT", max_length=50)


class TestDesignCreate(TestDesignBase):
    pass


class TestDesignUpdate(EntityBase):
    title: str | None = None
    category: TestDesignCategory | None = None
    description: str | None = None
    risk: str | None = None
    status: str | None = None


class TestDesign(TestDesignBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Test Case Models ---
class TestCaseBase(EntityBase):
    project_id: str
    requirement_id: str | None = None
    test_design_id: str | None = None
    title: str = Field(..., min_length=1, max_length=250)
    preconditions: str = Field(default="", max_length=2000)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = Field(default="", max_length=2000)
    priority: TestCasePriority = Field(default=TestCasePriority.P1)
    automation_status: AutomationStatus = Field(default=AutomationStatus.MANUAL)
    tags: list[str] = Field(default_factory=list)


class TestCaseCreate(TestCaseBase):
    pass


class TestCaseUpdate(EntityBase):
    requirement_id: str | None = None
    test_design_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=250)
    preconditions: str | None = None
    steps: list[str] | None = None
    expected_result: str | None = None
    priority: TestCasePriority | None = None
    automation_status: AutomationStatus | None = None
    tags: list[str] | None = None


class TestCase(TestCaseBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Workspace Models ---
class WorkspaceBase(EntityBase):
    project_id: str
    path: str
    branch: str = "main"
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE


class WorkspaceCreate(EntityBase):
    project_id: str
    branch: str = "main"


class Workspace(WorkspaceBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- File Node Model for File Tree ---
class FileNodeType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


class FileNode(BaseModel):
    name: str
    path: str
    type: FileNodeType
    size: int | None = None
    children: list[FileNode] | None = None


class FileContentPayload(BaseModel):
    path: str
    content: str


class GitChangedFile(BaseModel):
    path: str
    status: str  # e.g., 'M', 'A', 'D', '??'
    staged: bool = False


class GitDiffResult(BaseModel):
    diff: str
    changed_files: list[GitChangedFile] = Field(default_factory=list)


# --- Automation Binding Models ---
class AutomationBindingStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    BROKEN = "BROKEN"


class AutomationBindingBase(EntityBase):
    test_case_id: str
    workspace_id: str
    nodeid: str = Field(..., description="Pytest nodeid e.g. tests/test_login.py::test_login_flow")
    file_path: str
    framework: FrameworkType = Field(default=FrameworkType.PLAYWRIGHT_PYTHON)
    status: AutomationBindingStatus = Field(default=AutomationBindingStatus.DRAFT)


class AutomationBindingCreate(AutomationBindingBase):
    pass


class AutomationBinding(AutomationBindingBase):
    id: str
    created_at: datetime
    updated_at: datetime


# --- Workspace Validation Models (Problems Panel) ---
class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationIssue(BaseModel):
    file: str
    line: int = 1
    column: int = 1
    severity: ValidationSeverity = ValidationSeverity.ERROR
    code: str | None = None
    message: str
    source: str = "linter"  # "syntax", "ruff", "pytest", "typecheck"


class ValidationReport(BaseModel):
    workspace_id: str
    valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)


# --- Pytest Collection Models (Test Explorer) ---
class CollectedTest(BaseModel):
    nodeid: str
    file: str
    class_name: str | None = None
    test_name: str
    markers: list[str] = Field(default_factory=list)
    line: int | None = None


class CollectionReport(BaseModel):
    workspace_id: str
    total: int = 0
    tests: list[CollectedTest] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --- File Operations Models ---
class CreateFilePayload(BaseModel):
    path: str
    is_directory: bool = False
    content: str = ""


class RenameFilePayload(BaseModel):
    old_path: str
    new_path: str


# --- QA Assistant Models ---
class QAContext(BaseModel):
    project_id: str
    project_name: str = ""
    requirement_title: str | None = None
    test_case_title: str | None = None
    current_file: str | None = None
    selected_code: str | None = None
    open_files: list[str] = Field(default_factory=list)
    git_diff: str | None = None
    latest_validation: ValidationReport | None = None
    latest_run_summary: str | None = None


class QAChatRequest(BaseModel):
    action: str  # "explain", "generate_draft", "suggest_refactor", "analyze_error", "chat"
    message: str = ""
    context: QAContext


class QAChatResponse(BaseModel):
    response: str
    suggested_code: str | None = None
    target_file: str | None = None
    action_type: str = "reply"


# --- Test Execution & Run Models ---
class TestExecution(EntityBase):
    id: str
    run_id: str
    nodeid: str
    status: RunStatus = RunStatus.QUEUED
    duration_ms: float = 0.0
    error_message: str | None = None
    stack_trace: str | None = None
    failure_category: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TestRun(EntityBase):
    id: str
    project_id: str
    workspace_id: str
    status: RunStatus = RunStatus.QUEUED
    requested_by: str = "user"
    environment: dict[str, str] = Field(default_factory=dict)
    browser: str = "chromium"
    markers: list[str] = Field(default_factory=list)
    nodeids: list[str] = Field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    duration_ms: float = 0.0
    runner_type: str = "LOCAL"
    runner_profile_id: str | None = None
    external_job_id: str | None = None
    external_build_url: str | None = None
    queue_duration_ms: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    executions: list[TestExecution] = Field(default_factory=list)
    external_artifacts: list[ExternalArtifactReference] = Field(default_factory=list)


class TestRunCreate(BaseModel):
    project_id: str
    workspace_id: str
    nodeids: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    browser: str = "chromium"
    headless: bool = True
    requested_by: str = "user"
    runner_type: str = "LOCAL"
    runner_profile_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


# --- Failure Diagnosis & Repair Models ---
class FailureRecord(EntityBase):
    id: str
    run_id: str
    execution_id: str
    test_nodeid: str
    test_name: str
    classification: str  # "LOCATOR_CHANGED", "TIMING_ISSUE", "ASSERTION_FAILURE", "ENVIRONMENT_ERROR"
    exception_type: str
    error_message: str
    stack_trace: str
    failing_locator: str | None = None
    screenshot_path: str | None = None
    trace_path: str | None = None
    dom_snapshot_path: str | None = None
    console_logs: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    repair_proposal: dict[str, Any] | None = None
    created_at: datetime


class ApplyRepairRequest(BaseModel):
    file_path: str
    old_code: str
    new_code: str


# --- Phase 5: Production AI Models ---
class AIProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DISABLED = "DISABLED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


class AIStatusResponse(BaseModel):
    provider: str
    status: AIProviderStatus
    message: str = ""
    model: str = ""
    base_url: str | None = None


class AIInvocationDTO(EntityBase):
    id: str
    task: str
    provider: str
    model: str
    started_at: datetime
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    fallback_used: bool = False
    status: str = "SUCCESS"
    error_type: str | None = None
    prompt_version: str | None = None


class AIUsageSummary(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    invocations: list[AIInvocationDTO] = Field(default_factory=list)


class RequirementAnalysisDTO(BaseModel):
    summary: str
    risks: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    suggested_test_dimensions: list[str] = Field(default_factory=list)


class TestDesignSuggestion(BaseModel):
    title: str
    category: str = "FUNCTIONAL"
    description: str = ""
    risk: str = "Medium"


class TestCaseGenerationItem(BaseModel):
    title: str
    preconditions: str = ""
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""
    priority: str = "P1"
    tags: list[str] = Field(default_factory=list)


# --- Phase 6: Run History & Flaky Intelligence Models ---
class FlakyClassification(str, Enum):
    STABLE = "STABLE"
    LIKELY_FLAKY = "LIKELY_FLAKY"
    PERSISTENT_FAILURE = "PERSISTENT_FAILURE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class FlakyScore(BaseModel):
    sample_count: int = 0
    failure_rate: float = 0.0
    rerun_recovery_rate: float = 0.0
    alternation_rate: float = 0.0
    recent_instability: float = 0.0
    score: float = 0.0
    confidence: float = 0.0
    classification: FlakyClassification = FlakyClassification.INSUFFICIENT_DATA
    main_failure_category: str | None = None
    last_failure_at: datetime | None = None


class TestTrend(BaseModel):
    sample_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    average_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    retry_count: int = 0
    failure_categories: dict[str, int] = Field(default_factory=dict)


class FlakyTestItem(BaseModel):
    nodeid: str
    test_name: str
    project_id: str
    test_case_id: str | None = None
    flaky_score: FlakyScore
    trend: TestTrend


class TestHistoryItem(BaseModel):
    id: str
    run_id: str
    nodeid: str
    status: RunStatus
    duration_ms: float
    retry_count: int = 0
    failure_category: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None


class TestHistoryResponse(BaseModel):
    nodeid: str
    project_id: str
    test_case_id: str | None = None
    executions: list[TestHistoryItem] = Field(default_factory=list)
    trend: TestTrend
    flaky_score: FlakyScore


class FailureRecurrenceItem(BaseModel):
    failure_id: str
    run_id: str
    nodeid: str
    test_name: str
    classification: str
    error_message: str
    created_at: datetime


# --- Phase 7: Runner Platform Models ---
class RunnerType(str, Enum):
    LOCAL = "LOCAL"
    JENKINS = "JENKINS"
    DOCKER = "DOCKER"
    GITHUB_ACTIONS = "GITHUB_ACTIONS"


class RunnerProfileBase(EntityBase):
    project_id: str | None = None
    name: str = Field(..., min_length=1, max_length=150)
    type: RunnerType = RunnerType.LOCAL
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class RunnerProfileCreate(RunnerProfileBase):
    pass


class RunnerProfileUpdate(EntityBase):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class RunnerProfile(RunnerProfileBase):
    id: str
    created_at: datetime
    updated_at: datetime


class RunnerHealthStatus(BaseModel):
    runner_id: str
    type: RunnerType
    status: str  # AVAILABLE, AUTH_ERROR, UNAVAILABLE, TIMEOUT, DISABLED
    message: str = ""
    base_url: str | None = None


class ExternalArtifactReference(EntityBase):
    id: str
    run_id: str
    name: str
    type: str  # ALLURE, HTML_REPORT, SCREENSHOT, TRACE, LOGS
    url: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- Dashboard Stats ---
class DashboardStats(BaseModel):
    total_projects: int = 0
    total_requirements: int = 0
    total_test_cases: int = 0
    total_runs: int = 0
    runs_today: int = 0
    tests_executed_today: int = 0
    pass_rate_today: float = 0.0
    total_failures: int = 0
    flaky_tests_count: int = 0
    rerun_recovery_count: int = 0
    average_test_duration_ms: float = 0.0
    recent_projects: list[Project] = Field(default_factory=list)
    recent_requirements: list[Requirement] = Field(default_factory=list)
    recent_test_cases: list[TestCase] = Field(default_factory=list)
    recent_runs: list[TestRun] = Field(default_factory=list)


# --- Phase 8: Git, Branch, PR & GitHub Check Models ---
class BranchInfo(BaseModel):
    name: str
    is_current: bool = False
    commit_sha: str = ""
    commit_message: str = ""


class GitCommitInfo(BaseModel):
    sha: str
    message: str
    author_name: str
    author_email: str
    date: str


class GitCommitRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    author_name: str | None = None
    author_email: str | None = None


class GitBranchCreateRequest(BaseModel):
    branch_name: str = Field(..., min_length=1, max_length=150)
    checkout: bool = True


class GitPushResult(BaseModel):
    success: bool
    branch: str
    remote: str = "origin"
    message: str = ""


class CheckStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CheckRun(BaseModel):
    id: str
    name: str
    status: CheckStatus
    conclusion: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    html_url: str | None = None
    failure_summary: str | None = None
    failure_logs: str | None = None


class PRChecksSummary(BaseModel):
    pr_number: int
    pr_url: str
    head_branch: str
    overall_status: CheckStatus
    checks: list[CheckRun] = Field(default_factory=list)


class PullRequestInfo(EntityBase):
    id: str
    number: int
    title: str
    body: str
    html_url: str
    state: str = "open"  # "open", "closed", "merged"
    head_branch: str
    base_branch: str = "main"
    created_at: datetime
    updated_at: datetime
    checks_summary: PRChecksSummary | None = None


class PullRequestCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=250)
    body: str = Field(default="", max_length=10000)
    head_branch: str | None = None
    base_branch: str = "main"
    requirement_ids: list[str] = Field(default_factory=list)
    test_case_ids: list[str] = Field(default_factory=list)


class PRSummarySuggestionRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)
    test_case_ids: list[str] = Field(default_factory=list)
    include_diff: bool = True


class PRSummarySuggestionResponse(BaseModel):
    title: str
    body: str
    summary_bullets: list[str] = Field(default_factory=list)


class PRDiagnosisRequest(BaseModel):
    check_run_id: str
    failure_logs: str = ""


class PRDiagnosisResponse(BaseModel):
    classification: str  # "TEST_FAILURE", "LINT_FAILURE", "BUILD_FAILURE", "DEPENDENCY_FAILURE", "TYPE_FAILURE"
    summary: str
    root_cause: str
    suggested_fix: str
    affected_files: list[str] = Field(default_factory=list)
