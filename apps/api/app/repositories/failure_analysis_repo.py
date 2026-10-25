from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from qa_core.ai.trace import AITraceEvent
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.persistence.models import FailureAnalysisORM, utc_now

_TERMINAL_EVENTS = {
    "run.completed": "COMPLETED",
    "run.failed": "FAILED",
    "run.cancelled": "CANCELLED",
    "run.timeout": "TIMEOUT",
    "run.interrupted": "INTERRUPTED",
}

# Grace on top of the analysis budget before a RUNNING row is treated as ownerless.
ORPHAN_GRACE_SECONDS = 60.0


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

    async def get_state_source(self, analysis_id: str) -> dict | None:
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None:
            return None
        return {"failure_id": row.failure_id, "result": row.result or {}}

    async def append(self, analysis_id: str, event: AITraceEvent, *, result: dict | None = None) -> None:
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None:
            raise ValueError("Analysis record not found")
        serialized_event = SensitiveRedactor.redact_value(event.model_dump(mode="json"))
        verification_run_id = (serialized_event.get("metadata") or {}).get("verification_run_id")
        run_scoped = event.type in {
            "verification.started",
            "verification.completed",
            "repair.failed",
            "repair.verified",
        }
        duplicate = bool(serialized_event.get("step_id")) and any(
            existing.get("type") == serialized_event.get("type")
            and existing.get("step_id") == serialized_event.get("step_id")
            and (not run_scoped or (existing.get("metadata") or {}).get("verification_run_id") == verification_run_id)
            for existing in row.events
        )
        rolled_back = (row.result or {}).get("repair_state") == "ROLLED_BACK"
        stale_failure = rolled_back and event.type == "repair.failed"
        terminal_status = _TERMINAL_EVENTS.get(event.type)
        stale_terminal = terminal_status is not None and row.status != "RUNNING"
        if not duplicate and not stale_failure and not stale_terminal:
            row.events = [*row.events, serialized_event]
        if row.status == "RUNNING" and terminal_status is not None:
            row.status = terminal_status
            row.finished_at = utc_now()
        if result is not None and not stale_terminal:
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

    async def get(self, analysis_id: str) -> dict[str, Any] | None:
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "failure_id": row.failure_id,
            "status": row.status,
            "events": row.events,
            "result": row.result,
            "created_at": row.created_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    async def finalize(
        self,
        analysis_id: str,
        *,
        status: str,
        event: AITraceEvent | None = None,
        result: dict[str, Any] | None = None,
    ) -> bool:
        """Close a RUNNING analysis exactly once; a lost race reports False instead of overwriting it."""
        row = await self.session.get(FailureAnalysisORM, analysis_id)
        if row is None:
            return False
        claimed = await self.session.execute(
            update(FailureAnalysisORM)
            .where(FailureAnalysisORM.id == analysis_id, FailureAnalysisORM.status == "RUNNING")
            .values(status=status, finished_at=utc_now())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            return False
        await self.session.refresh(row)
        if event is not None:
            row.events = [*row.events, SensitiveRedactor.redact_value(event.model_dump(mode="json"))]
        if result is not None:
            row.result = SensitiveRedactor.redact_value(result)
        await self.session.flush()
        return True

    async def list_running_ids(self) -> list[str]:
        return list(
            (
                await self.session.execute(
                    select(FailureAnalysisORM.id)
                    .where(FailureAnalysisORM.status == "RUNNING")
                    .order_by(FailureAnalysisORM.created_at)
                )
            )
            .scalars()
            .all()
        )

    async def list_stale_running(self, *, timeout_seconds: float) -> list[str]:
        """RUNNING rows past their own budget plus a grace period: their owner can no longer report back.

        A live analysis is bounded by its own total budget, so a row this old has lost its owner
        (crashed task, killed process) and must not stay RUNNING forever. Closing it belongs to the
        service, which also records why it ended and releases the repair workflow.
        """
        cutoff = utc_now() - timedelta(seconds=timeout_seconds + ORPHAN_GRACE_SECONDS)
        return list(
            (
                await self.session.execute(
                    select(FailureAnalysisORM.id)
                    .where(FailureAnalysisORM.status == "RUNNING", FailureAnalysisORM.created_at < cutoff)
                    .order_by(FailureAnalysisORM.created_at)
                )
            )
            .scalars()
            .all()
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
