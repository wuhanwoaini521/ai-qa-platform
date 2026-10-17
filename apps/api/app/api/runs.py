from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from project_model.models import Permission, TestRun, TestRunCreate, User

from app.api.authz import get_current_user, require_permission
from app.api.project_acl import enforce_project_access, run_access, visible_project_ids
from app.container import get_run_service
from app.container import open_run_service as _open_run_service
from app.event_stream import event_frame
from app.services.test_run_service import TestRunService

open_run_service = _open_run_service

router = APIRouter(prefix="/runs", tags=["Test Runs"])


@router.get("", response_model=list[TestRun])
async def list_runs(
    project_id: str | None = None,
    service: TestRunService = Depends(get_run_service),
    user: User = Depends(get_current_user),
):
    if project_id:
        await enforce_project_access(user, project_id)
        return await service.list_runs(project_id=project_id)
    allowed = await visible_project_ids(user)
    runs = await service.list_runs()
    if allowed is None:
        return runs
    return [run for run in runs if run.project_id in allowed]


@router.post("", response_model=TestRun, status_code=status.HTTP_201_CREATED)
async def trigger_test_run(
    data: TestRunCreate,
    service: TestRunService = Depends(get_run_service),
    user: User = Depends(get_current_user),
):
    await enforce_project_access(user, data.project_id)
    try:
        return await service.create_and_execute_run(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{run_id}", response_model=TestRun, dependencies=[Depends(run_access)])
async def get_run(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return run


@router.post("/recover-stale", dependencies=[Depends(require_permission(Permission.SECURITY_ADMIN))])
async def recover_stale_runs(
    stale_after_seconds: float = Query(7200.0, ge=60),
    service: TestRunService = Depends(get_run_service),
) -> dict[str, list[str]]:
    """Close runs that were abandoned mid-flight so they never stay RUNNING forever."""
    recovered = await service.recover_stale_runs(stale_after_seconds=stale_after_seconds)
    return {"recovered_run_ids": recovered}


@router.post("/{run_id}/cancel", response_model=TestRun, dependencies=[Depends(run_access)])
async def cancel_run(
    run_id: str,
    service: TestRunService = Depends(get_run_service),
):
    run = await service.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return run


@router.get("/{run_id}/events", dependencies=[Depends(run_access)])
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
