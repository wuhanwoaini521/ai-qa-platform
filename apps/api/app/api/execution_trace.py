from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.execution_trace import ExecutionTrace
from project_model.models import User

from app.api.authz import get_current_user
from app.api.project_acl import enforce_project_access
from app.container import get_execution_trace_service
from app.services.execution_trace_service import ExecutionTraceService

router = APIRouter(tags=["Execution Trace"])


@router.get("/tasks/{task_id}/execution-trace", response_model=ExecutionTrace)
async def get_task_execution_trace(
    task_id: str,
    user: User = Depends(get_current_user),
    service: ExecutionTraceService = Depends(get_execution_trace_service),
) -> ExecutionTrace:
    """Read-only tree of what this task actually executed.

    Every node is a stored row; facts the server cannot establish are reported as unknown rather
    than filled in. Nothing here starts, retries or cancels anything.
    """
    trace = await service.for_task(task_id, str(user.id))
    if trace is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return trace


@router.get("/projects/{project_id}/execution-trace", response_model=ExecutionTrace)
async def get_project_execution_trace(
    project_id: str,
    limit: int = Query(default=6, ge=1, le=20),
    user: User = Depends(get_current_user),
    service: ExecutionTraceService = Depends(get_execution_trace_service),
) -> ExecutionTrace:
    """The same projection for the most recent tasks of a project, several roots side by side."""
    await enforce_project_access(user, project_id)
    return await service.for_project(project_id, str(user.id), limit=limit)
