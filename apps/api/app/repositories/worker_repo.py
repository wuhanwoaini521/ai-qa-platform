from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from project_model.models import Worker, WorkerCreate, WorkerStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import WorkerORM, utc_now


class WorkerRepository:
    def __init__(self, session_or_factory=None) -> None:
        if isinstance(session_or_factory, AsyncSession):
            self._session: AsyncSession | None = session_or_factory
            self._session_factory = None
        else:
            self._session = None
            self._session_factory = session_or_factory

    @property
    def session_factory(self):
        if self._session_factory is not None:
            return self._session_factory

        return database.get_session

    async def _run(self, session: AsyncSession | None, fn):
        active_session = session or self._session
        if active_session:
            return await fn(active_session)
        async with self.session_factory() as s:
            return await fn(s)

    async def register_or_update(
        self, data: WorkerCreate, worker_id: str | None = None, session: AsyncSession | None = None
    ) -> Worker:
        wid = worker_id or str(uuid.uuid4())
        now = utc_now()

        async def _exec(s: AsyncSession) -> Worker:
            stmt = select(WorkerORM).where(WorkerORM.id == wid)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if orm:
                orm.hostname = data.hostname
                orm.ip_address = data.ip_address
                orm.status = data.status.value if isinstance(data.status, WorkerStatus) else str(data.status)
                orm.browsers = data.browsers
                orm.os = data.os
                orm.max_concurrency = data.max_concurrency
                orm.current_load = data.current_load
                orm.tags = data.tags
                orm.last_heartbeat_at = now
            else:
                orm = WorkerORM(
                    id=wid,
                    hostname=data.hostname,
                    ip_address=data.ip_address,
                    status=data.status.value if isinstance(data.status, WorkerStatus) else str(data.status),
                    browsers=data.browsers,
                    os=data.os,
                    max_concurrency=data.max_concurrency,
                    current_load=data.current_load,
                    tags=data.tags,
                    last_heartbeat_at=now,
                    registered_at=now,
                )
                s.add(orm)

            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        return await self._run(session, _exec)

    async def heartbeat(
        self,
        worker_id: str,
        status: WorkerStatus = WorkerStatus.ONLINE,
        current_load: int = 0,
        session: AsyncSession | None = None,
    ) -> Worker | None:
        async def _exec(s: AsyncSession) -> Worker | None:
            stmt = select(WorkerORM).where(WorkerORM.id == worker_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            orm.status = status.value if isinstance(status, WorkerStatus) else str(status)
            orm.current_load = current_load
            orm.last_heartbeat_at = utc_now()
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        return await self._run(session, _exec)

    async def get_by_id(self, worker_id: str, session: AsyncSession | None = None) -> Worker | None:
        async def _exec(s: AsyncSession) -> Worker | None:
            stmt = select(WorkerORM).where(WorkerORM.id == worker_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._to_model(orm) if orm else None

        return await self._run(session, _exec)

    async def list_all(self, session: AsyncSession | None = None) -> list[Worker]:
        async def _exec(s: AsyncSession) -> list[Worker]:
            # Auto update lost workers
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
            stmt = select(WorkerORM).order_by(WorkerORM.registered_at.desc())
            res = await s.execute(stmt)
            workers = []
            for orm in res.scalars().all():
                hb = orm.last_heartbeat_at
                if hb and hb < cutoff and orm.status not in ("OFFLINE", "LOST"):
                    orm.status = "LOST"
                workers.append(self._to_model(orm))
            await s.commit()
            return workers

        return await self._run(session, _exec)

    async def delete(self, worker_id: str, session: AsyncSession | None = None) -> bool:
        async def _exec(s: AsyncSession) -> bool:
            stmt = select(WorkerORM).where(WorkerORM.id == worker_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return False
            await s.delete(orm)
            await s.commit()
            return True

        return await self._run(session, _exec)

    @staticmethod
    def _to_model(orm: WorkerORM) -> Worker:
        return Worker(
            id=orm.id,
            hostname=orm.hostname,
            ip_address=orm.ip_address,
            status=WorkerStatus(orm.status) if orm.status in WorkerStatus.__members__.values() else WorkerStatus.ONLINE,
            browsers=orm.browsers,
            os=orm.os,
            max_concurrency=orm.max_concurrency,
            current_load=orm.current_load,
            tags=orm.tags,
            last_heartbeat_at=orm.last_heartbeat_at,
            registered_at=orm.registered_at,
        )
