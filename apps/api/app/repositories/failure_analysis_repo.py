from __future__ import annotations

from uuid import uuid4

from qa_core.ai.trace import AITraceEvent
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.persistence.models import FailureAnalysisORM, utc_now


class FailureAnalysisRepository:
    """Failure analysis history within the caller-owned application transaction."""

    def __init__(self, session) -> None:
        self.session = session

    async def get_running(self, failure_id: str) -> str | None:
        return await self.session.scalar(
            select(FailureAnalysisORM.id)
            .where(FailureAnalysisORM.failure_id == failure_id, FailureAnalysisORM.status == "RUNNING")
            .order_by(FailureAnalysisORM.created_at.desc())
            .limit(1)
        )

    async def claim(self, failure_id: str) -> tuple[str, bool]:
        """Atomically create the active analysis, or return the existing one."""
        analysis_id = str(uuid4())
        try:
            async with self.session.begin_nested():
                self.session.add(FailureAnalysisORM(id=analysis_id, failure_id=failure_id))
                await self.session.flush()
        except IntegrityError:
            active_id = await self.get_running(failure_id)
            if active_id is None:
                raise
            return active_id, False
        return analysis_id, True

    async def create(self, failure_id: str) -> str:
        analysis_id = str(uuid4())
        self.session.add(FailureAnalysisORM(id=analysis_id, failure_id=failure_id))
        await self.session.flush()
        return analysis_id

    async def append(self, analysis_id: str, event: AITraceEvent, *, result: dict | None = None) -> None:
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None:
            raise ValueError("Analysis record not found")
        serialized_event = SensitiveRedactor.redact_value(event.model_dump(mode="json"))
        verification_run_id = (serialized_event.get("metadata") or {}).get("verification_run_id")
        run_scoped = event.type in {"verification.started", "verification.completed", "repair.failed", "repair.verified"}
        duplicate = bool(serialized_event.get("step_id")) and any(
            existing.get("type") == serialized_event.get("type")
            and existing.get("step_id") == serialized_event.get("step_id")
            and (
                not run_scoped
                or (existing.get("metadata") or {}).get("verification_run_id") == verification_run_id
            )
            for existing in row.events
        )
        rolled_back = (row.result or {}).get("repair_state") == "ROLLED_BACK"
        stale_failure = rolled_back and event.type == "repair.failed"
        if not duplicate and not stale_failure:
            row.events = [*row.events, serialized_event]
        terminal = {"run.completed": "COMPLETED", "run.failed": "FAILED", "run.cancelled": "CANCELLED"}
        if event.type in terminal:
            row.status = terminal[event.type]
            row.finished_at = utc_now()
        if result is not None:
            incoming_result = SensitiveRedactor.redact_value(result)
            if not rolled_back or incoming_result.get("repair_state") == "ROLLED_BACK":
                row.result = incoming_result
        await self.session.flush()

    async def list(self, failure_id: str, limit: int = 20) -> list[dict]:
        rows = (
            (
                await self.session.execute(
                    select(FailureAnalysisORM)
                    .where(FailureAnalysisORM.failure_id == failure_id)
                    .order_by(FailureAnalysisORM.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": row.id,
                "failure_id": row.failure_id,
                "status": row.status,
                "events": row.events,
                "result": row.result,
                "created_at": row.created_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
            for row in rows
        ]

    async def recover_interrupted(self) -> None:
        await self.session.execute(
            update(FailureAnalysisORM)
            .where(FailureAnalysisORM.status == "RUNNING")
            .values(status="INTERRUPTED", finished_at=utc_now())
        )

    async def attach_verification(self, analysis_id: str, failure_id: str, run_id: str) -> None:
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None or row.failure_id != failure_id:
            raise ValueError("Analysis record not found for this failure")
        in_flight_verified_patch = (
            row.result.get("repair_state") == "PATCH_APPLIED"
            and (row.result.get("repair_proposal") or {}).get("applied") is True
        )
        if row.status == "RUNNING" and not in_flight_verified_patch:
            raise ValueError("Wait for the analysis to finish before linking verification")
        result = {**row.result, "verification_run_id": run_id, "verified": False}
        result.pop("verification_run_status", None)
        row.result = result
        await self.session.flush()
