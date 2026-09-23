from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from project_model.models import (
    Release,
    ReleaseCreate,
    ReleaseGateReport,
    ReleaseUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.release_repo import ReleaseRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.quality_intelligence_service import QualityIntelligenceService
from app.services.release_service import ReleaseService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/releases", tags=["Release Management & Quality Gate"])


def get_release_service(session: AsyncSession = Depends(get_db)) -> ReleaseService:
    rel_repo = ReleaseRepository(session)
    run_repo = TestRunRepository(session)
    req_repo = RequirementRepository(session)
    tc_repo = TestCaseRepository(session)
    td_repo = TestDesignRepository(session)
    binding_repo = AutomationBindingRepository(session)
    history_repo = RunHistoryRepository(lambda: session)
    ws_service = WorkspaceService()

    quality_service = QualityIntelligenceService(
        requirement_repo=req_repo,
        test_case_repo=tc_repo,
        test_design_repo=td_repo,
        binding_repo=binding_repo,
        test_run_repo=run_repo,
        history_repo=history_repo,
        workspace_service=ws_service,
    )

    return ReleaseService(
        release_repo=rel_repo,
        test_run_repo=run_repo,
        quality_service=quality_service,
        history_repo=history_repo,
    )


@router.get("", response_model=list[Release])
async def list_releases(
    project_id: str | None = Query(default=None),
    service: ReleaseService = Depends(get_release_service),
):
    return await service.list_releases(project_id=project_id)


@router.post("", response_model=Release, status_code=status.HTTP_201_CREATED)
async def create_release(
    body: ReleaseCreate,
    service: ReleaseService = Depends(get_release_service),
):
    return await service.create_release(body)


@router.get("/{release_id}", response_model=Release)
async def get_release(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    rel = await service.get_release(release_id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return rel


@router.patch("/{release_id}", response_model=Release)
async def update_release(
    release_id: str,
    body: ReleaseUpdate,
    service: ReleaseService = Depends(get_release_service),
):
    updated = await service.update_release(release_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return updated


@router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    deleted = await service.delete_release(release_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return None


@router.post("/{release_id}/gate-evaluate", response_model=ReleaseGateReport)
async def evaluate_release_gate(
    release_id: str,
    service: ReleaseService = Depends(get_release_service),
):
    try:
        return await service.evaluate_release_gate(release_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
