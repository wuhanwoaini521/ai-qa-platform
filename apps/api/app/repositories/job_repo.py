from __future__ import annotations

import uuid

from project_model.models import ExecutionJob, ExecutionJobCreate, JobStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_session
from app.persistence.models import ExecutionJobORM, utc_now


class JobRepository:
    def __init__(self, session_factory=get_session) -> None:
        self.session_factory = session_factory

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

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def get_by_id(self, job_id: str, session: AsyncSession | None = None) -> ExecutionJob | None:
        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            stmt = select(ExecutionJobORM).where(ExecutionJobORM.id == job_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            return self._to_model(orm) if orm else None

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

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

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def claim_next_job(
        self, worker_id: str, browser: str = "chromium", session: AsyncSession | None = None
    ) -> ExecutionJob | None:
        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            stmt = (
                select(ExecutionJobORM)
                .where(ExecutionJobORM.status == "QUEUED", ExecutionJobORM.browser == browser)
                .order_by(ExecutionJobORM.priority.desc(), ExecutionJobORM.created_at.asc())
                .limit(1)
            )
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            orm.status = "ASSIGNED"
            orm.assigned_worker_id = worker_id
            orm.started_at = utc_now()
            orm.updated_at = utc_now()
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        duration_ms: float = 0.0,
        error_message: str | None = None,
        session: AsyncSession | None = None,
    ) -> ExecutionJob | None:
        async def _exec(s: AsyncSession) -> ExecutionJob | None:
            stmt = select(ExecutionJobORM).where(ExecutionJobORM.id == job_id)
            res = await s.execute(stmt)
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            orm.status = status.value if isinstance(status, JobStatus) else str(status)
            if duration_ms > 0:
                orm.duration_ms = duration_ms
            if error_message:
                orm.error_message = error_message
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                orm.finished_at = utc_now()
            orm.updated_at = utc_now()
            await s.commit()
            await s.refresh(orm)
            return self._to_model(orm)

        if session:
            return await _exec(session)
        async with self.session_factory() as s:
            return await _exec(s)

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
