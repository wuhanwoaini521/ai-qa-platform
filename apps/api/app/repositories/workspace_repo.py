from __future__ import annotations

import uuid

from project_model.models import WorkspaceCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import WorkspaceORM, utc_now


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_project_id(self, project_id: str) -> WorkspaceORM | None:
        result = await self.session.execute(select(WorkspaceORM).where(WorkspaceORM.project_id == project_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, workspace_id: str) -> WorkspaceORM | None:
        result = await self.session.execute(select(WorkspaceORM).where(WorkspaceORM.id == workspace_id))
        return result.scalar_one_or_none()

    async def create(self, data: WorkspaceCreate, path: str) -> WorkspaceORM:
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        orm = WorkspaceORM(
            id=ws_id,
            project_id=data.project_id,
            path=path,
            branch=data.branch,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return orm
