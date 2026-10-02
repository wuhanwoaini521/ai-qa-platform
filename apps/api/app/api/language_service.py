from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from project_model.models import Permission

from app.api.authz import authenticate_websocket_stream, has_permission
from app.services.python_language_service import PythonLanguageService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Python Language Service"])
_active_sessions: dict[str, int] = {}


@router.websocket("/{workspace_id}/lsp/stream")
async def language_stream(websocket: WebSocket, workspace_id: str):
    user = await authenticate_websocket_stream(websocket, f"lsp:{workspace_id}")
    if not user or not has_permission(user, Permission.PROJECT_READ):
        if user:
            await websocket.close(code=4403)
        return
    workspace = WorkspaceService().get_workspace_dir(workspace_id)
    if not workspace.is_dir():
        await websocket.close(code=4404)
        return
    user_key = str(user.id)
    if sum(_active_sessions.values()) >= 8 or _active_sessions.get(user_key, 0) >= 2:
        await websocket.close(code=4429, reason="Python language service session limit reached")
        return
    _active_sessions[user_key] = _active_sessions.get(user_key, 0) + 1
    service = PythonLanguageService(workspace, workspace_id)
    incoming = outgoing = None
    try:
        await service.start()
        incoming = asyncio.create_task(websocket.receive_json())
        outgoing = asyncio.create_task(service.read())
        while True:
            done, _ = await asyncio.wait({incoming, outgoing}, return_when=asyncio.FIRST_COMPLETED)
            if incoming in done:
                message = incoming.result()
                try:
                    await service.forward(message)
                except (ValueError, RuntimeError) as error:
                    if "id" in message:
                        await websocket.send_json(
                            {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": str(error)}}
                        )
                incoming = asyncio.create_task(websocket.receive_json())
            if outgoing in done:
                await websocket.send_json(outgoing.result())
                outgoing = asyncio.create_task(service.read())
    except WebSocketDisconnect:
        pass
    except Exception as error:
        try:
            await websocket.send_json(
                {
                    "jsonrpc": "2.0",
                    "method": "window/logMessage",
                    "params": {"type": 1, "message": f"Python language service stopped: {type(error).__name__}"},
                }
            )
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        for task in (incoming, outgoing):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (incoming, outgoing) if task), return_exceptions=True)
        try:
            await service.close()
        finally:
            _active_sessions[user_key] -= 1
            if not _active_sessions[user_key]:
                del _active_sessions[user_key]
