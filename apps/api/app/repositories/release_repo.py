from __future__ import annotations

import uuid

from project_model.models import ReleaseCreate, ReleaseUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import ReleaseORM, utc_now


class ReleaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project(self, project_id: str) -> list[ReleaseORM]:
        result = await self.session.execute(
            select(ReleaseORM).where(ReleaseORM.project_id == project_id).order_by(ReleaseORM.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[ReleaseORM]:
        result = await self.session.execute(select(ReleaseORM).order_by(ReleaseORM.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_id(self, release_id: str) -> ReleaseORM | None:
        result = await self.session.execute(select(ReleaseORM).where(ReleaseORM.id == release_id))
        return result.scalar_one_or_none()

    async def create(self, data: ReleaseCreate) -> ReleaseORM:
        rel_id = f"rel_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = ReleaseORM(
            id=rel_id,
            project_id=data.project_id,
            version=data.version,
            name=data.name,
            description=data.description,
            status=data.status.value,
            target_date=data.target_date,
            pass_rate_threshold=data.pass_rate_threshold,
            max_allowed_flaky=data.max_allowed_flaky,
            quality_score=data.quality_score,
            blockers=data.blockers,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update(self, release_id: str, data: ReleaseUpdate) -> ReleaseORM | None:
        orm = await self.get_by_id(release_id)
        if not orm:
            return None
        values = data.model_dump(exclude_unset=True)
        if "status" in values and values["status"] is not None:
            values["status"] = values["status"].value
        for k, v in values.items():
            setattr(orm, k, v)
        orm.updated_at = utc_now()
        await self.session.flush()
        return orm

    async def delete(self, release_id: str) -> bool:
        orm = await self.get_by_id(release_id)
        if not orm:
            return False
        await self.session.delete(orm)
        await self.session.flush()
        return True
