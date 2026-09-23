from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from project_model.models import TestRun, TestRunCreate
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.test_run_service import TestRunService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/runs", tags=["Test Runs"])


def get_run_service(session: AsyncSession = Depends(get_db)) -> TestRunService:
    run_repo = TestRunRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace_service = WorkspaceService()
    return TestRunService(run_repo, workspace_repo, workspace_service)


@router.get("", response_model=list[TestRun])
async def list_runs(
    project_id: str | None = None,
    service: TestRunService = Depends(get_run_service),
):
    return await service.list_runs(project_id=project_id)


@router.post("", response_model=TestRun, status_code=status.HTTP_201_CREATED)
async def trigger_test_run(
    data: TestRunCreate,
    service: TestRunService = Depends(get_run_service),
):
    return await service.create_and_execute_run(data)


@router.get("/{run_id}", response_model=TestRun)
async def get_run(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return run


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test Run not found")

    return StreamingResponse(
        service.event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
