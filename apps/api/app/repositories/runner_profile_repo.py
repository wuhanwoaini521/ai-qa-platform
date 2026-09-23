from __future__ import annotations

import uuid

from project_model.models import RunnerProfileCreate, RunnerProfileUpdate
from sqlalchemy import desc, select

from app.persistence import database
from app.persistence.models import RunnerProfileORM, utc_now


class RunnerProfileRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def list_profiles(self, project_id: str | None = None) -> list[RunnerProfileORM]:
        async with self.session_factory() as session:
            stmt = select(RunnerProfileORM)
            if project_id:
                stmt = stmt.where((RunnerProfileORM.project_id == project_id) | (RunnerProfileORM.project_id.is_(None)))
            stmt = stmt.order_by(desc(RunnerProfileORM.created_at))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_id(self, profile_id: str) -> RunnerProfileORM | None:
        async with self.session_factory() as session:
            stmt = select(RunnerProfileORM).where(RunnerProfileORM.id == profile_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_profile(self, data: RunnerProfileCreate) -> RunnerProfileORM:
        async with self.session_factory() as session:
            profile = RunnerProfileORM(
                id=str(uuid.uuid4()),
                project_id=data.project_id,
                name=data.name,
                type=data.type.value if hasattr(data.type, "value") else str(data.type),
                enabled=data.enabled,
                config=data.config,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    async def update_profile(self, profile_id: str, data: RunnerProfileUpdate) -> RunnerProfileORM | None:
        async with self.session_factory() as session:
            stmt = select(RunnerProfileORM).where(RunnerProfileORM.id == profile_id)
            result = await session.execute(stmt)
            profile = result.scalar_one_or_none()
            if not profile:
                return None

            if data.name is not None:
                profile.name = data.name
            if data.enabled is not None:
                profile.enabled = data.enabled
            if data.config is not None:
                profile.config = data.config
            profile.updated_at = utc_now()

            await session.commit()
            await session.refresh(profile)
            return profile

    async def delete_profile(self, profile_id: str) -> bool:
        async with self.session_factory() as session:
            stmt = select(RunnerProfileORM).where(RunnerProfileORM.id == profile_id)
            result = await session.execute(stmt)
            profile = result.scalar_one_or_none()
            if not profile:
                return False
            await session.delete(profile)
            await session.commit()
            return True
