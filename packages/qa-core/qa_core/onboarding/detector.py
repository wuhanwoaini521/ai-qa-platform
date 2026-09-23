from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from qa_core.onboarding.contract import (
    CaseIdStrategy,
    PackageManager,
    QAProjectContract,
    QAProjectFramework,
)

#: Directories the platform understands as page objects, flows, components and knowledge.
PAGES_DIRS = ("pages", "page_objects", "pageobjects")
FLOWS_DIRS = ("flows", "steps")
COMPONENTS_DIRS = ("components", "locators")
KNOWLEDGE_DIRS = ("knowledge", "domain", "data")
ALLURE_DIRS = ("allure-results", "allure_results", "allure-report")

CONFIG_FILES = ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "conftest.py")
LOCK_FILES = {
    "uv.lock": PackageManager.UV,
    "poetry.lock": PackageManager.POETRY,
    "pdm.lock": PackageManager.PDM,
    "requirements.txt": PackageManager.PIP,
}

#: Plugins the platform can act on, matched against declared dependencies.
PLUGIN_DEPENDENCIES = {
    "pytest-xdist": "xdist",
    "pytest-rerunfailures": "rerunfailures",
    "allure-pytest": "allure",
    "pytest-playwright": "playwright",
    "pytest-html": "html",
    "pytest-timeout": "timeout",
    "pytest-base-url": "base_url",
    "pytest-order": "order",
    "pytest-metadata": "metadata",
    "playwright": "playwright_runtime",
}

TESTRAIL_CASE_ID = re.compile(r"\bC\d{3,7}\b")
ALLURE_ID_DECORATOR = re.compile(r"allure\.(?:id|testcase)\s*\(", re.IGNORECASE)
MARKER_CASE_ID = re.compile(r"(?:pytest\.mark|@pytest\.mark)\.(?:tc|case|case_id|testrail)\b", re.IGNORECASE)


class DetectionEvidence(BaseModel):
    """One observed fact and where it was found, so a preview can be audited."""

    detail: str
    location: str


class QAProjectDetection(BaseModel):
    """Outcome of inspecting a project root."""

    root: str
    contract: QAProjectContract
    evidence: list[DetectionEvidence] = Field(default_factory=list)
    test_file_count: int = 0
    warnings: list[str] = Field(default_factory=list)


@dataclass
class _EvidenceCollector:
    items: list[DetectionEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, detail: str, location: Path | str) -> None:
        self.items.append(DetectionEvidence(detail=detail, location=str(location)))

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


class QAProjectDetector:
    """Inspects a QA repository and proposes a :class:`QAProjectContract`.

    Read-only by design: nothing is installed, executed or written. The caller previews the
    proposal and decides whether to persist a `.qa-platform.yaml` into its own copy.
    """

    def detect(self, root: Path | str) -> QAProjectDetection:
        project_root = Path(root).expanduser().resolve()
        if not project_root.is_dir():
            raise NotADirectoryError(f"Not a directory: {project_root}")

        collector = _EvidenceCollector()
        declared = self._declared_dependencies(project_root, collector)
        pytest_options = self._pytest_options(project_root, collector)

        framework = self._framework(project_root, declared)
        collector.add(f"framework resolved as {framework.value}", project_root)

        package_manager = self._package_manager(project_root, collector)
        test_roots = self._test_roots(project_root, pytest_options, collector)
        test_files = self._test_files(project_root, test_roots)
        plugins = sorted({PLUGIN_DEPENDENCIES[dep] for dep in declared if dep in PLUGIN_DEPENDENCIES})
        plugins.extend(self._addopts_plugins(pytest_options))

        warnings = list(collector.warnings)
        if not test_files:
            warnings.append("no test files found: the contract cannot be verified until tests are present")
        if framework is QAProjectFramework.UNKNOWN:
            warnings.append("framework not recognised: PyYAML contract will need explicit overrides")

        contract = QAProjectContract(
            framework=framework,
            package_manager=package_manager,
            python_version=self._python_version(project_root, declared),
            install_command=self._install_command(package_manager),
            collect_command=["python", "-m", "pytest", "--collect-only", "-q"],
            test_command=["python", "-m", "pytest", "-v", "--tb=short"],
            test_roots=test_roots,
            pages_dir=self._first_existing(project_root, PAGES_DIRS),
            flows_dir=self._first_existing(project_root, FLOWS_DIRS),
            components_dir=self._first_existing(project_root, COMPONENTS_DIRS),
            knowledge_dir=self._first_existing(project_root, KNOWLEDGE_DIRS),
            allure_results_dir=self._first_existing(project_root, ALLURE_DIRS),
            plugins=sorted(set(plugins)),
            markers=pytest_options.markers,
            suggested_markers=self._suggested_markers(pytest_options),
            case_id_strategy=self._case_id_strategy(project_root, test_files, collector),
            environment=self._default_environment(project_root, pytest_options),
            source="detected",
            confidence=self._confidence(framework, test_files, package_manager),
            warnings=warnings,
        )
        return QAProjectDetection(
            root=str(project_root),
            contract=contract,
            evidence=collector.items,
            test_file_count=len(test_files),
            warnings=warnings,
        )

    # --- configuration sources -------------------------------------------------------------

    def _pyproject(self, project_root: Path) -> dict:
        path = project_root / "pyproject.toml"
        if not path.exists():
            return {}
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            return {}

    def _declared_dependencies(self, project_root: Path, collector: _EvidenceCollector) -> set[str]:
        dependencies: set[str] = set()
        pyproject = self._pyproject(project_root)
        for section in ("dependencies",):
            for entry in pyproject.get("project", {}).get(section, []) or []:
                dependencies.add(_normalise_dependency(entry))
        poetry_deps = pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
        for name in poetry_deps:
            dependencies.add(name.lower())
        dependency_groups = pyproject.get("dependency-groups", {}) or {}
        for entries in dependency_groups.values():
            for entry in entries or []:
                if isinstance(entry, str):
                    dependencies.add(_normalise_dependency(entry))

        requirements = project_root / "requirements.txt"
        if requirements.exists():
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    dependencies.add(_normalise_dependency(stripped))
            collector.add("declared dependencies in requirements.txt", requirements)
        if dependencies:
            collector.add(f"declared dependencies: {', '.join(sorted(dependencies))}", project_root / "pyproject.toml")
        return dependencies

    def _pytest_options(self, project_root: Path, collector: _EvidenceCollector) -> _PytestOptions:
        options = _PytestOptions()

        pyproject = self._pyproject(project_root)
        ini = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}) or {}
        if ini:
            options.merge(ini)
            collector.add("pytest configuration in pyproject.toml", project_root / "pyproject.toml")

        pytest_ini = project_root / "pytest.ini"
        if pytest_ini.exists():
            sections = _parse_ini_sections(pytest_ini.read_text(encoding="utf-8", errors="replace"))
            options.merge(sections.get("pytest", {}))
            collector.add("pytest configuration in pytest.ini", pytest_ini)

        setup_cfg = project_root / "setup.cfg"
        if setup_cfg.exists():
            sections = _parse_ini_sections(setup_cfg.read_text(encoding="utf-8", errors="replace"))
            if "tool:pytest" in sections:
                options.merge(sections["tool:pytest"])
                collector.add("pytest configuration in setup.cfg [tool:pytest]", setup_cfg)

        tox_ini = project_root / "tox.ini"
        if tox_ini.exists():
            sections = _parse_ini_sections(tox_ini.read_text(encoding="utf-8", errors="replace"))
            if "pytest" in sections:
                options.merge(sections["pytest"])
                collector.add("pytest configuration in tox.ini [pytest]", tox_ini)

        for name in ("conftest.py", "tests/conftest.py"):
            conftest = project_root / name
            if conftest.exists():
                collector.add("fixtures/plugins defined in conftest", conftest)
        return options

    # --- individual signals ----------------------------------------------------------------

    def _framework(self, project_root: Path, declared: set[str]) -> QAProjectFramework:
        if (project_root / "playwright.config.ts").exists() or (project_root / "playwright.config.js").exists():
            return QAProjectFramework.PLAYWRIGHT
        has_pytest = "pytest" in declared or any((project_root / name).exists() for name in CONFIG_FILES)
        has_playwright = "playwright" in declared or "pytest-playwright" in declared
        if has_pytest and has_playwright:
            return QAProjectFramework.PYTEST_PLAYWRIGHT
        if has_pytest:
            return QAProjectFramework.PYTEST
        if has_playwright:
            return QAProjectFramework.PLAYWRIGHT
        return QAProjectFramework.UNKNOWN

    def _package_manager(self, project_root: Path, collector: _EvidenceCollector) -> PackageManager:
        for filename, manager in LOCK_FILES.items():
            if (project_root / filename).exists():
                collector.add(f"package manager {manager.value} (found {filename})", project_root / filename)
                return manager
        for filename, manager in (("Pipfile", PackageManager.PIP), ("setup.py", PackageManager.PIP)):
            if (project_root / filename).exists():
                collector.add(f"package manager {manager.value} (found {filename})", project_root / filename)
                return manager
        return PackageManager.NONE

    def _python_version(self, project_root: Path, declared: set[str]) -> str | None:
        requires = self._pyproject(project_root).get("project", {}).get("requires-python")
        if isinstance(requires, str):
            return requires
        runtime = project_root / ".python-version"
        if runtime.exists():
            return runtime.read_text(encoding="utf-8").strip()
        return None

    def _test_roots(self, project_root: Path, options: _PytestOptions, collector: _EvidenceCollector) -> list[str]:
        if options.testpaths:
            roots = [path for path in options.testpaths if (project_root / path).exists()]
            if roots:
                collector.add(f"test roots from pytest configuration: {', '.join(roots)}", project_root)
                return roots
        discovered = [name for name in ("tests", "test", "e2e", "specs") if (project_root / name).is_dir()]
        if discovered:
            collector.add(f"test roots discovered: {', '.join(discovered)}", project_root)
        return discovered

    def _test_files(self, project_root: Path, test_roots: list[str]) -> list[Path]:
        files: list[Path] = []
        roots = test_roots or ["."]
        for root_name in roots:
            base = project_root / root_name
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("test_*.py")) + sorted(base.rglob("*_test.py")):
                if "__pycache__" not in path.parts:
                    files.append(path)
        return files

    def _addopts_plugins(self, options: _PytestOptions) -> list[str]:
        addopts = options.addopts
        plugins = []
        if re.search(r"(^|\s)-n[\s=]", addopts):
            plugins.append("xdist")
        if "--reruns" in addopts:
            plugins.append("rerunfailures")
        if "--alluredir" in addopts:
            plugins.append("allure")
        return plugins

    def _suggested_markers(self, options: _PytestOptions) -> list[str]:
        """Markers that look like a fast subset, in declaration order.

        This is only a suggestion for the operator: a marker name says nothing about whether the
        tests behind it are offline-safe (in the reference repository the `smoke` marker selects
        tests that drive a live website). Execution always re-checks each selected test.
        """
        preferred = ("smoke", "sanity", "critical", "p0")
        return [marker for marker in preferred if marker in options.markers]

    def _default_environment(self, project_root: Path, options: _PytestOptions) -> dict[str, str]:
        environment: dict[str, str] = {}
        if options.base_url:
            environment["BASE_URL"] = options.base_url
        if options.allure_results_dir:
            environment["ALLURE_RESULTS_DIR"] = options.allure_results_dir
        elif (project_root / "allure-results").is_dir():
            environment["ALLURE_RESULTS_DIR"] = "allure-results"
        return environment

    def _case_id_strategy(
        self, project_root: Path, test_files: list[Path], collector: _EvidenceCollector
    ) -> CaseIdStrategy:
        testrail_hits = 0
        allure_hits = 0
        marker_hits = 0
        for path in test_files[:200]:
            content = path.read_text(encoding="utf-8", errors="replace")
            if TESTRAIL_CASE_ID.search(content):
                testrail_hits += 1
            if ALLURE_ID_DECORATOR.search(content):
                allure_hits += 1
            if MARKER_CASE_ID.search(content):
                marker_hits += 1
        if testrail_hits:
            collector.add(f"{testrail_hits} test files reference TestRail-style C-ids", project_root)
            return CaseIdStrategy.TESTRAIL_C_PREFIX
        if allure_hits:
            collector.add(f"{allure_hits} test files use allure.id decorators", project_root)
            return CaseIdStrategy.ALLURE_ID
        if marker_hits:
            collector.add(f"{marker_hits} test files use case-id markers", project_root)
            return CaseIdStrategy.MARKER
        if test_files:
            return CaseIdStrategy.UNKNOWN
        return CaseIdStrategy.NONE

    def _install_command(self, package_manager: PackageManager) -> list[str]:
        if package_manager is PackageManager.UV:
            return ["uv", "sync"]
        if package_manager is PackageManager.POETRY:
            return ["poetry", "install"]
        if package_manager is PackageManager.PDM:
            return ["pdm", "install"]
        if package_manager is PackageManager.PIP:
            return ["python", "-m", "pip", "install", "-r", "requirements.txt"]
        return []

    def _first_existing(self, project_root: Path, names: tuple[str, ...]) -> str | None:
        for name in names:
            if (project_root / name).is_dir():
                return name
        return None

    def _confidence(self, framework: QAProjectFramework, test_files: list[Path], manager: PackageManager) -> float:
        score = 0.0
        if framework is not QAProjectFramework.UNKNOWN:
            score += 0.5
        if test_files:
            score += 0.3
        if manager is not PackageManager.NONE:
            score += 0.2
        return round(score, 2)


@dataclass
class _PytestOptions:
    testpaths: list[str] = field(default_factory=list)
    markers: dict[str, str] = field(default_factory=dict)
    addopts: str = ""
    base_url: str | None = None
    allure_results_dir: str | None = None

    def merge(self, section: dict) -> None:
        testpaths = section.get("testpaths")
        if isinstance(testpaths, str):
            self.testpaths = [part for part in testpaths.replace(",", " ").split() if part]
        elif isinstance(testpaths, list):
            self.testpaths = [str(part) for part in testpaths]

        markers = section.get("markers")
        if isinstance(markers, list):
            for entry in markers:
                name, _, description = str(entry).partition(":")
                self.markers[name.strip()] = description.strip()
        elif isinstance(markers, str):
            for line in markers.splitlines():
                name, _, description = line.partition(":")
                if name.strip():
                    self.markers[name.strip()] = description.strip()

        addopts = section.get("addopts")
        if isinstance(addopts, str):
            self.addopts = f"{self.addopts} {addopts}".strip()
            base_url = re.search(r"--base-url[=\s]+(\S+)", addopts)
            if base_url:
                self.base_url = base_url.group(1)
            allure_dir = re.search(r"--alluredir[=\s]+(\S+)", addopts)
            if allure_dir:
                self.allure_results_dir = allure_dir.group(1)


def _normalise_dependency(entry: str) -> str:
    name = re.split(r"[<>=!~\[; ]", entry.strip(), maxsplit=1)[0]
    return name.strip().lower().replace("_", "-")


def _parse_ini_sections(content: str) -> dict[str, dict[str, str]]:
    """Minimal INI reader: enough for `[tool:pytest]` / `[pytest]` sections, including
    indented continuation lines (which is how pytest markers are declared)."""
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    last_key: str | None = None
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = {}
            sections[stripped[1:-1].strip()] = current
            last_key = None
            continue
        if current is None:
            continue
        if raw_line[0].isspace() and last_key is not None:
            current[last_key] = f"{current[last_key]}\n{stripped}"
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
        elif ":" in stripped:
            key, _, value = stripped.partition(":")
        else:
            continue
        last_key = key.strip()
        current[last_key] = value.strip()
    return sections
