"""Runtime is a Task/Run detail read, not another execution service."""

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import User

from app.api.authz import get_current_user
from app.container import get_runtime_projection
from app.services.runtime_models import RuntimeSnapshot, RuntimeStepDetail
from app.services.runtime_projection import RuntimeProjection

router = APIRouter(tags=["Runtime Detail"])


@router.get("/tasks/{task_id}/runtime", response_model=RuntimeSnapshot)
@router.get("/agent-tasks/{task_id}/runtime", response_model=RuntimeSnapshot)
async def task_runtime(
    task_id: str,
    user: User = Depends(get_current_user),
    projection: RuntimeProjection = Depends(get_runtime_projection),
):
    snapshot = await projection.task(task_id, str(user.id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return snapshot


@router.get("/runs/{run_id}/runtime", response_model=RuntimeSnapshot)
async def run_runtime(
    run_id: str,
    user: User = Depends(get_current_user),
    projection: RuntimeProjection = Depends(get_runtime_projection),
):
    snapshot = await projection.run(run_id, str(user.id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return snapshot


@router.get("/tasks/{task_id}/runtime/steps/{step_id}", response_model=RuntimeStepDetail)
async def runtime_step(
    task_id: str,
    step_id: str,
    user: User = Depends(get_current_user),
    projection: RuntimeProjection = Depends(get_runtime_projection),
):
    detail = await projection.step_detail(task_id, step_id, str(user.id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return detail
