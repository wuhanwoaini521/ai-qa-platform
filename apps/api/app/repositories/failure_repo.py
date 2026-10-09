from __future__ import annotations

from typing import Any

from project_model.models import FailureRecord
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import BrowserSessionORM, FailureAnalysisORM, FailureRecordORM, TestRunORM


class FailureRepository:
    """Failure and repair persistence operations used by failure workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _record(row: FailureRecordORM) -> FailureRecord:
        return FailureRecord(
            id=row.id,
            run_id=row.run_id,
            execution_id=row.execution_id,
            test_nodeid=row.test_nodeid,
            test_name=row.test_name,
            classification=row.classification,
            exception_type=row.exception_type,
            error_message=row.error_message or "",
            stack_trace=row.stack_trace or "",
            failing_locator=row.failing_locator,
            screenshot_path=row.screenshot_path,
            trace_path=row.trace_path,
            dom_snapshot_path=row.dom_snapshot_path,
            console_logs=row.console_logs or [],
            suggested_action=row.suggested_action,
            repair_proposal=row.repair_proposal,
            evidence_bundle=row.evidence_bundle or {},
            created_at=row.created_at,
        )

    async def get_by_id(self, failure_id: str) -> FailureRecord | None:
        row = await self.session.get(FailureRecordORM, failure_id)
        return self._record(row) if row else None

    async def list(self, *, limit: int = 50, project_id: str | None = None) -> list[FailureRecord]:
        query = select(FailureRecordORM).order_by(FailureRecordORM.created_at.desc()).limit(limit)
        if project_id:
            query = query.join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id).where(
                TestRunORM.project_id == project_id
            )
        result = await self.session.execute(query)
        return [self._record(row) for row in result.scalars()]

    async def update_diagnosis(
        self,
        failure_id: str,
        *,
        error_message: str,
        stack_trace: str,
        classification: str,
        suggested_action: str,
        failing_locator: str | None,
        clear_repair_proposal: bool,
    ) -> None:
        values: dict[str, Any] = {
            "error_message": error_message,
            "stack_trace": stack_trace,
            "classification": classification,
            "suggested_action": suggested_action,
            "failing_locator": failing_locator,
        }
        if clear_repair_proposal:
            values["repair_proposal"] = None
        await self.session.execute(update(FailureRecordORM).where(FailureRecordORM.id == failure_id).values(**values))
        await self.session.flush()

    async def update_evidence_bundle(self, failure_id: str, payload: dict[str, Any]) -> None:
        row = await self.session.get(FailureRecordORM, failure_id)
        if row is None:
            raise ValueError("Failure record not found")
        row.evidence_bundle = payload
        await self.session.flush()

    async def latest_completed_analyses(self, failure_id: str, *, limit: int = 10):
        result = await self.session.execute(
            select(FailureAnalysisORM)
            .where(FailureAnalysisORM.failure_id == failure_id, FailureAnalysisORM.status == "COMPLETED")
            .order_by(FailureAnalysisORM.created_at.desc())
            .limit(limit)
        )
        return [{"id": row.id, "result": row.result or {}, "events": row.events or []} for row in result.scalars()]

    async def latest_browser_session(self, execution_id: str) -> dict[str, str | None] | None:
        result = await self.session.execute(
            select(BrowserSessionORM)
            .where(BrowserSessionORM.case_execution_id == execution_id)
            .order_by(BrowserSessionORM.started_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return {"current_url": row.current_url, "page_evidence_json": row.page_evidence_json} if row else None

    async def update_repair_proposal(
        self, failure_id: str, proposal: dict[str, Any], *, failing_locator: str | None = None
    ) -> None:
        values: dict[str, Any] = {"repair_proposal": proposal}
        if failing_locator is not None:
            values["failing_locator"] = failing_locator
        await self.session.execute(update(FailureRecordORM).where(FailureRecordORM.id == failure_id).values(**values))
        await self.session.flush()
