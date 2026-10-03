"""Runtime is a Task/Run detail read, not another execution service."""

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import get_current_user
from app.persistence.database import get_db
from app.services.runtime_models import RuntimeSnapshot, RuntimeStepDetail
from app.services.runtime_projection import RuntimeProjection

router = APIRouter(tags=["Runtime Detail"])


@router.get("/tasks/{task_id}/runtime", response_model=RuntimeSnapshot)
@router.get("/agent-tasks/{task_id}/runtime", response_model=RuntimeSnapshot)
async def task_runtime(task_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    snapshot = await RuntimeProjection(session).task(task_id, str(user.id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return snapshot


@router.get("/runs/{run_id}/runtime", response_model=RuntimeSnapshot)
async def run_runtime(run_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    snapshot = await RuntimeProjection(session).run(run_id, str(user.id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Test Run not found")
    return snapshot


@router.get("/tasks/{task_id}/runtime/steps/{step_id}", response_model=RuntimeStepDetail)
async def runtime_step(
    task_id: str, step_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
):
    detail = await RuntimeProjection(session).step_detail(task_id, step_id, str(user.id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return detail
