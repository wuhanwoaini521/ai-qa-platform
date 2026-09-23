from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import (
    FlakyClassification,
    FlakyTestItem,
    TestHistoryResponse,
)

from app.repositories.run_history_repo import RunHistoryRepository

router = APIRouter(prefix="/flaky", tags=["Flaky Intelligence"])


def get_history_repo() -> RunHistoryRepository:
    return RunHistoryRepository()


@router.get("", response_model=list[FlakyTestItem])
async def list_flaky_tests(
    project_id: str | None = Query(default=None, description="Optional project ID filter"),
    min_score: float = Query(default=0.0, description="Minimum flaky score threshold"),
    classification: FlakyClassification | None = Query(default=None, description="Filter by classification"),
    repo: RunHistoryRepository = Depends(get_history_repo),
):
    """Retrieve all flaky test intelligence rankings with deterministic scoring."""
    return await repo.list_flaky_tests(
        project_id=project_id,
        min_score=min_score,
        classification=classification,
    )


@router.get("/history", response_model=TestHistoryResponse)
async def get_test_history(
    nodeid: str = Query(..., description="Pytest test node ID"),
    project_id: str = Query(..., description="Target project ID"),
    limit: int = Query(default=20, ge=1, le=100),
    repo: RunHistoryRepository = Depends(get_history_repo),
):
    """Retrieve full execution history, trend distribution, and flaky scoring for a specific test."""
    return await repo.get_test_history_detail(nodeid=nodeid, project_id=project_id, limit=limit)
