from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import ArtifactORM, utc_now


class ArtifactRepository:
    def __init__(self, session_factory=None) -> None:
        self._session = session_factory if isinstance(session_factory, AsyncSession) else None
        self._session_factory = None if self._session is not None else session_factory

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
        commit: bool = True,
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

        async def _exec(s: AsyncSession, *, should_commit: bool) -> ArtifactORM:
            s.add(orm)
            await s.flush()
            if should_commit:
                await s.commit()
                await s.refresh(orm)
            return orm

        if session is not None:
            return await _exec(session, should_commit=commit)
        if self._session is not None:
            return await _exec(self._session, should_commit=commit)
        async with self.session_factory() as s:
            return await _exec(s, should_commit=True)

    async def storage_path_is_referenced(self, storage_path: str) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(ArtifactORM.id).where(ArtifactORM.storage_path == storage_path).limit(1)
            return (await s.execute(stmt)).scalar_one_or_none() is not None

        if self._session is not None:
            return await _exec(self._session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_id(self, artifact_id: str, session: AsyncSession | None = None) -> ArtifactORM | None:
        async def _exec(s: AsyncSession) -> ArtifactORM | None:
            stmt = select(ArtifactORM).where(ArtifactORM.id == artifact_id)
            res = await s.execute(stmt)
            return res.scalar_one_or_none()

        if session is not None:
            return await _exec(session)
        if self._session is not None:
            return await _exec(self._session)
        async with self.session_factory() as s:
            return await _exec(s)
