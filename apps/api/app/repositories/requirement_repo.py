from __future__ import annotations

import uuid

from project_model.models import RequirementCreate, RequirementUpdate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import RequirementORM, utc_now


class RequirementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project(self, project_id: str, limit: int | None = None) -> list[RequirementORM]:
        query = (
            select(RequirementORM)
            .where(RequirementORM.project_id == project_id)
            .order_by(RequirementORM.created_at.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_all(self) -> int:
        """Row count without materialising the table."""
        result = await self.session.execute(select(func.count()).select_from(RequirementORM))
        return int(result.scalar() or 0)

    async def list_all(self, limit: int | None = None) -> list[RequirementORM]:
        query = select(RequirementORM).order_by(RequirementORM.created_at.desc())
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, req_id: str) -> RequirementORM | None:
        result = await self.session.execute(select(RequirementORM).where(RequirementORM.id == req_id))
        return result.scalar_one_or_none()

    async def create(self, data: RequirementCreate) -> RequirementORM:
        req_id = f"req_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = RequirementORM(
            id=req_id,
            project_id=data.project_id,
            title=data.title,
            description=data.description,
            acceptance_criteria=data.acceptance_criteria,
            status=data.status.value,
            external_system=data.external_system,
            external_id=data.external_id,
            external_url=data.external_url,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update(self, req_id: str, data: RequirementUpdate) -> RequirementORM | None:
        orm = await self.get_by_id(req_id)
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
