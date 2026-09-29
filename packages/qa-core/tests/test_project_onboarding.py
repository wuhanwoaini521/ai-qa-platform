"""QA project onboarding: detection fidelity and contract behaviour on realistic repository shapes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from qa_core.onboarding import (
    CaseIdStrategy,
    PackageManager,
    QAProjectContract,
    QAProjectDetector,
    QAProjectFramework,
    QARuntimeProfile,
    load_contract_file,
    render_contract,
    venv_interpreter,
)

pytestmark = pytest.mark.unit


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def playwright_project(root: Path) -> Path:
    write(
        root / "pyproject.toml",
        """
[project]
name = "reference-qa"
requires-python = ">=3.11"
dependencies = [
    "pytest>=8.0",
    "pytest-playwright>=0.5",
    "pytest-xdist>=3.5",
    "pytest-rerunfailures>=14.0",
    "allure-pytest>=2.13",
    "playwright>=1.45",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-n 2 --reruns 1 --alluredir=allure-results --base-url=https://qa.example.com"
markers = [
    "smoke: fast subset",
    "regression: full regression",
    "p0: critical",
]
""".lstrip(),
    )
    write(root / "uv.lock", "")
    write(root / "conftest.py", "import pytest\n")
    write(root / "tests" / "conftest.py", "import pytest\n")
    write(
        root / "tests" / "test_login.py",
        "import pytest\n\n@pytest.mark.smoke\ndef test_login_flow():\n    assert True\n\n"
        "# TestRail C12345 / C67890 covered by this flow\ndef test_login_invalid():\n    assert True\n",
    )
    write(root / "tests" / "test_checkout.py", "def test_checkout_flow():\n    assert True\n")
    write(root / "pages" / "login_page.py", "class LoginPage:\n    pass\n")
    write(root / "flows" / "login_flow.py", "def login():\n    pass\n")
    write(root / "knowledge" / "domain.md", "# domain\n")
    (root / "allure-results").mkdir(parents=True, exist_ok=True)
    return root


def test_detects_a_realistic_pytest_playwright_project(tmp_path: Path):
    detection = QAProjectDetector().detect(playwright_project(tmp_path))
    contract = detection.contract

    assert contract.framework is QAProjectFramework.PYTEST_PLAYWRIGHT
    assert contract.package_manager is PackageManager.UV
    assert contract.python_version == ">=3.11"
    assert contract.test_roots == ["tests"]
    assert contract.pages_dir == "pages"
    assert contract.flows_dir == "flows"
    assert contract.allure_results_dir == "allure-results"
    assert contract.case_id_strategy is CaseIdStrategy.TESTRAIL_C_PREFIX
    assert detection.test_file_count == 2
    assert contract.confidence >= 0.9

    # Plugins come from declared dependencies and from addopts, deduplicated.
    assert {"xdist", "rerunfailures", "allure", "playwright"} <= set(contract.plugins)
    assert contract.markers["smoke"] == "fast subset"
    assert contract.suggested_markers == ["smoke", "p0"]
    assert contract.environment["BASE_URL"] == "https://qa.example.com"
    assert contract.environment["ALLURE_RESULTS_DIR"] == "allure-results"

    # Detection is evidence-backed and never writes to the project.
    assert detection.evidence
    assert all(item.location for item in detection.evidence)
    assert not (tmp_path / ".qa-platform.yaml").exists()


def test_detects_project_without_declared_dependencies(tmp_path: Path):
    write(tmp_path / "requirements.txt", "pytest==8.2.0\nrequests\n")
    write(tmp_path / "pytest.ini", "[pytest]\ntestpaths = tests\nmarkers =\n    smoke: fast\n")
    write(tmp_path / "tests" / "test_api.py", "def test_api():\n    assert True\n")

    detection = QAProjectDetector().detect(tmp_path)
    contract = detection.contract

    assert contract.framework is QAProjectFramework.PYTEST
    assert contract.package_manager is PackageManager.PIP
    assert contract.install_command == ["python", "-m", "pip", "install", "-r", "requirements.txt"]
    assert contract.test_roots == ["tests"]
    assert contract.markers == {"smoke": "fast"}
    assert contract.case_id_strategy is CaseIdStrategy.UNKNOWN
    assert "no test files found" not in detection.warnings


def test_reports_unknown_framework_with_a_warning_instead_of_guessing(tmp_path: Path):
    write(tmp_path / "README.md", "# not a QA project\n")

    detection = QAProjectDetector().detect(tmp_path)

    assert detection.contract.framework is QAProjectFramework.UNKNOWN
    assert detection.contract.package_manager is PackageManager.NONE
    assert detection.contract.confidence < 0.5
    assert any("framework not recognised" in warning for warning in detection.warnings)
    assert any("no test files found" in warning for warning in detection.warnings)
    assert detection.test_file_count == 0


def test_detects_node_playwright_project_without_claiming_pytest_support(tmp_path: Path):
    write(tmp_path / "playwright.config.ts", "export default {}\n")

    detection = QAProjectDetector().detect(tmp_path)

    assert detection.contract.framework is QAProjectFramework.PLAYWRIGHT


def test_a_declared_contract_file_takes_precedence(tmp_path: Path):
    write(
        tmp_path / ".qa-platform.yaml",
        """
framework: pytest
package_manager: uv
install_command: ["uv", "sync", "--frozen"]
collect_command: ["python", "-m", "pytest", "--collect-only", "-q"]
test_command: ["python", "-m", "pytest", "-v"]
test_roots: ["qa"]
suggested_markers: ["smoke"]
""".lstrip(),
    )
    contract = load_contract_file(tmp_path / ".qa-platform.yaml")

    assert contract.source == "file"
    assert contract.test_roots == ["qa"]
    assert contract.install_command == ["uv", "sync", "--frozen"]


def test_run_command_stays_bounded_to_the_requested_selection():
    contract = QAProjectContract(
        test_command=["python", "-m", "pytest", "-v"],
        test_roots=["tests"],
    )

    assert contract.command_for_tests() == ["python", "-m", "pytest", "-v"]
    assert contract.command_for_tests(nodeids=["tests/test_a.py::test_a"]) == [
        "python",
        "-m",
        "pytest",
        "-v",
        "tests/test_a.py::test_a",
    ]
    assert contract.command_for_tests(markers=["smoke"]) == ["python", "-m", "pytest", "-v", "-m", "smoke"]


def test_rendered_contract_is_a_valid_round_trip_and_hides_detection_metadata(tmp_path: Path):
    detection = QAProjectDetector().detect(playwright_project(tmp_path))
    rendered = render_contract(detection.contract)

    assert "confidence" not in rendered
    assert "warnings" not in rendered
    reloaded = load_contract_file(_write_yaml(tmp_path, rendered))
    assert reloaded.test_roots == detection.contract.test_roots
    assert reloaded.markers == detection.contract.markers
    assert reloaded.framework is detection.contract.framework


def test_runtime_profile_prefers_the_project_virtualenv(tmp_path: Path):
    """The resolved interpreter must be the one this platform's virtualenv layout actually creates."""
    contract = QAProjectContract()
    no_venv = contract.runtime.resolve_interpreter(tmp_path)
    # The default is a bare command name; on Windows it must not stay a name that cannot be spawned.
    assert Path(no_venv).name.lower().startswith(("python", "python3"))
    if os.name == "nt":
        assert no_venv == sys.executable

    venv_python = venv_interpreter(tmp_path / ".venv")
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")

    assert contract.runtime.resolve_interpreter(tmp_path) == str(venv_python)


def test_runtime_profile_prefers_a_contract_declared_virtualenv_over_conventional_ones(tmp_path: Path):
    declared = venv_interpreter(tmp_path / "custom-env")
    declared.parent.mkdir(parents=True, exist_ok=True)
    declared.write_text("", encoding="utf-8")
    conventional = venv_interpreter(tmp_path / ".venv")
    conventional.parent.mkdir(parents=True, exist_ok=True)
    conventional.write_text("", encoding="utf-8")

    contract = QAProjectContract(runtime=QARuntimeProfile(virtualenv_dir=str(tmp_path / "custom-env")))

    assert contract.runtime.resolve_interpreter(tmp_path) == str(declared)


def _write_yaml(root: Path, content: str) -> Path:
    path = root / "roundtrip.yaml"
    path.write_text(content, encoding="utf-8")
    return path
