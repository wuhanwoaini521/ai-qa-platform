from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FailureCategory(str, Enum):
    LOCATOR_CHANGED = "LOCATOR_CHANGED"
    TIMING_ISSUE = "TIMING_ISSUE"
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    PAGE_CRASH = "PAGE_CRASH"
    TEST_DATA_ERROR = "TEST_DATA_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    CODE_ERROR = "CODE_ERROR"
    UNKNOWN = "UNKNOWN"


class ExecutionIncident(BaseModel):
    """Structured, replayable failure at a QA execution boundary."""

    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    browser_session_id: str | None = Field(default=None, max_length=128)
    category: FailureCategory = FailureCategory.UNKNOWN
    code: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)
    candidate_id: str | None = Field(default=None, max_length=48)
    error_type: str | None = Field(default=None, max_length=128)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    recovery_attempt: int = Field(default=0, ge=0, le=1000)
    recovery_limit: int = Field(default=0, ge=0, le=1000)
    status: Literal["OPEN", "RECOVERING", "RECOVERED", "UNRESOLVED"] = "OPEN"
    evidence_artifact_id: str | None = Field(default=None, max_length=128)


class FailureArtifact(BaseModel):
    test_id: str
    nodeid: str
    exception_type: str
    error_message: str
    stack_trace: str
    url: str | None = None
    screenshot_path: str | None = None
    trace_path: str | None = None
    dom_snapshot_path: str | None = None
    console_logs: list[str] = Field(default_factory=list)
    network_logs: list[str] = Field(default_factory=list)
    failing_locator: str | None = None
    classification: FailureCategory = FailureCategory.UNKNOWN
    suggested_action: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
