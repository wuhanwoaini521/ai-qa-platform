"""Job reliability: cancellation propagation, terminal-state races, dead-worker recovery.

These are the failure modes that leave a run stuck in RUNNING forever after a worker dies or a
cancel request races a finishing worker.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from app.persistence.models import ExecutionJobORM, WorkerORM, utc_now
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory, TaskRepositoryUnitOfWork
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.job_queue_service import JobQueueService
from app.services.test_run_service import TestRunService as _TestRunService
from app.services.worker_service import WorkerService
from app.services.workspace_service import WorkspaceService
from httpx import AsyncClient
from project_model import models as pm
from project_model.models import (
    JobStatus,
    ProjectCreate,
    RunnerType,
    RunStatus,
    WorkerCreate,
    WorkerStatus,
)
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _job_service(db) -> JobQueueService:
    return JobQueueService(repository_scope=TaskRepositoryScopeFactory(), job_repo=JobRepository(db))


def _run_service(session) -> _TestRunService:
    repositories = TaskRepositoryUnitOfWork(session)
    return _TestRunService(
        repositories.test_runs,
        repositories.workspaces,
        WorkspaceService(),
        repository_scope=TaskRepositoryScopeFactory(),
        repositories=repositories,
        runner_repo=repositories.runner_profiles,
    )


async def _seed_run(db, *, runner_type: RunnerType = RunnerType.WORKER):
    async with db() as session:
        project = await ProjectRepository(session).create(ProjectCreate(name=f"Reliability {uuid.uuid4().hex[:6]}"))
        run = await TestRunRepository(session).create_run(
            pm.TestRunCreate(project_id=project.id, workspace_id=str(uuid.uuid4()), runner_type=runner_type)
        )
        await session.commit()
        return project.id, run


async def test_cancelling_a_job_cancels_its_run(client: AsyncClient, test_db_session) -> None:
    project_id, run = await _seed_run(test_db_session)
    job = await _job_service(test_db_session).enqueue_job(
        run_id=run.id,
        project_id=project_id,
        workspace_id=run.workspace_id,
        nodeids=["tests/test_auth.py::test_login"],
    )

    response = await client.post(f"/api/jobs/{job.id}/cancel")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == JobStatus.CANCELLED.value
    run_after = (await client.get(f"/api/runs/{run.id}")).json()
    assert run_after["status"] == RunStatus.CANCELLED.value, "the run kept running after its job was cancelled"


async def test_terminal_job_status_cannot_be_overwritten(test_db_session) -> None:
    project_id, run = await _seed_run(test_db_session)
    service = _job_service(test_db_session)
    job = await service.enqueue_job(
        run_id=run.id,
        project_id=project_id,
        workspace_id=run.workspace_id,
        nodeids=["tests/test_auth.py::test_login"],
    )
    await service.dispatch_next_job(worker_id="worker-1", browser="chromium")

    completed, failed = await asyncio.gather(
        JobRepository(test_db_session).update_job_status(job.id, JobStatus.COMPLETED, duration_ms=1500.0),
        JobRepository(test_db_session).update_job_status(job.id, JobStatus.FAILED, error_message="worker crashed"),
    )

    async with test_db_session() as session:
        stored = (await session.execute(select(ExecutionJobORM).where(ExecutionJobORM.id == job.id))).scalar_one()

    assert stored.status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value}
    assert stored.finished_at is not None
    # The winning transition must be complete: no job keeps a duration from one verdict and an
    # error message from the other.
    assert (stored.status == JobStatus.COMPLETED.value) == (stored.duration_ms == 1500.0)
    assert (stored.status == JobStatus.FAILED.value) == (stored.error_message == "worker crashed")
    returned = {item.status for item in (completed, failed) if item is not None}
    assert returned <= {JobStatus.COMPLETED.value, JobStatus.FAILED.value}

    # Deterministic sticky-terminal check: a late report can never rewrite a finished job, which is
    # what the previous read-modify-write implementation allowed.
    await JobRepository(test_db_session).update_job_status(job.id, JobStatus.FAILED, error_message="second verdict")
    async with test_db_session() as session:
        after_second_report = (
            await session.execute(select(ExecutionJobORM).where(ExecutionJobORM.id == job.id))
        ).scalar_one()
    assert after_second_report.status == stored.status
    assert after_second_report.error_message == stored.error_message
    assert after_second_report.duration_ms == stored.duration_ms


async def _assign_job_to_worker(db, *, heartbeat_age: timedelta) -> tuple[str, str, str]:
    project_id, run = await _seed_run(db)
    async with db() as session:
        worker = await WorkerService(
            worker_repo=WorkerRepository(session), job_repo=JobRepository(session)
        ).register_worker(WorkerCreate(hostname=f"worker-{uuid.uuid4().hex[:6]}", status=WorkerStatus.ONLINE))
        orm = await session.get(WorkerORM, worker.id)
        orm.last_heartbeat_at = utc_now() - heartbeat_age
        await session.commit()

    job = await _job_service(db).enqueue_job(
        run_id=run.id,
        project_id=project_id,
        workspace_id=run.workspace_id,
        nodeids=["tests/test_auth.py::test_login"],
    )
    claimed = await _job_service(db).dispatch_next_job(worker_id=worker.id, browser="chromium")
    assert claimed is not None
    return run.id, worker.id, job.id


async def test_abandoned_worker_job_recovers_its_run(test_db_session) -> None:
    run_id, _worker_id, job_id = await _assign_job_to_worker(test_db_session, heartbeat_age=timedelta(hours=1))

    async with test_db_session() as session:
        recovered = await _run_service(session).recover_stale_runs(stale_after_seconds=0)

    assert recovered == [run_id]
    async with test_db_session() as session:
        run = await TestRunRepository(session).get_by_id(run_id)
        job = await session.get(ExecutionJobORM, job_id)
    assert run.status == RunStatus.CANCELLED.value
    assert job.status == JobStatus.CANCELLED.value, "the abandoned job stayed assigned to a dead worker"


async def test_live_worker_job_is_not_recovered(test_db_session) -> None:
    run_id, _worker_id, job_id = await _assign_job_to_worker(test_db_session, heartbeat_age=timedelta(seconds=5))

    async with test_db_session() as session:
        recovered = await _run_service(session).recover_stale_runs(stale_after_seconds=0)

    assert recovered == [], "a slow but live worker had its run cancelled"
    async with test_db_session() as session:
        run = await TestRunRepository(session).get_by_id(run_id)
        job = await session.get(ExecutionJobORM, job_id)
    assert run.status == RunStatus.QUEUED.value
    assert job.status == JobStatus.ASSIGNED.value
