from __future__ import annotations

from typing import Any, Protocol

from project_model.models import RunnerType, TestRun


class RunnerBackendProtocol(Protocol):
    async def execute(
        self, run: TestRun, workspace_path: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class LocalProcessRunnerBackend:
    """Local native process test runner backend."""

    def __init__(self) -> None:
        self.type = RunnerType.LOCAL

    async def execute(
        self, run: TestRun, workspace_path: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        nodeids = run.nodeids or []
        cmd = ["pytest", "-v"] + nodeids
        return {
            "status": "RUNNING",
            "runner_type": "LOCAL",
            "command": " ".join(cmd),
            "workspace_path": workspace_path,
        }


class DockerRunnerBackend:
    """Docker isolated container execution runner backend."""

    def __init__(self, image: str = "mcr.microsoft.com/playwright/python:v1.49.1-noble") -> None:
        self.image = image
        self.type = RunnerType.DOCKER

    async def execute(
        self, run: TestRun, workspace_path: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # Formulate Docker command with ephemeral volume isolation
        nodeids = run.nodeids or []
        pytest_args = " ".join(nodeids) if nodeids else "."
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace_path}:/workspace",
            "-w",
            "/workspace",
            "-e",
            f"BROWSER={run.browser}",
            self.image,
            "pytest",
            "-v",
            pytest_args,
        ]
        return {
            "status": "QUEUED",
            "runner_type": "DOCKER",
            "container_image": self.image,
            "command": " ".join(docker_cmd),
            "volume_mount": f"{workspace_path}:/workspace",
        }


class DistributedWorkerBackend:
    """Distributed cluster worker execution backend."""

    def __init__(self) -> None:
        self.type = RunnerType.LOCAL

    async def execute(
        self, run: TestRun, workspace_path: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "status": "QUEUED",
            "runner_type": "WORKER",
            "run_id": run.id,
            "browser": run.browser,
            "total_nodeids": len(run.nodeids or []),
        }
