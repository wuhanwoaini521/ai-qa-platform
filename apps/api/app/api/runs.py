from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from project_model.models import TestRun, TestRunCreate
from sqlalchemy.ext.asyncio import AsyncSession

from app.event_stream import event_frame
from app.persistence.database import async_session_factory, get_db
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.test_run_service import TestRunService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/runs", tags=["Test Runs"])


def get_run_service(session: AsyncSession = Depends(get_db)) -> TestRunService:
    """Build the run service from a session.

    Also callable outside the request cycle. `lifespan` startup recovery needs the same wiring but
    has no resolved dependency to pass, so a missing session means "open one and close it" rather
    than handing the Depends marker to the repository.
    """
    if not isinstance(session, AsyncSession):
        raise RuntimeError("get_run_service requires a real AsyncSession, not a Depends marker")
    run_repo = TestRunRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace_service = WorkspaceService()
    return TestRunService(run_repo, workspace_repo, workspace_service)


@asynccontextmanager
async def open_run_service() -> AsyncGenerator[TestRunService, None]:
    """A run service bound to its own session, for use outside the request lifecycle."""
    async with async_session_factory() as session:
        yield get_run_service(session)


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
    try:
        return await service.create_and_execute_run(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{run_id}", response_model=TestRun)
async def get_run(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return run


@router.post("/recover-stale")
async def recover_stale_runs(
    stale_after_seconds: float = 7200.0,
    service: TestRunService = Depends(get_run_service),
) -> dict[str, list[str]]:
    """Close runs that were abandoned mid-flight so they never stay RUNNING forever."""
    recovered = await service.recover_stale_runs(stale_after_seconds=stale_after_seconds)
    return {"recovered_run_ids": recovered}


@router.post("/{run_id}/cancel", response_model=TestRun)
async def cancel_run(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.cancel_run(run_id)
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

    async def events():
        stream = service.event_generator(run_id)
        try:
            async for event in stream:
                yield event_frame("message", event)
        finally:
            await stream.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
