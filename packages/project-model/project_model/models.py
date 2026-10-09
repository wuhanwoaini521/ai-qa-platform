from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from project_model.lifecycle import ModernTestModel, RequirementDocument, TestScenario


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
    SKIPPED = "SKIPPED"
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
    demo_kind: str | None = None
    created_at: datetime
    updated_at: datetime


# --- Requirement Models ---
class RequirementBase(EntityBase):
    project_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    acceptance_criteria: str = Field(default="", max_length=5000)
    status: RequirementStatus = Field(default=RequirementStatus.DRAFT)
    external_system: str | None = Field(default=None, max_length=50)  # e.g. "JIRA"
    external_id: str | None = Field(default=None, max_length=100)  # e.g. "EC-12345"
    external_url: str | None = Field(default=None, max_length=500)
    qa_model: RequirementDocument | None = None


class RequirementCreate(RequirementBase):
    pass


class RequirementUpdate(EntityBase):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    acceptance_criteria: str | None = None
    status: RequirementStatus | None = None
    external_system: str | None = None
    external_id: str | None = None
    external_url: str | None = None
    qa_model: RequirementDocument | None = None


class Requirement(RequirementBase):
    analysis_stale: bool = False
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
    scenario_model: TestScenario | None = None


class TestDesignCreate(TestDesignBase):
    pass


class TestDesignUpdate(EntityBase):
    title: str | None = None
    category: TestDesignCategory | None = None
    description: str | None = None
    risk: str | None = None
    status: str | None = None
    scenario_model: TestScenario | None = None


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
    external_system: str | None = Field(default=None, max_length=50)  # e.g. "TESTRAIL"
    external_case_id: str | None = Field(default=None, max_length=100)  # e.g. "C12345"
    external_url: str | None = Field(default=None, max_length=500)
    test_model: ModernTestModel | None = None


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
    external_system: str | None = None
    external_case_id: str | None = None
    external_url: str | None = None
    test_model: ModernTestModel | None = None


class TestCase(TestCaseBase):
    id: str
    binding: AutomationBinding | None = None
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
    test_case_id: str | None = None
    requirement_id: str | None = None
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


class TestBrowserSession(EntityBase):
    page_evidence: dict[str, Any] = Field(default_factory=dict)
    id: str
    run_id: str
    case_execution_id: str | None = None
    worker_id: str
    browser_session_id: str
    page_id: str
    nodeid: str
    case_name: str
    current_url: str = ""
    status: str = "running"
    elapsed_ms: float = 0.0
    started_at: datetime
    finished_at: datetime | None = None


class Breakpoint(EntityBase):
    id: str
    workspace_id: str
    file_path: str
    line_number: int
    enabled: bool = True
    source: str = "manual"
    run_id: str | None = None
    created_at: datetime
    updated_at: datetime


class BreakpointUpsert(BaseModel):
    file_path: str = Field(min_length=1, max_length=500)
    line_number: int = Field(ge=1, le=1_000_000)
    enabled: bool = True
    source: str = Field(default="manual", pattern=r"^(manual|auto_failure)$")
    run_id: str | None = Field(default=None, max_length=36)


class DebugSessionCreate(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=36)
    nodeid: str = Field(min_length=1, max_length=1000)


class DebugSessionBootstrap(BaseModel):
    id: str
    workspace_id: str
    nodeid: str
    status: str = "STARTING"
    breakpoints: list[Breakpoint] = Field(default_factory=list)


class TestRun(EntityBase):
    __test__ = False
    id: str
    task_id: str | None = None
    parent_run_id: str | None = None
    origin_failure_id: str | None = None
    project_id: str
    workspace_id: str
    status: RunStatus = RunStatus.QUEUED
    requested_by: str = "user"
    environment: dict[str, str] = Field(default_factory=dict)
    browser: str = "chromium"
    parallel_workers: int = 1
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
    #: Runner console output for a finished run (empty while it is still streaming).
    log_output: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    executions: list[TestExecution] = Field(default_factory=list)
    browser_sessions: list[TestBrowserSession] = Field(default_factory=list)
    external_artifacts: list[ExternalArtifactReference] = Field(default_factory=list)


class TestRunCreate(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)
    parent_run_id: str | None = None
    origin_failure_id: str | None = None
    project_id: str
    workspace_id: str
    nodeids: list[str] = Field(default_factory=list)
    markers: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    browser: str = "chromium"
    headless: bool = True
    parallel_workers: int = Field(default=1, ge=1, le=16)
    requested_by: str = "user"
    runner_type: str = "LOCAL"
    runner_profile_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_parallel_runner(self) -> TestRunCreate:
        if self.parallel_workers > 1 and self.runner_type.upper() != "LOCAL":
            raise ValueError("Parallel pytest workers are supported by the local runner only.")
        if self.idempotency_key and self.runner_type.upper() != "LOCAL":
            raise ValueError("Run request idempotency is currently supported by the local runner only.")
        return self


# --- Failure Diagnosis & Repair Models ---
class FailureRecord(EntityBase):
    failure_kind: str = "UNKNOWN"
    evidence_bundle: dict[str, Any] = Field(default_factory=dict)
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


class FailureRepairState(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    DECIDING = "DECIDING"
    VERIFYING_CANDIDATE = "VERIFYING_CANDIDATE"
    PATCH_READY = "PATCH_READY"
    APPLYING = "APPLYING"
    PATCH_APPLIED = "PATCH_APPLIED"
    VERIFYING_FIX = "VERIFYING_FIX"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ROLLED_BACK = "ROLLED_BACK"


class FailureRepairAction(str, Enum):
    START_ANALYSIS = "START_ANALYSIS"
    APPLY = "APPLY"
    VERIFY = "VERIFY"
    ROLLBACK = "ROLLBACK"
    RETRY = "RETRY"
    CREATE_ISSUE_DRAFT = "CREATE_ISSUE_DRAFT"


class FailureRepairWorkflow(BaseModel):
    """Server-owned repair state and the commands currently legal for the client."""

    repair_id: str | None = None
    failure_id: str
    analysis_id: str | None = None
    state: FailureRepairState
    allowed_actions: list[FailureRepairAction] = Field(default_factory=list)
    verification_run_id: str | None = None
    verification_run_status: str | None = None
    retry_run_id: str | None = None
    retry_run_status: str | None = None
    verified: bool = False
    repair_proposal: dict[str, Any] | None = None


# --- Phase 5: Production AI Models ---
class AIProviderStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DISABLED = "DISABLED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


class AIProviderRuntimeState(str, Enum):
    REAL_CONNECTED = "REAL_CONNECTED"
    FALLBACK = "FALLBACK"
    SIMULATION = "SIMULATION"
    UNAVAILABLE = "UNAVAILABLE"


class AIStatusResponse(BaseModel):
    provider: str
    status: AIProviderRuntimeState
    message: str = ""
    model: str = ""
    base_url: str | None = None
    real_model_available: bool = False
    fallback_active: bool = False
    failure_reason: str | None = None
    health_status: AIProviderStatus = AIProviderStatus.UNAVAILABLE
    operational_state: str = "UNAVAILABLE"
    streaming: bool = False
    latency_ms: float | None = None
    checked_at: datetime | None = None


class AIProviderSettingsResponse(BaseModel):
    enabled: bool = True
    provider: str
    api_key_configured: bool = False
    api_key_masked: str | None = None
    model: str
    base_url: str
    timeout: float
    max_retries: int
    max_request_tokens: int = 1_000_000
    max_daily_requests: int = 1000
    max_task_calls: int = 8


class AIProviderSettingsUpdate(BaseModel):
    provider: str = Field(pattern=r"^(fake|openai-compatible)$")
    api_key: str | None = None
    clear_api_key: bool = False
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=2048)
    timeout: float = Field(ge=1, le=300)
    max_retries: int = Field(ge=0, le=10)
    max_request_tokens: int = Field(default=1_000_000, ge=512, le=1_000_000)
    max_daily_requests: int = Field(default=1000, ge=1, le=100000)
    max_task_calls: int = Field(default=8, ge=1, le=100)


class AIProviderConnectionResult(BaseModel):
    connected: bool
    provider: str
    status: str
    message: str
    model: str
    streaming: bool = False
    structured_output_supported: bool | None = None
    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=utc_now)


class AIInvocationDTO(EntityBase):
    request_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
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
    token_source: str = "unknown"
    decision_name: str | None = None
    decision_choice: str | None = None
    decision_confidence: float | None = None


class AIUsageSummary(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    invocations: list[AIInvocationDTO] = Field(default_factory=list)
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_requests: int = 0
    unknown_token_requests: int = 0
    features: list[dict[str, Any]] = Field(default_factory=list)


class DecisionOption(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)


class DecisionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    state: Any
    options: list[DecisionOption] = Field(min_length=1, max_length=255)
    instructions: str | None = Field(default=None, max_length=2000)


class DecisionResult(BaseModel):
    choice: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    provider: str
    model: str | None = None
    attempted_provider: str | None = None
    attempted_model: str | None = None
    attempted_choice: str | None = None
    minimum_confidence: float | None = None
    usage: dict[str, int | float | None] | None = None
    fallback_used: bool = False
    reason: str | None = None


class JevSettingsUpdate(BaseModel):
    enabled: bool = False
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False
    model: str = Field(default="jev-1.13.0", min_length=1, max_length=128)
    base_url: str = Field(default="https://api.typesafe.ai/v1/systemone", min_length=1, max_length=2048)
    timeout: float = Field(default=20, gt=0, le=120)
    minimum_confidence: float = Field(default=0.60, ge=0, le=1)


class JevSettingsResponse(BaseModel):
    enabled: bool
    api_key_configured: bool
    api_key_masked: str | None = None
    model: str
    base_url: str
    timeout: float
    minimum_confidence: float


class DecisionConnectionResult(BaseModel):
    connected: bool
    code: str
    message: str
    choice: str | None = None
    model: str | None = None
    latency_ms: float | None = None


class JevRuntimeCheckResponse(BaseModel):
    connectivity: str
    runtime: str
    enabled: bool
    api_key_configured: bool
    provider: str
    model: str
    base_url_valid: bool
    minimum_confidence: float
    budget_available: bool
    latency_ms: float | None = None
    reasons: list[str] = Field(default_factory=list)


class DecisionPlaygroundResult(DecisionResult):
    decision_name: str


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
    WORKER = "WORKER"
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
    pass_rate_today: float | None = None
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


# --- Phase 9: Jira, TestRail & Integration Audit Models ---
class JiraIssue(BaseModel):
    key: str  # e.g. "PROJ-1234"
    summary: str
    description: str = ""
    acceptance_criteria: str = ""
    status: str = "Open"
    priority: str = "Medium"
    labels: list[str] = Field(default_factory=list)
    url: str = ""


class JiraImportRequest(BaseModel):
    issue_keys: list[str] = Field(..., min_length=1)
    project_id: str


class JiraBugDraftRequest(BaseModel):
    failure_id: str
    project_key: str = "QA"
    issue_type: str = "Bug"


class JiraBugDraft(BaseModel):
    summary: str
    project_key: str = "QA"
    issue_type: str = "Bug"
    description: str
    priority: str = "High"
    environment: dict[str, str] = Field(default_factory=dict)
    steps_to_reproduce: list[str] = Field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    error_trace: str = ""
    failure_id: str
    run_id: str
    artifact_urls: list[str] = Field(default_factory=list)


class JiraCreateBugRequest(BaseModel):
    draft: JiraBugDraft
    confirm_publish: bool = False  # Dry-run by default unless explicitly confirmed


class JiraCreateBugResponse(BaseModel):
    key: str
    url: str
    status: str
    published: bool = False
    message: str = ""


class TestRailCase(BaseModel):
    __test__ = False
    id: str  # "C12345"
    title: str
    section: str = "General"
    suite_id: str = "S1"
    url: str = ""


class TestRailPublishPreviewItem(BaseModel):
    __test__ = False
    test_nodeid: str
    test_name: str
    external_case_id: str | None = None
    pytest_status: str
    mapped_testrail_status: str  # e.g. "Passed", "Failed", "Blocked"
    comment: str = ""


class TestRailPublishPreview(BaseModel):
    __test__ = False
    run_id: str
    suite_id: str
    total_tests: int
    mapped_tests: int
    unmapped_tests: int
    items: list[TestRailPublishPreviewItem] = Field(default_factory=list)


class TestRailPublishRequest(BaseModel):
    __test__ = False
    run_id: str
    suite_id: str = "S101"
    confirm_publish: bool = False  # Dry-run by default
    status_mapping: dict[str, str] = Field(default_factory=dict)


class TestRailPublishResponse(BaseModel):
    __test__ = False
    success: bool
    published: bool
    testrail_run_id: str | None = None
    total_published: int = 0
    message: str = ""


class IntegrationAuditEntry(EntityBase):
    id: str
    system: str  # "JIRA", "TESTRAIL", "GITHUB", "JENKINS"
    action: str  # "IMPORT_REQUIREMENT", "CREATE_BUG", "PUBLISH_RESULT"
    target_id: str
    user_id: str = "user"
    status: str = "SUCCESS"  # "SUCCESS", "FAILED", "DRY_RUN"
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- Phase 10: Quality Intelligence, Coverage & Release Models ---
class RequirementCoverageItem(BaseModel):
    requirement_id: str
    title: str
    test_design_count: int = 0
    test_case_count: int = 0
    automated_case_count: int = 0
    status: str = "DRAFT"
    coverage_percentage: float = 0.0
    has_automation: bool = False


class QualityCoverageSummary(BaseModel):
    total_requirements: int = 0
    covered_requirements: int = 0
    requirement_coverage_pct: float = 0.0
    total_test_cases: int = 0
    manual_cases: int = 0
    draft_cases: int = 0
    automated_cases: int = 0
    automation_coverage_pct: float = 0.0
    executed_cases_recent: int = 0
    execution_coverage_pct: float = 0.0
    requirement_details: list[RequirementCoverageItem] = Field(default_factory=list)


class QualityRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class QualityRiskItem(BaseModel):
    id: str
    area: str
    risk_level: QualityRiskLevel = QualityRiskLevel.LOW
    score: float = 0.0  # 0.0 to 100.0 (higher = riskier)
    reasons: list[str] = Field(default_factory=list)
    impacted_nodeids: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class QualityRiskMatrix(BaseModel):
    project_id: str
    overall_quality_score: float = 100.0  # 0 to 100 (higher = healthier)
    overall_risk_level: QualityRiskLevel = QualityRiskLevel.LOW
    risks: list[QualityRiskItem] = Field(default_factory=list)
    high_risk_count: int = 0
    unautomated_p0_count: int = 0
    flaky_test_count: int = 0


class ImpactAnalysisRequest(BaseModel):
    project_id: str
    workspace_id: str | None = None
    changed_files: list[str] = Field(default_factory=list)


class ImpactAnalysisResult(BaseModel):
    __test__ = False
    changed_files: list[str] = Field(default_factory=list)
    impacted_requirements: list[str] = Field(default_factory=list)
    impacted_test_cases: list[str] = Field(default_factory=list)
    recommended_regression_tests: list[str] = Field(default_factory=list)
    confidence_score: float = 0.85
    rationale: list[str] = Field(default_factory=list)


class ReleaseStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_QA = "IN_QA"
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    RELEASED = "RELEASED"


class ReleaseBase(EntityBase):
    project_id: str
    version: str  # e.g. "v1.4.0"
    name: str
    description: str = ""
    status: ReleaseStatus = ReleaseStatus.PLANNED
    target_date: str = ""
    pass_rate_threshold: float = 95.0
    max_allowed_flaky: int = 0
    quality_score: float = 0.0
    blockers: list[str] = Field(default_factory=list)


class ReleaseCreate(ReleaseBase):
    pass


class ReleaseUpdate(EntityBase):
    name: str | None = None
    description: str | None = None
    status: ReleaseStatus | None = None
    target_date: str | None = None
    pass_rate_threshold: float | None = None
    max_allowed_flaky: int | None = None
    quality_score: float | None = None
    blockers: list[str] | None = None


class Release(ReleaseBase):
    id: str
    created_at: datetime
    updated_at: datetime


class ReleaseGateReport(BaseModel):
    release_id: str
    version: str
    can_release: bool
    pass_rate: float
    pass_rate_met: bool
    flaky_count: int
    flaky_met: bool
    unautomated_p0_count: int
    unautomated_p0_met: bool
    quality_score: float
    blockers: list[str] = Field(default_factory=list)
    verdict: str = "PENDING"


# --- Phase 11: Identity, RBAC, Audit & Enterprise Security Models ---
class UserRole(str, Enum):
    ADMIN = "ADMIN"
    QA_LEAD = "QA_LEAD"
    QA_ENGINEER = "QA_ENGINEER"
    VIEWER = "VIEWER"


class Permission(str, Enum):
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    REQUIREMENT_WRITE = "requirement:write"
    TEST_CASE_WRITE = "test_case:write"
    AUTOMATION_EDIT = "automation:edit"
    RUN_EXECUTE = "run:execute"
    RELEASE_GATE = "release:gate"
    INTEGRATION_MANAGE = "integration:manage"
    SECURITY_ADMIN = "security:admin"


ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.ADMIN: {p for p in Permission},
    UserRole.QA_LEAD: {
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.REQUIREMENT_WRITE,
        Permission.TEST_CASE_WRITE,
        Permission.AUTOMATION_EDIT,
        Permission.RUN_EXECUTE,
        Permission.RELEASE_GATE,
        Permission.INTEGRATION_MANAGE,
    },
    UserRole.QA_ENGINEER: {
        Permission.PROJECT_READ,
        Permission.REQUIREMENT_WRITE,
        Permission.TEST_CASE_WRITE,
        Permission.AUTOMATION_EDIT,
        Permission.RUN_EXECUTE,
    },
    UserRole.VIEWER: {
        Permission.PROJECT_READ,
    },
}


class UserBase(EntityBase):
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.QA_ENGINEER
    is_active: bool = True
    avatar_url: str | None = None


class UserCreate(UserBase):
    password: str | None = None


class UserUpdate(EntityBase):
    email: str | None = None
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    avatar_url: str | None = None


class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime


class TeamBase(EntityBase):
    name: str = Field(..., min_length=1, max_length=150)
    description: str = ""


class TeamCreate(TeamBase):
    pass


class TeamUpdate(EntityBase):
    name: str | None = None
    description: str | None = None


class TeamMember(EntityBase):
    team_id: str
    user_id: str
    role: str = "MEMBER"  # "LEAD", "MEMBER"
    created_at: datetime


class AddMemberRequest(EntityBase):
    user_id: str
    role: str = "MEMBER"


class Team(TeamBase):
    id: str
    member_count: int = 0
    members: list[TeamMember] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ApiKeyBase(EntityBase):
    name: str = Field(..., min_length=1, max_length=100)
    user_id: str
    expires_at: datetime | None = None


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKey(ApiKeyBase):
    id: str
    key_prefix: str
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKey):
    raw_api_key: str  # Only returned once on creation


class LoginRequest(BaseModel):
    email: str
    password: str = "password123"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
    permissions: list[str] = Field(default_factory=list)


class SecurityAuditLogEntry(EntityBase):
    id: str
    action: str  # "LOGIN", "USER_CREATE", "ROLE_CHANGE", "API_KEY_CREATE", "RELEASE_APPROVED", "INTEGRATION_WRITE"
    actor_id: str
    actor_email: str
    target_resource: str
    ip_address: str = "127.0.0.1"
    status: str = "SUCCESS"  # "SUCCESS", "DENIED", "FAILED"
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- Phase 12: Distributed Execution Platform Models ---
class WorkerStatus(str, Enum):
    ONLINE = "ONLINE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"
    LOST = "LOST"


class WorkerBase(EntityBase):
    hostname: str = Field(..., min_length=1, max_length=255)
    ip_address: str = "127.0.0.1"
    status: WorkerStatus = WorkerStatus.ONLINE
    browsers: list[str] = Field(default_factory=lambda: ["chromium", "firefox", "webkit"])
    os: str = "linux"
    max_concurrency: int = 4
    current_load: int = 0
    tags: list[str] = Field(default_factory=list)


class WorkerCreate(WorkerBase):
    pass


class Worker(WorkerBase):
    id: str
    last_heartbeat_at: datetime
    registered_at: datetime


class WorkerHeartbeatRequest(BaseModel):
    status: WorkerStatus = WorkerStatus.ONLINE
    current_load: int = 0
    active_job_ids: list[str] = Field(default_factory=list)


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionJobBase(EntityBase):
    run_id: str
    project_id: str
    workspace_id: str
    nodeids: list[str] = Field(default_factory=list)
    runner_type: str = "LOCAL"  # "LOCAL", "DOCKER", "WORKER"
    browser: str = "chromium"
    priority: int = 10  # higher number = higher priority
    status: JobStatus = JobStatus.QUEUED
    assigned_worker_id: str | None = None
    retry_count: int = 0
    max_retries: int = 2
    error_message: str | None = None


class ExecutionJobCreate(ExecutionJobBase):
    pass


class ClaimJobRequest(EntityBase):
    worker_id: str
    browser: str = "chromium"


class CompleteJobRequest(EntityBase):
    duration_ms: float = 0.0


class FailJobRequest(EntityBase):
    error_message: str


class ExecutionJob(ExecutionJobBase):
    id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    created_at: datetime
    updated_at: datetime


class ClusterStatusSummary(BaseModel):
    total_workers: int = 0
    online_workers: int = 0
    busy_workers: int = 0
    offline_workers: int = 0
    total_concurrency_capacity: int = 0
    used_concurrency: int = 0
    queued_jobs_count: int = 0
    running_jobs_count: int = 0
    workers: list[Worker] = Field(default_factory=list)


class ArtifactUploadResponse(BaseModel):
    artifact_id: str
    filename: str
    size_bytes: int
    content_type: str
    storage_type: str  # "LOCAL", "S3"
    storage_url: str


class ArtifactDownloadInfo(BaseModel):
    artifact_id: str
    filename: str
    download_url: str
    expires_in_seconds: int = 3600
