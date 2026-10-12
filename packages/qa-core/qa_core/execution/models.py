from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from project_model.models import FailureSnapshotBundle
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestExecutionStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class SingleTestResult(BaseModel):
    nodeid: str
    status: TestExecutionStatus
    duration_ms: float = 0.0
    error_message: str | None = None
    stack_trace: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)


class FailureSnapshotCapture(BaseModel):
    """Private runner-to-platform transfer; storage state is ciphertext, never plaintext."""

    browser_session_id: str = Field(min_length=1, max_length=36)
    page_id: str = Field(min_length=1, max_length=36)
    worker_id: str = Field(default="main", max_length=100)
    nodeid: str = Field(min_length=1, max_length=500)
    case_name: str = Field(default="", max_length=250)
    bundle: FailureSnapshotBundle
    encrypted_storage_state: str | None = Field(default=None, max_length=5_000_000)


class SuiteExecutionResult(BaseModel):
    #: pytest's process exit code: 0 passed, 1 failures, 2 interrupted, 3 internal error,
    #: 4 usage error, 5 no tests collected. The verdict is derived from it, never guessed.
    exit_code: int | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    results: list[SingleTestResult] = Field(default_factory=list)
    raw_logs: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    failure_snapshots: list[FailureSnapshotCapture] = Field(default_factory=list)


TestSuiteResult = SuiteExecutionResult
