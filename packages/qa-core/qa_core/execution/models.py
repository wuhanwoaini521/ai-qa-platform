from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

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


class SuiteExecutionResult(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    results: list[SingleTestResult] = Field(default_factory=list)
    raw_logs: list[str] = Field(default_factory=list)


TestSuiteResult = SuiteExecutionResult
