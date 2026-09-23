from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import PlainTextResponse

from app.persistence.database import check_db_health
from app.services.metrics_service import metrics_service
from app.settings import settings

router = APIRouter(tags=["Health & Telemetry"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Overall platform health status including subsystem checks."""
    db_healthy = await check_db_health()
    storage_accessible = settings.artifact_storage_dir.exists() and os.access(settings.artifact_storage_dir, os.W_OK)

    overall_status = "healthy" if (db_healthy and storage_accessible) else "degraded"

    return {
        "status": overall_status,
        "service": "ai-qa-platform-api",
        "version": "1.0.0",
        "uptime_seconds": round(metrics_service.uptime_seconds, 2),
        "checks": {
            "database": "connected" if db_healthy else "unreachable",
            "artifact_storage": "writable" if storage_accessible else "unwritable",
        },
    }


@router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Kubernetes/Container liveness probe. Fast 200 OK check."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe(response: Response) -> dict[str, Any]:
    """Kubernetes/Container readiness probe. Verifies database and critical subsystems."""
    db_healthy = await check_db_health()
    storage_accessible = settings.artifact_storage_dir.exists() and os.access(settings.artifact_storage_dir, os.W_OK)

    if not (db_healthy and storage_accessible):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "ok" if db_healthy else "down",
            "storage": "ok" if storage_accessible else "error",
        }

    return {
        "status": "ready",
        "database": "ok",
        "storage": "ok",
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> PlainTextResponse:
    """Prometheus exposition metrics endpoint."""
    output = await metrics_service.generate_prometheus_metrics()
    return PlainTextResponse(output, media_type="text/plain; version=0.0.4; charset=utf-8")
