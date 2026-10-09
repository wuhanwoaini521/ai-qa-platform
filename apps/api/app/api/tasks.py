from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from project_model.models import User
from project_model.task_models import (
    Task,
    TaskApprovalRequest,
    TaskCreate,
    TaskDetail,
    TaskGoalPreview,
)

from app.api.authz import get_current_user
from app.container import get_task_event_service, get_task_runtime_service
from app.event_stream import event_frame
from app.services.api_read_service import TaskEventService
from app.services.task_command_service import TaskCommandService

router = APIRouter(prefix="/tasks", tags=["Agent Tasks"])
task_runtime_service = get_task_runtime_service()
task_command_service = task_runtime_service.commands
task_execution_service = task_runtime_service.execution
task_scheduler_service = task_runtime_service.scheduler


def get_task_command_service(request: Request) -> TaskCommandService:
    runtime = getattr(request.app.state, "task_runtime", task_runtime_service)
    return runtime.commands


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> Task:
    try:
        return await runtime.create(data, str(user.id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/preview", response_model=TaskGoalPreview)
async def preview_task_goal(
    data: TaskCreate,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskGoalPreview:
    try:
        return await runtime.preview_goal(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("", response_model=list[Task])
async def list_tasks(
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> list[Task]:
    return await runtime.list(str(user.id), project_id=project_id, limit=limit)


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskDetail:
    detail = await runtime.get(task_id, str(user.id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@router.post("/{task_id}/approval", response_model=TaskDetail)
async def decide_task_approval(
    task_id: str,
    request: TaskApprovalRequest,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskDetail:
    detail = await runtime.approve(task_id, str(user.id), request)
    if detail is None:
        raise HTTPException(status_code=409, detail="Task is not waiting for an approval decision")
    return detail


@router.post("/{task_id}/pause", response_model=TaskDetail)
async def pause_task(
    task_id: str,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskDetail:
    detail = await runtime.pause(task_id, str(user.id))
    if detail is None:
        raise HTTPException(status_code=409, detail="Task cannot be paused in its current state")
    return detail


@router.post("/{task_id}/resume", response_model=TaskDetail)
async def resume_task(
    task_id: str,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskDetail:
    try:
        detail = await runtime.resume(task_id, str(user.id))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if detail is None:
        raise HTTPException(status_code=409, detail="Task is not paused")
    return detail


@router.post("/{task_id}/cancel", response_model=Task)
async def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> Task:
    result = await runtime.cancel(task_id, str(user.id))
    if result is None:
        raise HTTPException(status_code=409, detail="Task does not exist or is already terminal")
    detail = await runtime.get(task_id, str(user.id))
    assert detail is not None
    return detail


@router.post("/{task_id}/replan", response_model=TaskDetail)
async def replan_task(
    task_id: str,
    instructions: str = Query(min_length=1, max_length=4000),
    user: User = Depends(get_current_user),
    runtime: TaskCommandService = Depends(get_task_command_service),
) -> TaskDetail:
    try:
        detail = await runtime.replan(task_id, str(user.id), instructions)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if detail is None:
        raise HTTPException(status_code=409, detail="Only failed or blocked tasks can be replanned")
    return detail


async def _task_event_stream(
    task_id: str,
    owner_id: str,
    after_id: int,
    service: TaskEventService,
) -> AsyncGenerator[str, None]:
    cursor = after_id
    while True:
        batch = await service.read_after(task_id, owner_id, cursor)
        if batch is None:
            return
        for payload in batch.events:
            cursor = payload["id"]
            yield event_frame("message", payload, event_id=payload["id"])
        if service.is_terminal(batch.status) and not batch.events:
            return
        if not batch.events:
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    service: TaskEventService = Depends(get_task_event_service),
) -> StreamingResponse:
    if not await service.exists(task_id, str(user.id)):
        raise HTTPException(status_code=404, detail="Task not found")
    # EventSource reconnects with Last-Event-ID. The query parameter also supports clients
    # that cannot set custom request headers.
    cursor = after
    header_cursor = request.headers.get("last-event-id")
    raw_cursor = header_cursor or request.query_params.get("last_event_id")
    if raw_cursor:
        try:
            cursor = max(cursor, int(raw_cursor))
        except ValueError:
            raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer")
    return StreamingResponse(
        _task_event_stream(task_id, str(user.id), cursor, service),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
