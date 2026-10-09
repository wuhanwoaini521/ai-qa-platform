from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import FlakyClassification, FlakyTestItem, TestHistoryResponse

from app.container import get_flaky_query_service
from app.services.api_read_service import FlakyQueryService

router = APIRouter(prefix="/flaky", tags=["Flaky Intelligence"])


@router.get("", response_model=list[FlakyTestItem])
async def list_flaky_tests(
    project_id: str | None = Query(default=None, description="Optional project ID filter"),
    min_score: float = Query(default=0.0, description="Minimum flaky score threshold"),
    classification: FlakyClassification | None = Query(default=None, description="Filter by classification"),
    service: FlakyQueryService = Depends(get_flaky_query_service),
):
    return await service.list_flaky_tests(project_id=project_id, min_score=min_score, classification=classification)


@router.get("/history", response_model=TestHistoryResponse)
async def get_test_history(
    nodeid: str = Query(..., description="Pytest test node ID"),
    project_id: str = Query(..., description="Target project ID"),
    limit: int = Query(default=20, ge=1, le=100),
    service: FlakyQueryService = Depends(get_flaky_query_service),
):
    return await service.get_test_history(nodeid=nodeid, project_id=project_id, limit=limit)
