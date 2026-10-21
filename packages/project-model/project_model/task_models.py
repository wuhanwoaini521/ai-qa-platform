from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskType(str, Enum):
    QA_GOAL = "QA_GOAL"
    ANALYZE_REQUIREMENT = "ANALYZE_REQUIREMENT"
    CREATE_TEST = "CREATE_TEST"
    FIX_FAILURE = "FIX_FAILURE"
    OPTIMIZE_TEST = "OPTIMIZE_TEST"
    EXPLORE_PAGE = "EXPLORE_PAGE"
    EXPLORE_PRODUCT = "EXPLORE_PRODUCT"
    ANALYZE_DISCOVERY = "ANALYZE_DISCOVERY"
    RUN_REGRESSION = "RUN_REGRESSION"
    REVIEW_TEST = "REVIEW_TEST"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    RETRYING = "RETRYING"
    REPLANNING = "REPLANNING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class TaskStepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class EvidenceType(str, Enum):
    SOURCE_CODE = "SourceCode"
    SCREENSHOT = "Screenshot"
    PLAYWRIGHT_TRACE = "PlaywrightTrace"
    DOM_SNAPSHOT = "DOMSnapshot"
    ACCESSIBILITY_TREE = "AccessibilityTree"
    CONSOLE_LOG = "ConsoleLog"
    NETWORK_LOG = "NetworkLog"
    PYTEST_TRACEBACK = "PytestTraceback"
    TEST_RESULT = "TestResult"
    LOCATOR_CANDIDATES = "LocatorCandidates"
    GIT_DIFF = "GitDiff"
    RUNTIME_METADATA = "RuntimeMetadata"
    ANALYSIS = "Analysis"


class TaskStepSpec(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    tool: str = Field(min_length=1, max_length=128)
    depends_on: list[str] = Field(default_factory=list)
    when: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=1, ge=0, le=5)
    parallelizable: bool = False


class TaskCreate(BaseModel):
    type: TaskType
    goal: str = Field(min_length=3, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    plan_token: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=30, ge=1, le=100)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_replans: int = Field(default=2, ge=0, le=5)
    max_ai_calls: int = Field(default=8, ge=0, le=50)
    max_duration_seconds: int = Field(default=1800, ge=10, le=86400)


class TaskGoalPreviewStep(BaseModel):
    title: str
    conditional: bool = False
    risk: str = "LOW"


class TaskGoalPreview(BaseModel):
    goal: str
    plan_token: str
    context: str
    steps: list[TaskGoalPreviewStep]
    effects: list[str] = Field(default_factory=list)
    approval_required: bool = False
    constraints: list[str] = Field(default_factory=list)


class TaskStep(BaseModel):
    id: str
    task_id: str
    position: int = 0
    key: str
    name: str
    tool: str
    status: TaskStepStatus = TaskStepStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    condition: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    decision: dict[str, Any] | None = None
    retry_count: int = 0
    max_retries: int = 1
    parallelizable: bool = False
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0


class TaskEvidence(BaseModel):
    id: str
    task_id: str
    step_id: str | None = None
    type: EvidenceType
    source: str
    summary: str = ""
    content: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TaskArtifact(BaseModel):
    id: str
    task_id: str
    step_id: str | None = None
    artifact_id: str
    name: str
    kind: str
    created_at: datetime


class TaskDecision(BaseModel):
    id: str
    task_id: str
    step_id: str | None = None
    name: str
    provider: str
    choice: str
    confidence: float | None = None
    rationale: str = ""
    escalated: bool = False
    created_at: datetime


class TaskEvent(BaseModel):
    id: int
    task_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Task(BaseModel):
    id: str
    type: TaskType
    goal: str
    status: TaskStatus
    project_id: str | None = None
    workspace_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    plan: list[TaskStep] = Field(default_factory=list)
    evidence: list[TaskEvidence] = Field(default_factory=list)
    artifacts: list[TaskArtifact] = Field(default_factory=list)
    decisions: list[TaskDecision] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    replan_count: int = 0
    max_steps: int = 30
    max_retries: int = 3
    max_replans: int = 2
    max_ai_calls: int = 8
    max_duration_seconds: int = 1800
    current_step_id: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class TaskDetail(Task):
    steps: list[TaskStep] = Field(default_factory=list)
    events: list[TaskEvent] = Field(default_factory=list)
    events_truncated: bool = False
    event_cursor: int = 0


class TaskApprovalRequest(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=2000)
