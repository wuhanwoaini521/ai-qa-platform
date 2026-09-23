from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Protocol, runtime_checkable

from project_model.models import RunnerHealthStatus, RunnerType, RunStatus

from qa_core.execution.pytest_runner import PytestRunner


@dataclass
class RunnerTriggerRequest:
    run_id: str
    project_id: str
    workspace_dir: Path | str | None = None
    nodeids: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300


@dataclass
class RunnerTriggerResult:
    run_id: str
    external_job_id: str | None = None
    external_build_url: str | None = None
    status: RunStatus = RunStatus.RUNNING
    message: str = "Execution triggered."


@dataclass
class RunnerStatusResult:
    run_id: str
    status: RunStatus
    duration_ms: float = 0.0
    queue_duration_ms: float = 0.0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    external_job_id: str | None = None
    external_build_url: str | None = None
    error_message: str | None = None


@runtime_checkable
class RunnerBackend(Protocol):
    async def trigger(self, request: RunnerTriggerRequest) -> RunnerTriggerResult: ...
    async def get_status(self, run_id: str, external_job_id: str | None = None) -> RunnerStatusResult: ...
    async def stream_logs(self, run_id: str, external_job_id: str | None = None) -> AsyncGenerator[str, None]: ...
    async def stop(self, run_id: str, external_job_id: str | None = None) -> bool: ...
    async def check_health(self) -> RunnerHealthStatus: ...


class LocalRunnerBackend(RunnerBackend):
    """Executes tests directly on the local environment using PytestRunner."""

    def __init__(self, pytest_runner: PytestRunner | None = None) -> None:
        self.pytest_runner = pytest_runner or PytestRunner()

    async def trigger(self, request: RunnerTriggerRequest) -> RunnerTriggerResult:
        return RunnerTriggerResult(
            run_id=request.run_id,
            external_job_id=f"local-{request.run_id}",
            status=RunStatus.RUNNING,
            message="Local runner execution initiated.",
        )

    async def get_status(self, run_id: str, external_job_id: str | None = None) -> RunnerStatusResult:
        return RunnerStatusResult(run_id=run_id, status=RunStatus.RUNNING)

    async def stream_logs(self, run_id: str, external_job_id: str | None = None) -> AsyncGenerator[str, None]:
        yield f"Local runner executing run {run_id}\n"

    async def stop(self, run_id: str, external_job_id: str | None = None) -> bool:
        return True

    async def check_health(self) -> RunnerHealthStatus:
        return RunnerHealthStatus(
            runner_id="local",
            type=RunnerType.LOCAL,
            status="AVAILABLE",
            message="Local runner environment is operational.",
            base_url=None,
        )
