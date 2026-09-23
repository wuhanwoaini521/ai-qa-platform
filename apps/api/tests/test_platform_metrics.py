"""Regression tests for the platform telemetry counters (``/api/metrics``)."""

from __future__ import annotations

import pytest
from app.repositories.job_repo import JobRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.job_queue_service import JobQueueService
from app.services.metrics_service import metrics_service
from httpx import AsyncClient
from project_model import models as pm


@pytest.mark.asyncio
async def test_metrics_counters_reflect_registered_workers_and_job_states(client: AsyncClient, test_db_session):
    """Worker/job counters must reflect the persisted enum states, not be permanently zero."""
    worker_repo = WorkerRepository(test_db_session)
    await worker_repo.register_or_update(pm.WorkerCreate(hostname="worker-online-1"))
    await worker_repo.register_or_update(pm.WorkerCreate(hostname="worker-busy-1", status=pm.WorkerStatus.BUSY))

    # Jobs reference a run and a project (FK), seeded through the repositories the app itself uses.
    proj_resp = await client.post("/api/projects", json={"name": "Metrics Counters Project"})
    project_id = proj_resp.json()["id"]
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            pm.TestRunCreate(project_id=project_id, workspace_id="ws-metrics")
        )
        await session.commit()
        run_id = run.id

    queue = JobQueueService(job_repo=JobRepository(test_db_session))
    await queue.enqueue_job(
        run_id=run_id, project_id=project_id, workspace_id="ws-metrics", nodeids=["tests/test_a.py::test_a"]
    )
    completed_job = await queue.enqueue_job(
        run_id=run_id, project_id=project_id, workspace_id="ws-metrics", nodeids=["tests/test_b.py::test_b"]
    )
    failed_job = await queue.enqueue_job(
        run_id=run_id, project_id=project_id, workspace_id="ws-metrics", nodeids=["tests/test_c.py::test_c"]
    )
    await queue.complete_job(completed_job.id, duration_ms=42.0)
    await queue.fail_job(failed_job.id, error_message="boom")

    summary = await metrics_service.get_summary_metrics()
    assert summary["workers_total"] == 2
    assert summary["workers_online"] == 2
    assert summary["workers_busy"] == 1
    assert summary["jobs_queued"] == 1
    assert summary["jobs_running"] == 0
    assert summary["jobs_completed"] == 1
    assert summary["jobs_failed"] == 1

    response = await client.get("/api/metrics")
    assert response.status_code == 200
    body = response.text
    assert "ai_qa_workers_total 2" in body
    assert "ai_qa_workers_online 2" in body
    assert "ai_qa_workers_busy 1" in body
    assert 'ai_qa_jobs_status{state="queued"} 1' in body
    assert 'ai_qa_jobs_status{state="running"} 0' in body
    assert 'ai_qa_jobs_status{state="completed"} 1' in body
    assert 'ai_qa_jobs_status{state="failed"} 1' in body
