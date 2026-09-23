from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


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
        """Return the interpreter to run the project with, preferring its own virtualenv."""
        candidates = [
            project_root / ".venv" / "bin" / "python",
            project_root / "venv" / "bin" / "python",
            project_root / ".venv" / "Scripts" / "python.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
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
    default_markers: list[str] = Field(default_factory=list)
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
