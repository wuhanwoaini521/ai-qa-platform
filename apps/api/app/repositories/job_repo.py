from __future__ import annotations

import uuid
from datetime import datetime

from project_model.models import ExecutionJob, ExecutionJobCreate, JobStatus
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import database
from app.persistence.models import ExecutionJobORM, WorkerORM, utc_now


class JobRepository:
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

    async def create_job(self, data: ExecutionJobCreate, session: AsyncSession | None = None) -> ExecutionJob:
        job_id = str(uuid.uuid4())
        now = utc_now()
        orm = ExecutionJobORM(
            id=job_id,
            run_id=data.run_id,
            project_id=data.project_id,
            workspace_id=data.workspace_id,
            nodeids=data.nodeids,
            runner_type=data.runner_type,
            browser=data.browser,
            priority=data.priority,
            status=data.status.value if isinstance(data.status, JobStatus) else str(data.status),
            assigned_worker_id=data.assigned_worker_id,
            retry_count=data.retry_count,
            max_retries=data.max_retries,
            error_message=data.error_message,
            created_at=now,
            updated_at=now,
        )

        async def _exec(s: AsyncSession) -> ExecutionJob:
            s.add(orm)
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        return await self._run(session, _exec)

    async def list_jobs(
        self,
        run_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        session: AsyncSession | None = None,
    ) -> list[ExecutionJob]:
        async def _exec(s: AsyncSession) -> list[ExecutionJob]:
            stmt = select(ExecutionJobORM)
            if run_id:
                stmt = stmt.where(ExecutionJobORM.run_id == run_id)
            if project_id:
                stmt = stmt.where(ExecutionJobORM.project_id == project_id)
            if status:
                stmt = stmt.where(ExecutionJobORM.status == status)
            stmt = stmt.order_by(ExecutionJobORM.priority.desc(), ExecutionJobORM.created_at.asc()).limit(limit)
            res = await s.execute(stmt)
            return [self._to_model(orm) for orm in res.scalars().all()]

        return await self._run(session, _exec)

    async def get_by_id(self, job_id: str, session: AsyncSession | None = None) -> ExecutionJob | None:
        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            orm = await s.get(ExecutionJobORM, job_id)
            return self._to_model(orm) if orm else None

        return await self._run(session, _exec)

    async def claim_next_job(
        self,
        worker_id: str,
        browser: str = "chromium",
        browsers: list[str] | None = None,
        project_ids: list[str] | None = None,
        session: AsyncSession | None = None,
    ) -> ExecutionJob | None:
        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            stmt = select(ExecutionJobORM).where(ExecutionJobORM.status == JobStatus.QUEUED.value)
            supported_browsers = list(dict.fromkeys(browsers or [browser]))
            stmt = stmt.where(ExecutionJobORM.browser.in_(supported_browsers))
            if project_ids is not None:
                stmt = stmt.where(ExecutionJobORM.project_id.in_(list(dict.fromkeys(project_ids))))
            stmt = (
                stmt.order_by(ExecutionJobORM.priority.desc(), ExecutionJobORM.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await s.execute(stmt)
            orm = result.scalar_one_or_none()
            if orm is None:
                return None

            claimed_at = utc_now()
            claim = await s.execute(
                update(ExecutionJobORM)
                .where(ExecutionJobORM.id == orm.id, ExecutionJobORM.status == JobStatus.QUEUED.value)
                .values(
                    status=JobStatus.ASSIGNED.value,
                    assigned_worker_id=worker_id,
                    started_at=claimed_at,
                    updated_at=claimed_at,
                )
            )
            if claim.rowcount != 1:
                await s.rollback()
                return None
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        return await self._run(session, _exec)

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        duration_ms: float = 0.0,
        error_message: str | None = None,
        session: AsyncSession | None = None,
    ) -> ExecutionJob | None:
        terminal = [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]
        target = status.value if isinstance(status, JobStatus) else str(status)
        now = utc_now()
        values: dict = {"status": target, "updated_at": now}
        if duration_ms > 0:
            values["duration_ms"] = duration_ms
        if error_message:
            values["error_message"] = error_message
        if target in terminal:
            values["finished_at"] = now

        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            # A read-modify-write let a completed worker call resurrect a job cancelled in the
            # meantime; the conditional UPDATE makes the first terminal transition the only one.
            await s.execute(
                update(ExecutionJobORM)
                .where(ExecutionJobORM.id == job_id, ExecutionJobORM.status.notin_(terminal))
                .values(**values)
            )
            await s.commit()
            orm = await s.get(ExecutionJobORM, job_id)
            return self._to_model(orm) if orm else None

        return await self._run(session, _exec)

    async def list_abandoned_run_ids(
        self,
        older_than: datetime,
        worker_offline_before: datetime,
        session: AsyncSession | None = None,
    ) -> list[str]:
        """Runs whose only job is stuck on a worker that stopped heartbeating.

        A crashed worker leaves its job in ASSIGNED/RUNNING forever, and the run with it. Only
        jobs with no recent queue activity *and* an offline worker are returned, so a slow but
        live worker is never recovered.
        """

        async def _exec(s: AsyncSession) -> list[str]:
            stmt = (
                select(ExecutionJobORM.run_id)
                .outerjoin(WorkerORM, WorkerORM.id == ExecutionJobORM.assigned_worker_id)
                .where(
                    ExecutionJobORM.status.in_([JobStatus.ASSIGNED.value, JobStatus.RUNNING.value]),
                    ExecutionJobORM.updated_at < older_than,
                    or_(
                        ExecutionJobORM.assigned_worker_id.is_(None),
                        WorkerORM.id.is_(None),
                        # coalesce: a worker row without a heartbeat must still be treated as offline
                        # instead of making the comparison NULL and leaving the run RUNNING forever.
                        func.coalesce(WorkerORM.last_heartbeat_at, datetime.min) < worker_offline_before,
                    ),
                )
            )
            res = await s.execute(stmt)
            return list(dict.fromkeys(res.scalars().all()))

        return await self._run(session, _exec)

    async def cancel_active_jobs_for_run(self, run_id: str, session: AsyncSession | None = None) -> int:
        async def _exec(s: AsyncSession) -> int:
            result = await s.execute(
                update(ExecutionJobORM)
                .where(
                    ExecutionJobORM.run_id == run_id,
                    ExecutionJobORM.status.in_(
                        [JobStatus.QUEUED.value, JobStatus.ASSIGNED.value, JobStatus.RUNNING.value]
                    ),
                )
                .values(status=JobStatus.CANCELLED.value, finished_at=utc_now(), updated_at=utc_now())
            )
            await s.commit()
            return int(result.rowcount or 0)

        return await self._run(session, _exec)

    @staticmethod
    def _to_model(orm: ExecutionJobORM) -> ExecutionJob:
        return ExecutionJob(
            id=orm.id,
            run_id=orm.run_id,
            project_id=orm.project_id,
            workspace_id=orm.workspace_id,
            nodeids=orm.nodeids,
            runner_type=orm.runner_type,
            browser=orm.browser,
            priority=orm.priority,
            status=JobStatus(orm.status) if orm.status in JobStatus.__members__.values() else JobStatus.QUEUED,
            assigned_worker_id=orm.assigned_worker_id,
            retry_count=orm.retry_count,
            max_retries=orm.max_retries,
            error_message=orm.error_message,
            duration_ms=orm.duration_ms,
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
