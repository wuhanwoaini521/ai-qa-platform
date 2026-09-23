from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    project_id: str
    workspace_path: str
    test_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    headless: bool = True


class TestResultItem(BaseModel):
    test_id: str
    title: str
    status: str  # "PASSED", "FAILED", "SKIPPED", "ERROR"
    duration_ms: float
    error_message: str | None = None
    stack_trace: str | None = None
    artifacts: list[str] = Field(default_factory=list)


class ExecutionReport(BaseModel):
    run_id: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    results: list[TestResultItem] = Field(default_factory=list)


class FailureContext(BaseModel):
    test_name: str
    error_message: str
    stack_trace: str
    dom_snapshot: str | None = None
    screenshot_path: str | None = None
    network_logs: list[str] = Field(default_factory=list)
    failing_locator: str | None = None


class FailureAnalysis(BaseModel):
    category: str  # e.g., "LOCATOR_CHANGED", "TIMING_ISSUE", "ASSERTION_FAILURE", "ENVIRONMENT"
    root_cause: str
    confidence: float
    suggested_action: str
    healing_possible: bool = False


class AuthoringRequest(BaseModel):
    requirement_title: str
    requirement_description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    target_framework: str = "playwright_python"
    existing_page_objects: list[str] = Field(default_factory=list)


class AuthoringResult(BaseModel):
    suggested_file_path: str
    generated_code: str
    page_objects: list[dict[str, str]] = Field(default_factory=list)
    explanation: str


class HealingRequest(BaseModel):
    old_locator: str
    page_source_or_dom: str
    target_description: str


class HealingResult(BaseModel):
    success: bool
    new_locator: str | None = None
    strategy_used: str | None = None
    confidence: float = 0.0


class ExplorationStep(BaseModel):
    action: str  # "CLICK", "FILL", "NAVIGATE", "ASSERT"
    target: str
    value: str | None = None
    screenshot_path: str | None = None


class ExplorationSession(BaseModel):
    session_id: str
    target_url: str
    steps: list[ExplorationStep] = Field(default_factory=list)
    discovered_elements: list[str] = Field(default_factory=list)


@runtime_checkable
class TestRunner(Protocol):
    """Protocol for executing test suites across frameworks."""

    async def run_tests(self, request: ExecutionRequest) -> ExecutionReport: ...


@runtime_checkable
class FailureAnalyzer(Protocol):
    """Protocol for classifying test failure root causes."""

    async def analyze_failure(self, context: FailureContext) -> FailureAnalysis: ...


@runtime_checkable
class TestAuthor(Protocol):
    """Protocol for generating clean test automation code."""

    async def generate_test(self, request: AuthoringRequest) -> AuthoringResult: ...


@runtime_checkable
class LocatorHealer(Protocol):
    """Protocol for automatically healing broken web locators."""

    async def heal_locator(self, request: HealingRequest) -> HealingResult: ...


@runtime_checkable
class BrowserExplorer(Protocol):
    """Protocol for interactive AI web exploration."""

    async def start_session(self, url: str) -> ExplorationSession: ...


@runtime_checkable
class QAOrchestrator(Protocol):
    """Protocol coordinating authoring, execution, diagnosis, and healing workflows."""

    async def orchestrate_run(self, request: ExecutionRequest) -> tuple[ExecutionReport, list[FailureAnalysis]]: ...
