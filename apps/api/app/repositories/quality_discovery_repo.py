from __future__ import annotations

from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import QualityDiscoveryRunORM, utc_now


class QualityDiscoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, run_id: str) -> QualityDiscoveryRunORM | None:
        result = await self.session.execute(
            select(QualityDiscoveryRunORM).where(QualityDiscoveryRunORM.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str, limit: int = 25) -> list[QualityDiscoveryRunORM]:
        result = await self.session.execute(
            select(QualityDiscoveryRunORM)
            .where(QualityDiscoveryRunORM.project_id == project_id)
            .order_by(desc(QualityDiscoveryRunORM.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        project_id: str,
        requested_by: str,
        mode: str,
        start_url: str,
        requirement_id: str | None,
        requirement_text: str,
        allowed_domains: list[str],
    ) -> QualityDiscoveryRunORM:
        now = utc_now()
        row = QualityDiscoveryRunORM(
            id=f"qd_{uuid4().hex[:16]}",
            project_id=project_id,
            requested_by=requested_by,
            mode=mode,
            start_url=start_url,
            requirement_id=requirement_id,
            requirement_text=requirement_text,
            allowed_domains=allowed_domains,
            status="QUEUED",
            progress={"states": 0, "actions": 0, "features": 0},
            result={"requirements": [], "states": [], "edges": [], "actions": [], "features": [], "gaps": [], "coverage": []},
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, run_id: str, **values) -> QualityDiscoveryRunORM | None:
        row = await self.get(run_id)
        if row is None:
            return None
        for name, value in values.items():
            setattr(row, name, value)
        row.updated_at = utc_now()
        await self.session.flush()
        return row
