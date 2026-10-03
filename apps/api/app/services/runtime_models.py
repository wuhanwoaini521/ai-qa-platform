"""Public read models for Runtime; deliberately independent of persistence models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeSpan(BaseModel):
    id: str
    kind: str
    title: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    task_id: str | None = None
    test_run_id: str | None = None
    step_id: str | None = None
    timestamp_source: str | None = None


class RuntimeStep(RuntimeSpan):
    key: str
    tool: str
    dependencies: list[str] = Field(default_factory=list)
    retry_count: int = 0
    inputs_summary: str = ""
    outputs_summary: str = ""
    error: str | None = None


class RuntimeTask(RuntimeSpan):
    type: str
    current_step_id: str | None = None
    retry_count: int = 0


class RuntimeRun(RuntimeSpan):
    relationship_source: Literal["standalone", "legacy_context", "foreign_key"] = "standalone"
    parent_run_id: str | None = None
    origin_failure_id: str | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


class RuntimeDecision(BaseModel):
    id: str
    step_id: str | None = None
    name: str
    provider: str
    selected: str
    confidence: float | None = None
    created_at: datetime | None = None


class RuntimeEvidence(BaseModel):
    id: str
    step_id: str | None = None
    type: str
    source: str
    summary: str
    artifact_id: str | None = None
    created_at: datetime | None = None


class RuntimeArtifact(BaseModel):
    id: str
    artifact_id: str | None = None
    name: str
    type: str
    source: str
    step_id: str | None = None
    test_run_id: str | None = None
    case_id: str | None = None
    created_at: datetime | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    url: str | None = None


class RuntimeBrowser(RuntimeSpan):
    browser_session_id: str
    current_url: str
    case_execution_id: str | None = None


class RuntimeFailure(BaseModel):
    id: str
    test_run_id: str
    execution_id: str
    title: str
    classification: str
    message: str
    created_at: datetime | None = None


class RuntimeSummary(BaseModel):
    completed_steps: int = 0
    total_steps: int = 0
    active_step_ids: list[str] = Field(default_factory=list)
    next_step_ids: list[str] = Field(default_factory=list)
    failures: int = 0
    retries: int = 0
    ai_calls: int | None = None
    artifacts: int = 0
    approval: bool = False


class NormalizedRuntimeEvent(BaseModel):
    id: str
    source: str
    source_id: str
    runtime_id: str
    task_id: str | None = None
    test_run_id: str | None = None
    trace_run_id: str | None = None
    step_id: str | None = None
    timestamp: datetime | None = None
    type: str
    category: Literal["lifecycle", "step", "test", "ai", "decision", "browser", "failure", "artifact", "system"]
    status: str | None = None
    title: str
    summary: str = ""
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeSnapshot(BaseModel):
    id: str
    kind: Literal["task", "run"]
    status: str
    title: str
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    task: RuntimeTask | None = None
    steps: list[RuntimeStep] = Field(default_factory=list)
    runs: list[RuntimeRun] = Field(default_factory=list)
    run_ancestors: list[RuntimeRun] = Field(default_factory=list)
    executions: list[RuntimeSpan] = Field(default_factory=list)
    ai_invocations: list[RuntimeSpan] = Field(default_factory=list)
    decisions: list[RuntimeDecision] = Field(default_factory=list)
    evidence: list[RuntimeEvidence] = Field(default_factory=list)
    browser_sessions: list[RuntimeBrowser] = Field(default_factory=list)
    failures: list[RuntimeFailure] = Field(default_factory=list)
    artifacts: list[RuntimeArtifact] = Field(default_factory=list)
    summary: RuntimeSummary = Field(default_factory=RuntimeSummary)
    events: list[NormalizedRuntimeEvent] = Field(default_factory=list)
    event_cursor: int = 0
    events_truncated: bool = False


class RuntimeStepDetail(BaseModel):
    id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
