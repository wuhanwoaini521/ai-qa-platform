"""Onboarding and piloting a real QA repository through the platform.

Everything here operates on the *imported copy*: the source repository is read once, never written
to, and never executed in place. The service is the only place that turns a foreign pytest project
into platform records (project, workspace, run, executions, failure records).
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from project_model.models import (
    ProjectCreate,
    TestRun,
    TestRunCreate,
    WorkspaceCreate,
)
from pydantic import BaseModel, Field
from qa_core.onboarding import (
    AllureImportReport,
    AllureResultImporter,
    CollectionOutcome,
    IdentityReport,
    ImportPlan,
    NodeIdCaseMapper,
    QAProjectCollector,
    QAProjectContract,
    QAProjectDetection,
    QAProjectImporter,
    QARuntimeProvisioner,
    RuntimeProvisioningResult,
    SafetyPolicy,
    SafetyVerdict,
    load_contract_file,
    render_contract,
)

from app.repositories.project_repo import ProjectRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.test_run_service import LocalPytestExecutionOptions, TestRunService

CONTRACT_FILENAME = ".qa-platform.yaml"

#: A selection must look like `path/to/test_file.py::test_name[param]`. Anything else (a flag, a
#: shell fragment, a glob) is rejected before it can reach the pytest command line.
NODEID_PATTERN = re.compile(r"^[^\s:=-][^\s:]*\.py::[^\s]+$")
#: Marker expressions are limited to the syntax pytest itself accepts.
MARKER_PATTERN = re.compile(r"^[A-Za-z0-9_\-\s()]+$")


class OnboardingError(RuntimeError):
    """Raised for operator-fixable onboarding problems (bad path, missing runtime, unknown project)."""


def validate_nodeids(nodeids: list[str]) -> list[str]:
    """Reject anything that is not a pytest node id, so a selection can never inject CLI flags.

    node ids and marker expressions are appended to the pytest command line, so they are validated
    here rather than trusted: an operator (or a compromised caller) must not be able to turn a test
    selection into `--pyargs`, `-p`, `-c` or a shell fragment.
    """
    invalid = []
    for nodeid in nodeids:
        candidate = nodeid.strip()
        file_part = PurePosixPath(candidate.split("::")[0])
        # A node id names a workspace-relative POSIX path. A backslash, a drive letter or a leading
        # separator would either escape the workspace or be re-read as a path by a Windows
        # resolver, and a `..` segment would leave the workspace.
        if (
            not NODEID_PATTERN.match(candidate)
            or "\\" in candidate
            or file_part.is_absolute()
            or ".." in file_part.parts
        ):
            invalid.append(nodeid)
    if invalid:
        raise OnboardingError(
            "invalid test selection: "
            + ", ".join(repr(item) for item in invalid[:5])
            + " (expected 'tests/test_file.py::test_name')"
        )
    return [nodeid.strip() for nodeid in nodeids]


def validate_markers(markers: list[str]) -> list[str]:
    invalid = [marker for marker in markers if not MARKER_PATTERN.match(marker.strip())]
    if invalid:
        raise OnboardingError("invalid marker expression: " + ", ".join(repr(item) for item in invalid[:5]))
    return [marker.strip() for marker in markers]


class ImportedProject(BaseModel):
    project_id: str
    workspace_id: str
    project_name: str
    workspace_path: str
    source_path: str
    contract: QAProjectContract
    copied_files: int = 0
    copied_bytes: int = 0
    excluded_dirs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DetectionPreview(BaseModel):
    plan: ImportPlan
    detection: QAProjectDetection


class CollectionReport(BaseModel):
    project_id: str
    outcome: CollectionOutcome
    identity: IdentityReport | None = None


class PilotRunReport(BaseModel):
    project_id: str
    run_id: str | None = None
    run: TestRun | None = None
    executed_nodeids: list[str] = Field(default_factory=list)
    rejected: list[SafetyVerdict] = Field(default_factory=list)
    persisted: bool = False


class OnboardingService:
    """Imports a QA repository into an isolated workspace and pilots it."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        workspace_repo: WorkspaceRepository,
        run_service: TestRunService,
        workspace_base_dir: Path | None = None,
        imports_dir: Path | None = None,
    ) -> None:
        self.project_repo = project_repo
        self.workspace_repo = workspace_repo
        self.run_service = run_service
        self.workspace_base_dir = workspace_base_dir
        self.imports_dir = imports_dir

    # --- detection & import -----------------------------------------------------------------

    async def preview_import(self, source_path: str, project_name: str | None = None) -> DetectionPreview:
        source = Path(source_path).expanduser()
        if not source.is_dir():
            raise OnboardingError(f"Source repository not found: {source}")
        # The preview shows the layout an import would use, so it needs a project id; a stub keeps
        # the preview read-only and the real, id-derived destination is chosen during the import.
        destination = self._workspace_path_for("preview")
        importer = QAProjectImporter()
        plan = importer.plan(source, destination)
        detection = importer.detector.detect(source)
        return DetectionPreview(plan=plan, detection=detection)

    async def import_repository(
        self,
        source_path: str,
        project_name: str | None = None,
        overwrite: bool = False,
    ) -> ImportedProject:
        source = Path(source_path).expanduser()
        if not source.is_dir():
            raise OnboardingError(f"Source repository not found: {source}")
        detection = QAProjectImporter().detector.detect(source)

        name = project_name or source.name
        project = await self.project_repo.create(ProjectCreate(name=name[:115], description=f"Imported from {source}"))
        # A project's workspace lives at `<base>/<project id>` for every project the platform creates.
        # Importing to that path (instead of a readable but different directory) keeps the Studio,
        # the file APIs, git and the runner addressing the same tree the import populated.
        destination = self._workspace_path_for(project.id)

        importer = QAProjectImporter()
        plan = importer.plan(source, destination)
        result = importer.execute(plan, overwrite=overwrite)

        # The contract is materialised inside the workspace so the operator can review and edit it.
        (destination / CONTRACT_FILENAME).write_text(render_contract(result.contract), encoding="utf-8")

        # The imported workspace already contains the project's own files: never scaffold over them.
        workspace = await self.workspace_repo.create(
            WorkspaceCreate(project_id=project.id, branch="main"), path=str(destination)
        )

        return ImportedProject(
            project_id=project.id,
            workspace_id=workspace.id,
            project_name=name,
            workspace_path=str(destination),
            source_path=str(source),
            contract=result.contract,
            copied_files=result.copied_files,
            copied_bytes=result.copied_bytes,
            excluded_dirs=result.excluded_dirs,
            warnings=detection.warnings,
        )

    async def get_imported_project(self, project_id: str) -> ImportedProject:
        workspace = await self.workspace_repo.get_by_project_id(project_id)
        if workspace is None:
            raise OnboardingError(f"No workspace imported for project {project_id}")
        root = Path(workspace.path)
        contract_path = root / CONTRACT_FILENAME
        if contract_path.is_file():
            contract = load_contract_file(contract_path)
        else:
            contract = QAProjectImporter().detector.detect(root).contract
        project = await self.project_repo.get_by_id(project_id)
        return ImportedProject(
            project_id=project_id,
            workspace_id=workspace.id,
            project_name=project.name if project else root.name,
            workspace_path=str(root),
            source_path="",
            contract=contract,
        )

    # --- runtime ----------------------------------------------------------------------------

    async def provision_runtime(self, project_id: str) -> RuntimeProvisioningResult:
        imported = await self.get_imported_project(project_id)
        result = await QARuntimeProvisioner().provision(Path(imported.workspace_path), imported.contract)
        if result.status.value == "READY" and result.virtualenv_dir:
            imported.contract.runtime.virtualenv_dir = result.virtualenv_dir
            (Path(imported.workspace_path) / CONTRACT_FILENAME).write_text(
                render_contract(imported.contract), encoding="utf-8"
            )
        return result

    # --- collection & identity --------------------------------------------------------------

    async def collect(
        self, project_id: str, with_identity: bool = True, markers: list[str] | None = None
    ) -> CollectionReport:
        imported = await self.get_imported_project(project_id)
        outcome = await self._collect(imported, markers=markers)
        identity = None
        if with_identity and outcome.status.value == "COLLECTED":
            mapper = self._identity_mapper(imported.workspace_path)
            identity = mapper.map(Path(imported.workspace_path), outcome.tests)
        return CollectionReport(project_id=project_id, outcome=outcome, identity=identity)

    async def _collect(self, imported: ImportedProject, markers: list[str] | None = None) -> CollectionOutcome:
        return await QAProjectCollector(imported.contract).collect(Path(imported.workspace_path), markers=markers)

    # --- execution --------------------------------------------------------------------------

    async def run_selection(
        self,
        project_id: str,
        nodeids: list[str] | None = None,
        markers: list[str] | None = None,
        allow_unsafe: bool = False,
        persist: bool = True,
        n_workers: int | None = None,
        reruns: int | None = None,
    ) -> PilotRunReport:
        imported = await self.get_imported_project(project_id)
        root = Path(imported.workspace_path)
        if not persist:
            raise OnboardingError("Pilot runs must be persisted through the platform Run service")

        requested = validate_nodeids(list(nodeids or []))
        if markers:
            markers = validate_markers(markers)
            collection = await self._collect(imported, markers=markers)
            if collection.status.value != "COLLECTED":
                raise OnboardingError(
                    f"cannot select tests by marker: the project does not collect cleanly ({collection.error_message})"
                )
            requested.extend(test.nodeid for test in collection.tests)

        if not requested:
            collection = await self._collect(imported)
            if collection.status.value != "COLLECTED":
                raise OnboardingError(f"cannot run the project: test collection failed ({collection.error_message})")
            requested.extend(test.nodeid for test in collection.tests)

        requested = list(dict.fromkeys(requested))

        safe, rejected = SafetyPolicy().split(requested, root) if requested else ([], [])
        if allow_unsafe:
            safe, rejected = requested, []

        if not safe:
            return PilotRunReport(
                project_id=project_id,
                run=None,
                executed_nodeids=[],
                rejected=rejected,
                persisted=False,
            )

        run_args = self._pytest_args_from_contract(imported.contract.test_command)
        if reruns:
            if not imported.contract.has_plugin("rerunfailures"):
                raise OnboardingError("Retry count requires the imported project's pytest-rerunfailures plugin")
            run_args.extend(["--reruns", str(max(0, min(reruns, 5)))])
        if imported.contract.has_plugin("allure") and imported.contract.runtime.virtualenv_dir:
            results_dir = self._workspace_relative_path(root, imported.contract.allure_results_dir or "allure-results")
            run_args.append(f"--alluredir={results_dir}")

        run = await self.run_service.create_and_execute_run(
            TestRunCreate(
                project_id=imported.project_id,
                workspace_id=imported.project_id,
                requested_by="pilot",
                runner_type="LOCAL",
                nodeids=safe,
                parallel_workers=max(1, min(n_workers or 1, 16)),
            ),
            local_pytest_options=LocalPytestExecutionOptions(
                interpreter=imported.contract.runtime.resolve_interpreter(root),
                environment=tuple({**imported.contract.runtime.environment, **imported.contract.environment}.items()),
                extra_pytest_args=tuple(run_args),
                timeout_sec=900.0,
            ),
        )
        return PilotRunReport(
            project_id=project_id,
            run_id=run.id,
            run=run,
            executed_nodeids=safe,
            rejected=rejected,
            persisted=True,
        )

    @staticmethod
    def _pytest_args_from_contract(command: list[str]) -> list[str]:
        """Translate the project's standard pytest command without permitting a second runner."""
        if not command:
            return []

        tokens = list(command)
        executable = Path(tokens[0]).name.lower()
        prefix = 0
        if executable in {"pytest", "pytest.exe"}:
            prefix = 1
        elif executable in {"python", "python3", "python.exe", "python3.exe"} and tokens[1:3] == ["-m", "pytest"]:
            prefix = 3
        elif executable in {"uv", "uv.exe", "poetry", "poetry.exe", "pdm", "pdm.exe", "pipenv", "pipenv.exe"}:
            if tokens[1:3] == ["run", "pytest"]:
                prefix = 3
            elif tokens[1:4] == ["run", "python", "-m"] and tokens[4:5] == ["pytest"]:
                prefix = 5

        if not prefix:
            raise OnboardingError("The imported project's test command must invoke pytest")

        args = tokens[prefix:]
        allowed = {
            "-v",
            "--verbose",
            "-q",
            "--quiet",
            "--tb=short",
            "--tb=long",
            "--strict-markers",
            "--disable-warnings",
        }
        if any(arg not in allowed for arg in args):
            raise OnboardingError("The imported project's pytest command contains unsupported options")
        return args

    @staticmethod
    def _workspace_relative_path(root: Path, value: str) -> Path:
        relative = PurePosixPath(value.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise OnboardingError("The imported project's Allure results path must stay inside its workspace")
        resolved_root = root.resolve()
        resolved = (root / Path(*relative.parts)).resolve()
        if not resolved.is_relative_to(resolved_root):
            raise OnboardingError("The imported project's Allure results path must stay inside its workspace")
        return resolved

    # --- allure -----------------------------------------------------------------------------

    async def import_allure_results(self, project_id: str) -> AllureImportReport:
        imported = await self.get_imported_project(project_id)
        results_dir = self._workspace_relative_path(
            Path(imported.workspace_path), imported.contract.allure_results_dir or "allure-results"
        )
        if not results_dir.is_dir():
            raise OnboardingError(f"No Allure results directory in the imported workspace: {results_dir}")
        return AllureResultImporter().import_from(results_dir)

    # --- helpers ----------------------------------------------------------------------------

    def _workspace_path_for(self, project_id: str) -> Path:
        """Where a project's workspace lives: the same derivation every other component uses."""
        if self.imports_dir:
            return Path(self.imports_dir) / project_id
        return Path(self.workspace_base_dir or Path("runtime/workspaces")) / project_id

    def _identity_mapper(self, workspace_path: str) -> NodeIdCaseMapper:
        return NodeIdCaseMapper(self._explicit_mappings(Path(workspace_path)))

    def _explicit_mappings(self, root: Path) -> dict[str, Any]:
        """Optional `.qa-platform-cases.yaml` next to the contract: nodeid -> case id(s)."""
        path = root / ".qa-platform-cases.yaml"
        if not path.is_file():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mappings = payload.get("mappings", {})
        return mappings if isinstance(mappings, dict) else {}
