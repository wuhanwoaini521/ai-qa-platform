from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.api import artifacts as artifacts_api
from app.api import workers as workers_api
from app.container import get_job_queue_service
from app.main import app as fastapi_app
from app.repositories.artifact_repo import ArtifactRepository
from app.repositories.job_repo import JobRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.job_queue_service import JobQueueService
from app.services.runner_service import RunnerService
from app.services.worker_service import WorkerService
from httpx import AsyncClient
from project_model import models as pm
from project_model.models import (
    JobStatus,
    ProjectCreate,
    RunnerProfileCreate,
    RunnerProfileUpdate,
    RunnerType,
    WorkerCreate,
    WorkerHeartbeatRequest,
    WorkerStatus,
)


@pytest.mark.asyncio
async def test_worker_and_cluster_status(test_db_session):
    worker_service = WorkerService(
        worker_repo=WorkerRepository(test_db_session),
        job_repo=JobRepository(test_db_session),
    )

    # 1. Register worker
    hostname = f"worker-{uuid.uuid4().hex[:6]}"
    worker = await worker_service.register_worker(
        WorkerCreate(
            hostname=hostname,
            ip_address="10.0.0.12",
            status=WorkerStatus.ONLINE,
            browsers=["chromium", "firefox"],
            max_concurrency=4,
        )
    )
    assert worker.hostname == hostname
    assert worker.status == WorkerStatus.ONLINE

    # 2. Heartbeat
    updated = await worker_service.heartbeat(
        worker.id,
        WorkerHeartbeatRequest(status=WorkerStatus.BUSY, current_load=2),
    )
    assert updated is not None
    assert updated.status == WorkerStatus.BUSY
    assert updated.current_load == 2

    # 3. Cluster Summary
    summary = await worker_service.get_cluster_summary()
    assert summary.total_workers >= 1
    assert summary.total_concurrency_capacity >= 4
    assert summary.used_concurrency >= 2


@pytest.mark.asyncio
async def test_job_queue_and_dispatch(test_db_session):
    job_service = JobQueueService(
        repository_scope=TaskRepositoryScopeFactory(), job_repo=JobRepository(test_db_session)
    )

    # Jobs reference a run and a project (FK enforced by the engine), so seed real parents.
    async with test_db_session() as session:
        project = await ProjectRepository(session).create(ProjectCreate(name="Job Queue Dispatch Project"))
        run = await TestRunRepository(session).create_run(
            pm.TestRunCreate(project_id=project.id, workspace_id=str(uuid.uuid4()))
        )
        await session.commit()
    run_id = run.id
    project_id = project.id
    workspace_id = str(uuid.uuid4())
    worker_id = str(uuid.uuid4())

    # 1. Enqueue Job
    job = await job_service.enqueue_job(
        run_id=run_id,
        project_id=project_id,
        workspace_id=workspace_id,
        nodeids=["tests/test_auth.py::test_login", "tests/test_auth.py::test_logout"],
        browser="chromium",
        priority=20,
    )
    assert job.status == JobStatus.QUEUED
    assert job.priority == 20
    assert len(job.nodeids) == 2

    # 2. Worker claims job
    claimed = await job_service.dispatch_next_job(worker_id=worker_id, browser="chromium")
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.assigned_worker_id == worker_id
    assert claimed.status == JobStatus.ASSIGNED

    # 3. Complete job
    completed = await job_service.complete_job(job.id, duration_ms=1250.0)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert completed.duration_ms == 1250.0


@pytest.mark.asyncio
async def test_runner_selection_resolves_backend_by_profile_type(test_db_session):
    """RunnerService selects an execution backend from the runner profile type/config."""
    service = RunnerService(runner_repo=RunnerProfileRepository(test_db_session))

    # 1. An enabled LOCAL profile resolves to the local runner backend.
    local_profile = await service.create_runner(RunnerProfileCreate(name="Local Dev Runner", type=RunnerType.LOCAL))
    local_health = await service.check_health(local_profile.id)
    assert local_health.type == RunnerType.LOCAL
    assert local_health.status == "AVAILABLE"

    # 2. Non-local-runner profile types fall back to the local backend as well.
    docker_profile = await service.create_runner(RunnerProfileCreate(name="Docker Pool", type=RunnerType.DOCKER))
    docker_health = await service.check_health(docker_profile.id)
    assert docker_health.type == RunnerType.LOCAL
    assert docker_health.status == "AVAILABLE"

    # 3. A disabled profile is reported as DISABLED without contacting any backend.
    await service.update_runner(docker_profile.id, RunnerProfileUpdate(enabled=False))
    disabled_health = await service.check_health(docker_profile.id)
    assert disabled_health.status == "DISABLED"
    assert disabled_health.type == RunnerType.DOCKER

    # 4. The built-in local alias always resolves to the local backend.
    local_alias_health = await service.check_health("local")
    assert local_alias_health.type == RunnerType.LOCAL
    assert local_alias_health.status == "AVAILABLE"

    # 5. Unknown runner profiles are rejected.
    with pytest.raises(ValueError):
        await service.check_health("runner-that-does-not-exist")


@pytest.mark.asyncio
async def test_artifact_storage_service(test_db_session, tmp_path: Path):
    storage = ArtifactStorageService(
        artifact_repo=ArtifactRepository(test_db_session),
        base_dir=str(tmp_path / "artifacts"),
    )
    test_bytes = b"<html><body>Test Report</body></html>"

    upload_res = await storage.save_artifact(
        filename="report.html",
        content=test_bytes,
        content_type="text/html",
    )
    assert upload_res.filename == "report.html"
    assert upload_res.size_bytes == len(test_bytes)

    # Read back
    read_res = await storage.read_artifact_bytes(upload_res.artifact_id)
    assert read_res is not None
    content, filename, ctype = read_res
    assert content == test_bytes
    assert filename == "report.html"
    assert ctype == "text/html"


@pytest.mark.asyncio
async def test_distributed_endpoints(client: AsyncClient, test_db_session, tmp_path, monkeypatch):
    # The /workers, /jobs and /artifacts routers hold service singletons built at import time,
    # which captured their session factory before the test database was installed, so bind them here.
    monkeypatch.setattr(
        workers_api,
        "worker_service",
        WorkerService(worker_repo=WorkerRepository(test_db_session), job_repo=JobRepository(test_db_session)),
    )
    fastapi_app.dependency_overrides[get_job_queue_service] = lambda: JobQueueService(
        repository_scope=TaskRepositoryScopeFactory(), job_repo=JobRepository(test_db_session)
    )
    monkeypatch.setattr(
        artifacts_api,
        "artifact_service",
        ArtifactStorageService(
            artifact_repo=ArtifactRepository(test_db_session),
            base_dir=str(tmp_path / "artifacts"),
        ),
    )

    # 1. Register worker endpoint
    reg_resp = await client.post(
        "/api/workers",
        json={
            "hostname": f"node-test-{uuid.uuid4().hex[:6]}",
            "ip_address": "192.168.1.100",
            "status": "ONLINE",
            "browsers": ["chromium"],
            "max_concurrency": 8,
        },
    )
    assert reg_resp.status_code == 201
    worker_data = reg_resp.json()
    wid = worker_data["id"]

    # 2. Heartbeat endpoint
    hb_resp = await client.post(
        f"/api/workers/{wid}/heartbeat",
        json={"status": "BUSY", "current_load": 4},
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["current_load"] == 4

    # 3. Cluster status endpoint
    cluster_resp = await client.get("/api/workers/cluster-status")
    assert cluster_resp.status_code == 200
    assert cluster_resp.json()["total_workers"] >= 1

    # 4. Jobs list endpoint
    jobs_resp = await client.get("/api/jobs")
    assert jobs_resp.status_code == 200

    # 5. Artifacts upload endpoint
    art_resp = await client.post(
        "/api/artifacts/upload",
        files={"file": ("screenshot.png", b"\x89PNG\r\n\x1a\nfake-png-data", "image/png")},
    )
    assert art_resp.status_code == 201
    art_id = art_resp.json()["artifact_id"]

    # 6. Artifact download endpoint
    dl_resp = await client.get(f"/api/artifacts/{art_id}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.content == b"\x89PNG\r\n\x1a\nfake-png-data"
