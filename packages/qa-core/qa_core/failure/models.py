from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

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
