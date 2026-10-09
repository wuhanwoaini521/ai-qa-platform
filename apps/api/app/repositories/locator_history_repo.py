from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import FailureAnalysisORM, LocatorHistoryORM, utc_now


class LocatorHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_ids(self, identities: list[str]) -> list[LocatorHistoryORM]:
        if not identities:
            return []
        result = await self.session.execute(select(LocatorHistoryORM).where(LocatorHistoryORM.id.in_(identities)))
        return list(result.scalars().all())

    async def claim_verified_heal(self, analysis_id: str) -> bool:
        analysis = await self.session.get(FailureAnalysisORM, analysis_id)
        if analysis is None or not analysis.result.get("verified") or analysis.result.get("locator_heal_recorded"):
            return False
        result = await self.session.execute(
            update(FailureAnalysisORM)
            .where(FailureAnalysisORM.id == analysis_id, FailureAnalysisORM.result == analysis.result)
            .values(result={**analysis.result, "locator_heal_recorded": True})
        )
        return result.rowcount == 1

    async def record_outcome(self, values: dict) -> None:
        now = utc_now()
        insert = sqlite_insert if self.session.bind.dialect.name == "sqlite" else pg_insert
        statement = insert(LocatorHistoryORM).values(**values)
        updates = {
            field: getattr(LocatorHistoryORM, field) + values[field]
            for field in ("success_count", "failure_count", "verification_count", "heal_count")
        }
        updates["updated_at"] = now
        if values["last_success_at"]:
            updates["last_success_at"] = now
        if values["last_failure_at"]:
            updates["last_failure_at"] = now
        await self.session.execute(statement.on_conflict_do_update(index_elements=["id"], set_=updates))
