from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from project_model.models import Permission, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import authenticate_websocket_stream, has_permission, require_permission
from app.persistence.database import get_db
from app.repositories.project_repo import ProjectRepository
from app.services.recorder_service import (
    RecorderGenerateRequest,
    RecorderSessionCreate,
    generate_python_case,
    recorder_service,
)

router = APIRouter(prefix="/recorder", tags=["Browser Recorder"])


@router.post("/sessions")
async def create_recorder_session(
    data: RecorderSessionCreate,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    session: AsyncSession = Depends(get_db),
):
    if not await ProjectRepository(session).get_by_id(data.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        created = await recorder_service.create_session(user.id, data)
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "id": created.id,
        "project_id": created.project_id,
        "state": created.state,
        "url": created.page.url,
        "requested_url": created.requested_url,
        "navigation_error": created.navigation_error,
    }


@router.get("/sessions/{session_id}")
async def get_recorder_session(
    session_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    return {
        "id": session.id,
        "project_id": session.project_id,
        "state": session.state,
        "url": session.page.url,
        "requested_url": session.requested_url,
        "navigation_error": session.navigation_error,
        "steps": session.steps,
    }


@router.post("/sessions/{session_id}/generate")
async def generate_case(
    session_id: str,
    request: RecorderGenerateRequest,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    return {"code": generate_python_case(request), "project_id": session.project_id}


@router.delete("/sessions/{session_id}")
async def close_recorder_session(
    session_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    await recorder_service.close(session_id, user.id)
    return {"closed": True}


@router.websocket("/sessions/{session_id}/stream")
async def recorder_stream(websocket: WebSocket, session_id: str):
    user = await authenticate_websocket_stream(websocket, f"recorder:{session_id}")
    if not user or not has_permission(user, Permission.AUTOMATION_EDIT):
        if user:
            await websocket.close(code=4403, reason="Recorder permission required")
        return
    session = await recorder_service.get(session_id, user.id)
    if not session:
        await websocket.close(code=4404, reason="Recorder session not found")
        return
    session.last_activity = asyncio.get_running_loop().time()
    try:
        while True:
            session.last_activity = asyncio.get_running_loop().time()
            frame = await recorder_service.page_snapshot(session)
            await websocket.send_json(frame)
            try:
                command = await asyncio.wait_for(websocket.receive_json(), timeout=0.35)
            except asyncio.TimeoutError:
                continue
            action = command.get("action")
            page = session.page
            try:
                if action == "navigate":
                    target = RecorderSessionCreate(project_id=session.project_id, start_url=command["url"]).start_url
                    session.requested_url = target
                    await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                    session.navigation_error = None
                    await websocket.send_json({"type": "command_success", "action": "navigate", "url": page.url})
                elif action == "back":
                    await page.go_back(wait_until="domcontentloaded", timeout=15000)
                elif action == "forward":
                    await page.go_forward(wait_until="domcontentloaded", timeout=15000)
                elif action == "reload":
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                elif action == "start":
                    session.state = "RECORDING"
                    if not session.steps:
                        session.steps.extend(
                            recorder_service.events_to_steps([{"action": "navigate", "url": page.url}])
                        )
                    for frame in page.frames:
                        await frame.evaluate("() => {window.__qaRecorderEnabled=true; window.__qaRecorderEvents=[]}")
                elif action == "pause":
                    session.state = "PAUSED"
                elif action == "resume":
                    session.state = "RECORDING"
                elif action == "stop":
                    session.state = "STOPPED"
                elif action == "click":
                    await page.mouse.click(command["x"], command["y"])
                elif action == "double_click":
                    await page.mouse.dblclick(command["x"], command["y"])
                elif action == "move":
                    await page.mouse.move(command["x"], command["y"])
                elif action == "pick_element":
                    requested_action = command.get("step_action")
                    session.pending_pick_action = (
                        requested_action
                        if requested_action
                        in {"click", "double_click", "fill", "select", "check", "uncheck", "press", "hover"}
                        else "click"
                    )
                    for frame in page.frames:
                        await frame.evaluate(
                            "() => { window.__qaRecorderPickMode = true; window.__qaRecorderEnabled = true; }"
                        )
                elif action == "wheel":
                    await page.mouse.wheel(command.get("delta_x", 0), command.get("delta_y", 0))
                elif action == "type":
                    await page.keyboard.insert_text(command.get("text", ""))
                elif action == "press":
                    await page.keyboard.press(command["key"])
                elif action == "tab":
                    index = int(command["index"])
                    pages = session.context.pages
                    if 0 <= index < len(pages):
                        session.page = pages[index]
                elif action == "add_step":
                    from app.services.recorder_service import RecorderStep

                    session.steps.append(RecorderStep.model_validate(command["step"]).model_dump(mode="json"))
                elif action == "edit_step":
                    from app.services.recorder_service import RecorderStep

                    updated = RecorderStep.model_validate(command["step"]).model_dump(mode="json")
                    session.steps = [updated if step["id"] == updated["id"] else step for step in session.steps]
                elif action == "delete_step":
                    session.steps = [step for step in session.steps if step["id"] != command.get("id")]
                elif action == "reorder":
                    order = command.get("ids", [])
                    by_id = {step["id"]: step for step in session.steps}
                    session.steps = [by_id[item] for item in order if item in by_id] + [
                        step for step in session.steps if step["id"] not in order
                    ]
                session.last_activity = asyncio.get_running_loop().time()
            except Exception as error:
                if action == "navigate":
                    session.navigation_error = str(error)
                await websocket.send_json(
                    {
                        "type": "command_error",
                        "message": str(error),
                        "url": command.get("url") if action == "navigate" else page.url,
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
