from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from project_model.models import DebugSessionBootstrap, DebugSessionCreate, Permission, User
from qa_core.onboarding.contract import venv_interpreter

from app.api.authz import authenticate_websocket_stream, get_current_user, has_permission, require_permission
from app.api.workspace_dependencies import get_workspace_catalog_service
from app.services.debug_session_service import debug_session_service, validate_debug_nodeid
from app.services.workspace_catalog_service import WorkspaceCatalogService
from app.services.workspace_service import SecurityException, WorkspaceService
from app.settings import get_config

router = APIRouter(prefix="/debug", tags=["Python Debugger"])


@router.post("/sessions", response_model=DebugSessionBootstrap)
async def create_debug_session(
    payload: DebugSessionCreate,
    user: User = Depends(get_current_user),
    _: User = Depends(require_permission(Permission.RUN_EXECUTE)),
    catalog: WorkspaceCatalogService = Depends(get_workspace_catalog_service),
) -> DebugSessionBootstrap:
    if not get_config().features.debugger:
        raise HTTPException(status_code=503, detail="Debugger is disabled by config/config.yaml.")
    workspace_service = WorkspaceService()
    try:
        workspace_dir = workspace_service.get_workspace_dir(payload.workspace_id)
        nodeid = validate_debug_nodeid(workspace_dir, payload.nodeid)
    except (SecurityException, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not workspace_dir.is_dir():
        raise HTTPException(status_code=404, detail="Workspace not found")

    lineage = (
        await debug_session_service.failure_lineage(
            failure_id=payload.failure_id,
            workspace_id=payload.workspace_id,
            nodeid=nodeid,
        )
        if payload.failure_id
        else None
    )
    if payload.failure_id and lineage is None:
        raise HTTPException(status_code=404, detail="Failure execution not found for this debug target")
    run_id = lineage["run_id"] if lineage else None
    execution_id = lineage["execution_id"] if lineage else None
    failure_id = lineage["failure_id"] if lineage else None

    breakpoints = await catalog.list_enabled_breakpoints(payload.workspace_id)
    target_interpreter = venv_interpreter(workspace_dir / ".qa-platform-runtime")
    try:
        return await debug_session_service.create(
            owner_id=user.id,
            workspace_id=payload.workspace_id,
            workspace_dir=workspace_dir,
            nodeid=nodeid,
            target_interpreter=target_interpreter,
            breakpoints=breakpoints,
            run_id=run_id,
            execution_id=execution_id,
            failure_id=failure_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/sessions/{session_id}", response_model=DebugSessionBootstrap)
async def get_debug_session(
    session_id: str,
    user: User = Depends(get_current_user),
    _: User = Depends(require_permission(Permission.RUN_EXECUTE)),
) -> DebugSessionBootstrap:
    session = await debug_session_service.get_record(session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Debug session not found")
    return session


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
    if not get_config().features.debugger:
        await websocket.close(code=4403, reason="Debugger is disabled by config/config.yaml")
        return
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
    await debug_session_service.activate(session_id)
    try:
        first_message = await asyncio.wait_for(
            websocket.receive_json(), timeout=get_config().debugger.attach_timeout_seconds
        )
    except asyncio.TimeoutError:
        await debug_session_service.close(session_id, user.id)
        await websocket.close(code=4408, reason="Debug client did not attach before the configured timeout")
        return
    except WebSocketDisconnect:
        await debug_session_service.close(session_id, user.id)
        return
    try:
        await debug_session_service.forward(session, first_message)
    except (ValueError, RuntimeError) as error:
        await websocket.send_json(
            {
                "seq": 0,
                "type": "response",
                "request_seq": first_message.get("seq", 0),
                "success": False,
                "command": first_message.get("command", ""),
                "message": str(error),
            }
        )
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
