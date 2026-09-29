from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def venv_interpreter(environment_dir: Path) -> Path:
    """The Python executable inside a virtualenv, in the layout the host platform creates.

    POSIX virtualenvs put it in ``bin/``; Windows ones use ``Scripts/python.exe``. Every caller that
    builds or probes a provisioned interpreter goes through this so the two layouts are never
    spelled out a second time.
    """
    if os.name == "nt":
        return environment_dir / "Scripts" / "python.exe"
    return environment_dir / "bin" / "python"


class QAProjectFramework(str, Enum):
    """Test framework a QA project is written against."""

    PYTEST = "pytest"
    PYTEST_PLAYWRIGHT = "pytest_playwright"
    PLAYWRIGHT = "playwright"  # node-based; detected but not executable by this platform yet
    UNKNOWN = "unknown"


class PackageManager(str, Enum):
    UV = "uv"
    PIP = "pip"
    POETRY = "poetry"
    PDM = "pdm"
    NONE = "none"


class CaseIdStrategy(str, Enum):
    """How a repository attaches external case identifiers to tests."""

    NONE = "none"
    TESTRAIL_C_PREFIX = "testrail_c_prefix"
    ALLURE_ID = "allure_id"
    MARKER = "marker"
    FILENAME = "filename"
    UNKNOWN = "unknown"


class QARuntimeProfile(BaseModel):
    """Isolated execution runtime for a QA project.

    A QA repository must never execute inside the platform API's own interpreter: it can require a
    different Python version and its own dependency set.
    """

    python_version: str | None = None
    interpreter: str = "python3"
    virtualenv_dir: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)

    def resolve_interpreter(self, project_root: Path) -> str:
        """Return the interpreter to run the project with, preferring its provisioned virtualenv."""
        candidates = [venv_interpreter(project_root / name) for name in (".qa-platform-runtime", ".venv", "venv")]
        if self.virtualenv_dir:
            # A contract that names its own virtualenv outranks the conventional directories.
            candidates.insert(0, venv_interpreter(Path(self.virtualenv_dir)))
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return self._fallback_interpreter()

    def _fallback_interpreter(self) -> str:
        """The interpreter to use when the project has no virtualenv of its own.

        ``python3`` is the POSIX name this model defaults to. On Windows the launcher is
        ``python``, and a name that resolves there may land on the Microsoft Store alias stub
        rather than a real interpreter, so the platform's own interpreter is used instead: it is
        the caller's own environment and always exists.
        """
        if self.interpreter in ("python", "python3") and os.name == "nt":
            return sys.executable
        return self.interpreter


class QAProjectContract(BaseModel):
    """Everything the platform needs to install, collect and run one QA project.

    The contract is either read from `.qa-platform.yaml` in the project or produced by
    :class:`qa_core.onboarding.detector.QAProjectDetector`. Detection never writes to the project:
    a suggested contract is previewed to the operator first.
    """

    framework: QAProjectFramework = QAProjectFramework.UNKNOWN
    package_manager: PackageManager = PackageManager.NONE
    python_version: str | None = None

    install_command: list[str] = Field(default_factory=list)
    collect_command: list[str] = Field(default_factory=list)
    test_command: list[str] = Field(default_factory=list)

    test_roots: list[str] = Field(default_factory=list)
    pages_dir: str | None = None
    flows_dir: str | None = None
    components_dir: str | None = None
    knowledge_dir: str | None = None
    allure_results_dir: str | None = None

    plugins: list[str] = Field(default_factory=list)
    markers: dict[str, str] = Field(default_factory=dict)
    #: Markers that look like a fast subset. Purely a suggestion: they are NOT verified as
    #: offline-safe, and the execution path applies its own safety policy before running anything.
    suggested_markers: list[str] = Field(default_factory=list)
    case_id_strategy: CaseIdStrategy = CaseIdStrategy.NONE

    runtime: QARuntimeProfile = Field(default_factory=QARuntimeProfile)
    environment: dict[str, str] = Field(default_factory=dict)

    #: `file` when the operator supplied `.qa-platform.yaml`, `detected` when inferred.
    source: str = "detected"
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    def command_for_collection(self) -> list[str]:
        return list(self.collect_command)

    def command_for_tests(self, nodeids: list[str] | None = None, markers: list[str] | None = None) -> list[str]:
        """Build a run command for a bounded selection, never the whole regression suite."""
        command = list(self.test_command)
        for marker in markers or []:
            command.extend(["-m", marker])
        if nodeids:
            command.extend(nodeids)
        return command

    def has_plugin(self, name: str) -> bool:
        normalised = name.lower().replace("_", "-")
        return any(plugin.lower().replace("_", "-") == normalised for plugin in self.plugins)


def load_contract_file(path: Path) -> QAProjectContract:
    """Read `.qa-platform.yaml`. Raises FileNotFoundError / ValidationError for the caller to map."""
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw["source"] = "file"
    return QAProjectContract.model_validate(raw)


def render_contract(contract: QAProjectContract) -> str:
    """Render a contract back to YAML, so an operator can preview it before it is ever written."""
    payload = contract.model_dump(mode="json", exclude={"source", "confidence", "warnings"})
    return yaml.safe_dump(payload, sort_keys=False)
