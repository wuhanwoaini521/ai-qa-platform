from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from project_model.models import Breakpoint, DebugSessionBootstrap, DebugSessionCreate, Permission, User
from qa_core.onboarding.contract import venv_interpreter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import authenticate_websocket_stream, get_current_user, has_permission, require_permission
from app.persistence.database import get_db
from app.persistence.models import BreakpointORM
from app.services.debug_session_service import debug_session_service, validate_debug_nodeid
from app.services.workspace_service import SecurityException, WorkspaceService

router = APIRouter(prefix="/debug", tags=["Python Debugger"])


@router.post("/sessions", response_model=DebugSessionBootstrap)
async def create_debug_session(
    payload: DebugSessionCreate,
    user: User = Depends(get_current_user),
    _: User = Depends(require_permission(Permission.RUN_EXECUTE)),
    session: AsyncSession = Depends(get_db),
) -> DebugSessionBootstrap:
    workspace_service = WorkspaceService()
    try:
        workspace_dir = workspace_service.get_workspace_dir(payload.workspace_id)
        nodeid = validate_debug_nodeid(workspace_dir, payload.nodeid)
    except (SecurityException, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not workspace_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found")

    result = await session.execute(
        select(BreakpointORM)
        .where(BreakpointORM.workspace_id == payload.workspace_id, BreakpointORM.enabled.is_(True))
        .order_by(BreakpointORM.file_path, BreakpointORM.line_number)
    )
    breakpoints = [Breakpoint.model_validate(row) for row in result.scalars().all()]
    target_interpreter = venv_interpreter(workspace_dir / ".qa-platform-runtime")
    try:
        return await debug_session_service.create(
            owner_id=user.id,
            workspace_id=payload.workspace_id,
            workspace_dir=workspace_dir,
            nodeid=nodeid,
            target_interpreter=target_interpreter,
            breakpoints=breakpoints,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.delete("/sessions/{session_id}")
async def close_debug_session(
    session_id: str,
    user: User = Depends(get_current_user),
    _: User = Depends(require_permission(Permission.RUN_EXECUTE)),
) -> dict[str, bool]:
    closed = await debug_session_service.close(session_id, user.id)
    if not closed:
        raise HTTPException(status_code=404, detail="Debug session not found")
    return {"closed": True}


@router.websocket("/sessions/{session_id}/stream")
async def debug_stream(websocket: WebSocket, session_id: str) -> None:
    user = await authenticate_websocket_stream(websocket, f"debug:{session_id}")
    if not user or not has_permission(user, Permission.RUN_EXECUTE):
        if user:
            await websocket.close(code=4403, reason="Run execution permission required")
        return
    session = await debug_session_service.get(session_id, user.id)
    if session is None or session.connected:
        await websocket.close(code=4404 if session is None else 4409, reason="Debug session unavailable")
        return

    session.connected = True
    receive_task: asyncio.Task | None = asyncio.create_task(websocket.receive_json())
    send_task: asyncio.Task | None = asyncio.create_task(session.outgoing.get())
    try:
        while True:
            done, _ = await asyncio.wait(
                {task for task in (receive_task, send_task) if task is not None},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if receive_task and receive_task in done:
                message = receive_task.result()
                try:
                    await debug_session_service.forward(session, message)
                except (ValueError, RuntimeError) as error:
                    await websocket.send_json(
                        {
                            "seq": 0,
                            "type": "response",
                            "request_seq": message.get("seq", 0),
                            "success": False,
                            "command": message.get("command", ""),
                            "message": str(error),
                        }
                    )
                receive_task = asyncio.create_task(websocket.receive_json())
            if send_task and send_task in done:
                await websocket.send_json(send_task.result())
                send_task = asyncio.create_task(session.outgoing.get())
    except WebSocketDisconnect:
        pass
    finally:
        for task in (receive_task, send_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (receive_task, send_task) if task), return_exceptions=True)
        session.connected = False
        await debug_session_service.close(session_id, user.id)
