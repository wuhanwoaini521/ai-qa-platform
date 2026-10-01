from __future__ import annotations

from uuid import uuid4

from qa_core.ai.trace import AITraceEvent
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import select, update

from app.persistence.database import async_session_factory
from app.persistence.models import FailureAnalysisORM, utc_now


class FailureAnalysisRepository:
    """Durable milestones in short transactions, including failure and cancellation."""

    async def create(self, failure_id: str) -> str:
        analysis_id = str(uuid4())
        async with async_session_factory() as session:
            session.add(FailureAnalysisORM(id=analysis_id, failure_id=failure_id))
            await session.commit()
        return analysis_id

    async def append(self, analysis_id: str, event: AITraceEvent, *, result: dict | None = None) -> None:
        async with async_session_factory() as session:
            row = await session.get(FailureAnalysisORM, analysis_id)
            if row is None:
                raise ValueError("Analysis record not found")
            row.events = [*row.events, SensitiveRedactor.redact_value(event.model_dump(mode="json"))]
            terminal = {"run.completed": "COMPLETED", "run.failed": "FAILED", "run.cancelled": "CANCELLED"}
            if event.type in terminal:
                row.status = terminal[event.type]
                row.finished_at = utc_now()
            if result is not None:
                row.result = SensitiveRedactor.redact_value(result)
            await session.commit()

    async def list(self, failure_id: str, limit: int = 20) -> list[dict]:
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(FailureAnalysisORM)
                        .where(
                            FailureAnalysisORM.failure_id == failure_id,
                        )
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
        async with async_session_factory() as session:
            await session.execute(
                update(FailureAnalysisORM)
                .where(
                    FailureAnalysisORM.status == "RUNNING",
                )
                .values(status="INTERRUPTED", finished_at=utc_now())
            )
            await session.commit()

    async def attach_verification(self, analysis_id: str, failure_id: str, run_id: str) -> None:
        async with async_session_factory() as session:
            row = await session.get(FailureAnalysisORM, analysis_id)
            if row is None or row.failure_id != failure_id:
                raise ValueError("Analysis record not found for this failure")
            if row.status == "RUNNING":
                raise ValueError("Wait for the analysis to finish before linking verification")
            result = {**row.result, "verification_run_id": run_id, "verified": False}
            result.pop("verification_run_status", None)
            row.result = result
            await session.commit()
