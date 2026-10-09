from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import AIDailyBudgetORM


class AIDailyBudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_day(self, day: str) -> AIDailyBudgetORM | None:
        return await self.session.get(AIDailyBudgetORM, day)

    async def reserve(self, day: str, max_requests: int) -> bool:
        insert = sqlite_insert if self.session.bind.dialect.name == "sqlite" else pg_insert
        await self.session.execute(
            insert(AIDailyBudgetORM).values(day=day, reserved_requests=0).on_conflict_do_nothing(index_elements=["day"])
        )
        result = await self.session.execute(
            update(AIDailyBudgetORM)
            .where(AIDailyBudgetORM.day == day, AIDailyBudgetORM.reserved_requests < max_requests)
            .values(reserved_requests=AIDailyBudgetORM.reserved_requests + 1)
        )
        return result.rowcount == 1
