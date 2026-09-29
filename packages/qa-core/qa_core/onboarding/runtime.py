"""Isolated execution runtime for an imported QA project.

An imported project declares its own Python version and dependencies, so it must never run in the
platform API's interpreter. Provisioning is explicit, bounded and reported: the platform either has
a working interpreter for the project or says exactly why it does not.
"""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.onboarding.collector import run_project_command
from qa_core.onboarding.contract import PackageManager, QAProjectContract, venv_interpreter

#: Directory the platform owns inside an imported workspace. Never the project's own `.venv`.
RUNTIME_DIR_NAME = ".qa-platform-runtime"


class ProvisioningStatus(str, Enum):
    READY = "READY"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class RuntimeProvisioningResult(BaseModel):
    status: ProvisioningStatus
    interpreter: str | None = None
    virtualenv_dir: str | None = None
    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    duration_ms: float = 0.0
    message: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


class QARuntimeProvisioner:
    """Creates a per-project virtualenv and installs its declared dependencies."""

    def __init__(self, timeout_sec: float = 1800.0) -> None:
        self.timeout_sec = timeout_sec

    async def provision(self, project_root: Path, contract: QAProjectContract) -> RuntimeProvisioningResult:
        project_root = project_root.resolve()
        existing = self._existing_interpreter(project_root, contract)
        if existing:
            return RuntimeProvisioningResult(
                status=ProvisioningStatus.READY,
                interpreter=str(existing),
                virtualenv_dir=str(existing.parent.parent),
                message="runtime already provisioned",
            )

        if not contract.install_command:
            return RuntimeProvisioningResult(
                status=ProvisioningStatus.UNSUPPORTED,
                message=(
                    "no package manager detected, so no isolated runtime can be created automatically; "
                    "declare install_command in .qa-platform.yaml"
                ),
            )

        if contract.package_manager is PackageManager.UV:
            return await self._provision_with_uv(project_root, contract)
        return await self._provision_with_venv(project_root, contract)

    def _existing_interpreter(self, project_root: Path, contract: QAProjectContract) -> Path | None:
        candidates = []
        if contract.runtime.virtualenv_dir:
            candidates.append(venv_interpreter(Path(contract.runtime.virtualenv_dir)))
        candidates.append(venv_interpreter(project_root / RUNTIME_DIR_NAME))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    async def _provision_with_uv(self, project_root: Path, contract: QAProjectContract) -> RuntimeProvisioningResult:
        environment_dir = project_root / RUNTIME_DIR_NAME
        command = [*contract.install_command]
        result = await run_project_command(
            command,
            project_root,
            interpreter=sys.executable,
            environment={
                **contract.environment,
                "UV_PROJECT_ENVIRONMENT": str(environment_dir),
                "UV_PYTHON_DOWNLOADS": "automatic",
            },
            timeout_sec=self.timeout_sec,
        )
        interpreter = venv_interpreter(environment_dir)
        return self._result(command, result.exit_code, result.stdout, result.stderr, result.duration_ms, interpreter)

    async def _provision_with_venv(self, project_root: Path, contract: QAProjectContract) -> RuntimeProvisioningResult:
        environment_dir = project_root / RUNTIME_DIR_NAME
        create = await run_project_command(
            ["python", "-m", "venv", str(environment_dir)],
            project_root,
            interpreter=sys.executable,
            environment=contract.environment,
            timeout_sec=self.timeout_sec,
        )
        if create.exit_code != 0:
            return self._result(
                ["python", "-m", "venv", str(environment_dir)],
                create.exit_code,
                create.stdout,
                create.stderr,
                create.duration_ms,
                venv_interpreter(environment_dir),
            )

        interpreter = venv_interpreter(environment_dir)
        install_command = list(contract.install_command)
        if install_command[:3] == ["python", "-m", "pip"]:
            install_command = [str(interpreter), *install_command[1:]]
        install = await run_project_command(
            install_command,
            project_root,
            interpreter=str(interpreter),
            environment=contract.environment,
            timeout_sec=self.timeout_sec,
        )
        return self._result(
            install_command, install.exit_code, install.stdout, install.stderr, install.duration_ms, interpreter
        )

    def _result(
        self,
        command: list[str],
        exit_code: int | None,
        stdout: str,
        stderr: str,
        duration_ms: float,
        interpreter: Path,
    ) -> RuntimeProvisioningResult:
        ready = exit_code == 0 and interpreter.exists()
        return RuntimeProvisioningResult(
            status=ProvisioningStatus.READY if ready else ProvisioningStatus.FAILED,
            interpreter=str(interpreter) if interpreter.exists() else None,
            virtualenv_dir=str(interpreter.parent.parent) if interpreter.exists() else None,
            command=command,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
            message="runtime provisioned" if ready else f"provisioning exited with status {exit_code}",
            stdout_tail="\n".join(stdout.splitlines()[-20:]),
            stderr_tail="\n".join(stderr.splitlines()[-20:]),
        )
