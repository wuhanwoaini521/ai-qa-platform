from __future__ import annotations

from project_model.models import ApplyRepairRequest, FailureRecord
from qa_core.healing.models import LocatorRepairProposal
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import FailureRecordORM
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService


class FailureService:
    def __init__(
        self,
        run_repo: TestRunRepository,
        workspace_repo: WorkspaceRepository,
        workspace_service: WorkspaceService,
        orchestrator: ProductionQAOrchestrator | None = None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or ProductionQAOrchestrator()

    def _to_dto(self, orm: FailureRecordORM) -> FailureRecord:
        return FailureRecord(
            id=orm.id,
            run_id=orm.run_id,
            execution_id=orm.execution_id,
            test_nodeid=orm.test_nodeid,
            test_name=orm.test_name,
            classification=orm.classification,
            exception_type=orm.exception_type,
            error_message=orm.error_message,
            stack_trace=orm.stack_trace,
            failing_locator=orm.failing_locator,
            screenshot_path=orm.screenshot_path,
            trace_path=orm.trace_path,
            dom_snapshot_path=orm.dom_snapshot_path,
            console_logs=orm.console_logs or [],
            suggested_action=orm.suggested_action,
            repair_proposal=orm.repair_proposal,
            created_at=orm.created_at,
        )

    async def list_failures(self) -> list[FailureRecord]:
        orms = await self.run_repo.list_failures()
        return [self._to_dto(orm) for orm in orms]

    async def get_failure(self, failure_id: str) -> FailureRecord | None:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            return None
        return self._to_dto(orm)

    async def diagnose_failure(self, failure_id: str) -> FailureRecord:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        diag = self.orchestrator.diagnose_failure(
            error_message=orm.error_message,
            stack_trace=orm.stack_trace,
            test_nodeid=orm.test_nodeid,
        )
        orm.classification = diag.classification.value
        orm.suggested_action = diag.suggested_action
        if diag.failing_locator:
            orm.failing_locator = diag.failing_locator
            proposal = self.orchestrator.propose_locator_repair(
                failing_locator=diag.failing_locator,
                error_message=orm.error_message,
                file_path=orm.test_nodeid.split("::")[0],
            )
            orm.repair_proposal = proposal.model_dump()

        await self.run_repo.session.flush()
        return self._to_dto(orm)

    async def generate_repair_proposal(self, failure_id: str) -> LocatorRepairProposal:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        failing_loc = orm.failing_locator or "element"
        proposal = self.orchestrator.propose_locator_repair(
            failing_locator=failing_loc,
            error_message=orm.error_message,
            file_path=orm.test_nodeid.split("::")[0],
        )
        orm.repair_proposal = proposal.model_dump()
        await self.run_repo.session.flush()
        return proposal

    async def apply_repair(self, workspace_id: str, payload: ApplyRepairRequest) -> dict[str, str]:
        """Explicitly applies code repair diff upon user confirmation."""
        current_content = await self.workspace_service.read_file(workspace_id, payload.file_path)
        if payload.old_code not in current_content:
            # If not exact match, perform safe line replacement
            raise ValueError(f"Original target code block not found in {payload.file_path}")

        updated_content = current_content.replace(payload.old_code, payload.new_code, 1)
        await self.workspace_service.write_file(workspace_id, payload.file_path, updated_content)
        return {"status": "applied", "file_path": payload.file_path}
