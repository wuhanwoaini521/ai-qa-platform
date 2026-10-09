from __future__ import annotations

import pytest
from app.container import get_metrics_service
from app.persistence.database import check_db_health
from httpx import AsyncClient
from worker.daemon import WorkerDaemon


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_check_endpoint(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "ai-qa-platform-api"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "checks" in data
    assert "database" in data["checks"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_liveness_probe(client: AsyncClient):
    response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_readiness_probe(client: AsyncClient):
    response = await client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_prometheus_metrics_endpoint(client: AsyncClient):
    # Trigger an API call first to increment metrics
    await client.get("/api/health")

    response = await client.get("/api/metrics")
    assert response.status_code == 200
    text = response.text
    assert "ai_qa_platform_uptime_seconds" in text
    assert "ai_qa_workers_total" in text
    assert "ai_qa_jobs_status" in text
    assert "ai_qa_http_requests_total" in text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_database_health_check(test_db_session):  # noqa: ARG001
    is_healthy = await check_db_health()
    assert is_healthy is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_metrics_service_summary(test_db_session):  # noqa: ARG001
    get_metrics_service().record_request("GET", "/api/test", 200, 0.05)
    summary = await get_metrics_service().get_summary_metrics()
    assert "uptime_seconds" in summary
    assert summary["total_http_requests"] >= 1
    assert "workers_total" in summary
    assert "jobs_queued" in summary


@pytest.mark.asyncio
async def test_worker_daemon_init_and_attributes():
    daemon = WorkerDaemon(
        api_url="http://127.0.0.1:8000",
        worker_id="test-worker-1",
        worker_name="Test Runner",
        capabilities=["pytest", "chromium"],
        max_concurrency=2,
    )
    assert daemon.worker_id == "test-worker-1"
    assert daemon.worker_name == "Test Runner"
    assert daemon.capabilities == ["pytest", "chromium"]
    assert daemon.max_concurrency == 2
    assert daemon.api_url == "http://127.0.0.1:8000"
