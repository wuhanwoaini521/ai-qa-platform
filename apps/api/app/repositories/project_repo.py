from __future__ import annotations

import uuid

from project_model.models import ProjectCreate, ProjectUpdate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import ProjectORM, utc_now


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_all(self) -> int:
        """Row count without materialising the table."""
        result = await self.session.execute(select(func.count()).select_from(ProjectORM))
        return int(result.scalar() or 0)

    async def list_all(self, limit: int | None = None) -> list[ProjectORM]:
        query = select(ProjectORM).order_by(ProjectORM.created_at.desc())
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, project_id: str) -> ProjectORM | None:
        result = await self.session.execute(select(ProjectORM).where(ProjectORM.id == project_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, project_id: str) -> ProjectORM | None:
        result = await self.session.execute(select(ProjectORM).where(ProjectORM.id == project_id).with_for_update())
        return result.scalar_one_or_none()

    async def create(self, data: ProjectCreate) -> ProjectORM:
        proj_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = ProjectORM(
            id=proj_id,
            name=data.name,
            description=data.description,
            repository_url=data.repository_url,
            default_branch=data.default_branch,
            framework_type=data.framework_type.value,
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def update(self, project_id: str, data: ProjectUpdate) -> ProjectORM | None:
        orm = await self.get_by_id(project_id)
        if not orm:
            return None
        values = data.model_dump(exclude_unset=True)
        if "framework_type" in values and values["framework_type"] is not None:
            values["framework_type"] = values["framework_type"].value
        for k, v in values.items():
            setattr(orm, k, v)
        orm.updated_at = utc_now()
        await self.session.flush()
        return orm
