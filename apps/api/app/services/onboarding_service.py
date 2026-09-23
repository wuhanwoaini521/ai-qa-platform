"""Onboarding and piloting a real QA repository through the platform.

Everything here operates on the *imported copy*: the source repository is read once, never written
to, and never executed in place. The service is the only place that turns a foreign pytest project
into platform records (project, workspace, run, executions, failure records).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from project_model.models import (
    ProjectCreate,
    RunStatus,
    TestRunCreate,
    WorkspaceCreate,
)
from pydantic import BaseModel, Field
from qa_core.failure.classifier import FailureClassifier
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
    QAProjectRunner,
    QARuntimeProvisioner,
    RuntimeProvisioningResult,
    SafetyPolicy,
    SafetyVerdict,
    SuiteRunOutcome,
    load_contract_file,
    render_contract,
)

from app.repositories.project_repo import ProjectRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository

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
    invalid = [
        nodeid
        for nodeid in nodeids
        # An absolute path would let the selection point at a host file instead of the workspace.
        if not NODEID_PATTERN.match(nodeid.strip())
        or nodeid.strip().startswith("/")
        or ".." in nodeid.split("::")[0].split("/")
    ]
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
    outcome: SuiteRunOutcome
    executed_nodeids: list[str] = Field(default_factory=list)
    rejected: list[SafetyVerdict] = Field(default_factory=list)
    persisted: bool = False


class OnboardingService:
    """Imports a QA repository into an isolated workspace and pilots it."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        workspace_repo: WorkspaceRepository,
        run_repo: TestRunRepository,
        workspace_base_dir: Path | None = None,
        imports_dir: Path | None = None,
    ) -> None:
        self.project_repo = project_repo
        self.workspace_repo = workspace_repo
        self.run_repo = run_repo
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

        requested = validate_nodeids(list(nodeids or []))
        if markers:
            markers = validate_markers(markers)
            collection = await self._collect(imported, markers=markers)
            if collection.status.value != "COLLECTED":
                raise OnboardingError(
                    f"cannot select tests by marker: the project does not collect cleanly ({collection.error_message})"
                )
            requested.extend(test.nodeid for test in collection.tests)

        safe, rejected = SafetyPolicy().split(requested, root) if requested else ([], [])
        if allow_unsafe:
            safe, rejected = requested, []

        if requested and not safe:
            return PilotRunReport(
                project_id=project_id,
                outcome=SuiteRunOutcome(exit_code=None, command=[], timed_out=False),
                executed_nodeids=[],
                rejected=rejected,
                persisted=False,
            )

        # When the project reports through Allure *and* its own runtime was provisioned (so the
        # plugin is guaranteed to be importable), the platform owns the results directory: the run's
        # artifacts land inside the isolated workspace and can be imported afterwards. Without a
        # provisioned runtime the ambient interpreter is used and no project plugin may be assumed.
        run_args: list[str] = []
        if n_workers:
            run_args.extend(["-n", str(max(1, min(n_workers, 32)))])
        if reruns:
            run_args.extend(["--reruns", str(max(0, min(reruns, 5)))])
        if imported.contract.has_plugin("allure") and imported.contract.runtime.virtualenv_dir:
            results_dir = root / (imported.contract.allure_results_dir or "allure-results")
            run_args.append(f"--alluredir={results_dir}")

        outcome = await QAProjectRunner(
            imported.contract,
            artifacts_dir=self._report_artifacts_dir(imported.project_id),
        ).run(root, nodeids=safe or None, extra_args=run_args)

        run_id: str | None = None
        if persist:
            run_id = await self._persist_run(imported, outcome, safe or requested)
        return PilotRunReport(
            project_id=project_id,
            run_id=run_id,
            outcome=outcome,
            executed_nodeids=safe,
            rejected=rejected,
            persisted=persist,
        )

    async def _persist_run(self, imported: ImportedProject, outcome: SuiteRunOutcome, executed: list[str]) -> str:
        run = await self.run_repo.create_run(
            TestRunCreate(
                project_id=imported.project_id,
                workspace_id=imported.workspace_id,
                requested_by="pilot",
                runner_type="IMPORTED_PYTEST",
                nodeids=executed,
            )
        )
        status = RunStatus.PASSED if outcome.exit_code == 0 else RunStatus.FAILED

        counts = outcome.counts
        for logical in outcome.logical_tests:
            execution = await self.run_repo.add_execution(
                run_id=run.id,
                nodeid=logical.nodeid,
                status=RunStatus(logical.status.value)
                if logical.status.value in {member.value for member in RunStatus}
                else RunStatus.ERROR,
                retry_count=logical.reruns,
                error_message=logical.failure_message,
                stack_trace=outcome.stdout_tail if logical.status.value in ("FAILED", "ERROR") else None,
            )
            # Skips, xfails and xpasses are outcomes, not failures: only real failures feed the
            # diagnosis/repair pipeline.
            if logical.status.value in ("FAILED", "ERROR"):
                category, action, locator = FailureClassifier.classify(
                    logical.failure_message or "", outcome.stdout_tail
                )
                await self.run_repo.create_failure_record(
                    run_id=run.id,
                    execution_id=execution.id,
                    test_nodeid=logical.nodeid,
                    test_name=logical.nodeid.split("::")[-1][:250],
                    classification=category.value,
                    exception_type=(logical.failure_message or "").split(":")[0][:200] or "UnknownError",
                    error_message=logical.failure_message or "test failed",
                    stack_trace=outcome.stdout_tail,
                    failing_locator=locator,
                    suggested_action=action,
                )

        await self.run_repo.update_run_status(
            run_id=run.id,
            status=status,
            passed=counts.get("passed", 0),
            failed=counts.get("failed", 0) + counts.get("error", 0),
            skipped=counts.get("skipped", 0),
            duration_ms=outcome.duration_ms,
            log_output=((outcome.stdout_tail or "") + ("\n" + outcome.stderr_tail if outcome.stderr_tail else ""))[
                -20000:
            ]
            or None,
        )
        return run.id

    # --- allure -----------------------------------------------------------------------------

    async def import_allure_results(self, project_id: str) -> AllureImportReport:
        imported = await self.get_imported_project(project_id)
        results_dir = Path(imported.workspace_path) / (imported.contract.allure_results_dir or "allure-results")
        if not results_dir.is_dir():
            raise OnboardingError(f"No Allure results directory in the imported workspace: {results_dir}")
        return AllureResultImporter().import_from(results_dir)

    # --- helpers ----------------------------------------------------------------------------

    def _workspace_path_for(self, project_id: str) -> Path:
        """Where a project's workspace lives: the same derivation every other component uses."""
        if self.imports_dir:
            return Path(self.imports_dir) / project_id
        return Path(self.workspace_base_dir or Path("runtime/workspaces")) / project_id

    def _report_artifacts_dir(self, project_id: str) -> Path:
        """Platform-owned directory for pytest report logs, deliberately outside the workspace."""
        # Absolute: the report directory is passed to the project process through PYTHONPATH, and a
        # relative entry would resolve against the workspace the child runs in.
        base = (
            (self.workspace_base_dir or Path("runtime/workspaces")).parent / "pytest-reports" / project_id
        ).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

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
