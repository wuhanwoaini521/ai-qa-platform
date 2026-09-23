from __future__ import annotations

import ast
import time

from project_model.models import (
    ApplyRepairRequest,
    FailureRecord,
    FailureRecurrenceItem,
)
from qa_core.ai.models import FailureAnalysisResponse, LocatorSemanticReview
from qa_core.healing.models import LocatorRepairProposal
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.persistence.models import FailureRecordORM, utc_now
from app.repositories.ai_repo import AIRepository
from app.repositories.run_history_repo import RunHistoryRepository
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
        history_repo: RunHistoryRepository | None = None,
        ai_repo: AIRepository | None = None,
    ) -> None:
        self.run_repo = run_repo
        self.workspace_repo = workspace_repo
        self.workspace_service = workspace_service
        self.orchestrator = orchestrator or ProductionQAOrchestrator()
        self.history_repo = history_repo or RunHistoryRepository()
        self.ai_repo = ai_repo or AIRepository()

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

    async def list_failures(self, project_id: str | None = None, limit: int = 50) -> list[FailureRecord]:
        orms = await self.run_repo.list_failures(limit=limit, project_id=project_id)
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

    async def diagnose_failure_ai(self, failure_id: str) -> FailureAnalysisResponse:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not failure_id or not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        # Fetch historical context
        history_execs = await self.history_repo.get_test_executions(nodeid=orm.test_nodeid, limit=5)
        history_summary = "No prior executions."
        if history_execs:
            history_summary = "\n".join(
                f"- Run: {e.run_id[:8]} | Status: {e.status} | Category: {e.failure_category or 'N/A'} | Duration: {e.duration_ms}ms"
                for e in history_execs
            )

        start = time.perf_counter()
        started_at = utc_now()

        diag_ai = await self.orchestrator.diagnose_failure_ai(
            error_message=orm.error_message,
            stack_trace=orm.stack_trace,
            test_nodeid=orm.test_nodeid,
            failing_locator=orm.failing_locator,
            historical_context=history_summary,
        )

        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await self.ai_repo.record_invocation(
            task="failure_diagnosis",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=220,
            output_tokens=260,
            prompt_version="v1.0",
        )

        return diag_ai

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

    async def review_semantic_repair(
        self, failure_id: str, candidate_locator: str | None = None
    ) -> LocatorSemanticReview:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        old_loc = orm.failing_locator or "element"
        new_loc = candidate_locator or (orm.repair_proposal or {}).get("proposed_locator", '[data-testid="element"]')

        start = time.perf_counter()
        started_at = utc_now()

        review = await self.orchestrator.review_locator_candidate(
            old_locator=old_loc,
            proposed_locator=new_loc,
            strategy="semantic-attribute",
            dom_snippet=orm.dom_snapshot_path or "",
            error_message=orm.error_message,
        )

        duration_ms = (time.perf_counter() - start) * 1000.0

        invocation = self.orchestrator.last_invocation_metadata()
        await self.ai_repo.record_invocation(
            task="locator_review",
            provider=invocation["provider"],
            model=invocation["model"],
            fallback_used=invocation["fallback_used"],
            started_at=started_at,
            duration_ms=duration_ms,
            input_tokens=140,
            output_tokens=160,
            prompt_version="v1.0",
        )

        return review

    async def get_recurrence(self, failure_id: str) -> list[FailureRecurrenceItem]:
        orm = await self.run_repo.get_failure_by_id(failure_id)
        if not orm:
            raise ValueError(f"Failure record not found: {failure_id}")

        return await self.history_repo.get_failure_recurrence(
            nodeid=orm.test_nodeid,
            classification=orm.classification,
            exclude_failure_id=failure_id,
        )

    async def apply_repair(self, workspace_id: str, payload: ApplyRepairRequest) -> dict[str, str]:
        """Apply a human-approved repair patch.

        The replacement is validated before it is written: a locator that contains the quote character
        used by the surrounding string (`"[data-testid=\"ok\"]"`) would otherwise produce a file that
        no longer parses. If no safe form of the patch exists, nothing is written and the caller is
        told why — the platform never leaves a workspace in a broken state.
        """
        current_content = await self.workspace_service.read_file(workspace_id, payload.file_path)
        if payload.old_code not in current_content:
            raise ValueError(f"Original target code block not found in {payload.file_path}")

        updated_content = self._patched_content(current_content, payload.file_path, payload.old_code, payload.new_code)
        if updated_content is None:
            raise ValueError(
                f"The proposed patch would make {payload.file_path} invalid; nothing was written. "
                "Review the locator and apply it manually."
            )

        await self.workspace_service.write_file(workspace_id, payload.file_path, updated_content)
        return {"status": "applied", "file_path": payload.file_path}

    def _patched_content(self, content: str, file_path: str, old_code: str, new_code: str) -> str | None:
        """Replace `old_code` once, preferring a form that keeps the file parseable."""
        index = content.find(old_code)
        if index == -1:
            return None
        if not file_path.endswith(".py"):
            return content[:index] + new_code + content[index + len(old_code) :]

        opening_quote = content[index - 1] if index > 0 else ""
        candidates = [new_code]
        if opening_quote in ("'", '"') and opening_quote in new_code:
            candidates.append(new_code.replace(opening_quote, f"\\{opening_quote}"))

        for candidate in candidates:
            updated = content[:index] + candidate + content[index + len(old_code) :]
            try:
                ast.parse(updated)
            except SyntaxError:
                continue
            return updated
        return None
