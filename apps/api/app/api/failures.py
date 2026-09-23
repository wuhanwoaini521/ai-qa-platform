from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import ApplyRepairRequest, FailureRecord
from qa_core.healing.models import LocatorRepairProposal
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.failure_service import FailureService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/failures", tags=["Failures & Healing"])


def get_failure_service(session: AsyncSession = Depends(get_db)) -> FailureService:
    run_repo = TestRunRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace_service = WorkspaceService()
    return FailureService(run_repo, workspace_repo, workspace_service)


@router.get("", response_model=list[FailureRecord])
async def list_failures(
    service: FailureService = Depends(get_failure_service),
):
    return await service.list_failures()


@router.get("/{failure_id}", response_model=FailureRecord)
async def get_failure(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    f = await service.get_failure(failure_id)
    if not f:
        raise HTTPException(status_code=404, detail="Failure record not found")
    return f


@router.post("/{failure_id}/diagnose", response_model=FailureRecord)
async def diagnose_failure(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.diagnose_failure(failure_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{failure_id}/repair-proposal", response_model=LocatorRepairProposal)
async def generate_repair_proposal(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.generate_repair_proposal(failure_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{failure_id}/apply-repair")
async def apply_repair_proposal(
    failure_id: str,
    workspace_id: str = Query(..., description="Target workspace ID"),
    payload: ApplyRepairRequest = ...,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.apply_repair(workspace_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
