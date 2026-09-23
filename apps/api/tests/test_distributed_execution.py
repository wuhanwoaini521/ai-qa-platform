from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from app.main import app
from app.persistence.database import init_db
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.job_queue_service import JobQueueService
from app.services.runner_backends import (
    DistributedWorkerBackend,
    DockerRunnerBackend,
    LocalProcessRunnerBackend,
)
from app.services.worker_service import WorkerService
from httpx import ASGITransport, AsyncClient
from project_model.models import (
    JobStatus,
    TestRun,
    WorkerCreate,
    WorkerHeartbeatRequest,
    WorkerStatus,
)


@pytest.mark.asyncio
async def test_worker_and_cluster_status():
    await init_db()
    worker_service = WorkerService()

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
async def test_job_queue_and_dispatch():
    await init_db()
    job_service = JobQueueService()

    run_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
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
async def test_runner_backends():
    run = TestRun(
        id="run_test_123",
        project_id="proj_1",
        workspace_id="ws_1",
        status="RUNNING",
        requested_by="user",
        environment={},
        browser="chromium",
        markers=[],
        nodeids=["tests/test_demo.py::test_example"],
        total=1,
        passed=0,
        failed=0,
        skipped=0,
        cancelled=0,
        duration_ms=0.0,
        created_at=datetime.now(timezone.utc),
    )

    local_backend = LocalProcessRunnerBackend()
    local_res = await local_backend.execute(run, workspace_path="/tmp/ws")
    assert local_res["runner_type"] == "LOCAL"
    assert "pytest -v tests/test_demo.py::test_example" in local_res["command"]

    docker_backend = DockerRunnerBackend()
    docker_res = await docker_backend.execute(run, workspace_path="/tmp/ws")
    assert docker_res["runner_type"] == "DOCKER"
    assert "docker run --rm" in docker_res["command"]

    worker_backend = DistributedWorkerBackend()
    worker_res = await worker_backend.execute(run, workspace_path="/tmp/ws")
    assert worker_res["runner_type"] == "WORKER"
    assert worker_res["total_nodeids"] == 1


@pytest.mark.asyncio
async def test_artifact_storage_service():
    storage = ArtifactStorageService(base_dir="/tmp/ai_qa_test_artifacts")
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
async def test_distributed_endpoints():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
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
