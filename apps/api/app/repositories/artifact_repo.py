from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import ArtifactORM, utc_now


class ArtifactRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def create(
        self,
        filename: str,
        size_bytes: int,
        content_type: str,
        storage_type: str,
        storage_path: str,
        session: AsyncSession | None = None,
        project_id: str | None = None,
        created_by: str | None = None,
    ) -> ArtifactORM:
        art_id = str(uuid.uuid4())
        orm = ArtifactORM(
            id=art_id,
            filename=filename,
            size_bytes=size_bytes,
            content_type=content_type,
            storage_type=storage_type,
            storage_path=storage_path,
            project_id=project_id,
            created_by=created_by,
            created_at=utc_now(),
        )

        async def _exec(s: AsyncSession) -> ArtifactORM:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return orm

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_id(self, artifact_id: str, session: AsyncSession | None = None) -> ArtifactORM | None:
        async def _exec(s: AsyncSession) -> ArtifactORM | None:
            stmt = select(ArtifactORM).where(ArtifactORM.id == artifact_id)
            res = await s.execute(stmt)
            return res.scalar_one_or_none()

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)
