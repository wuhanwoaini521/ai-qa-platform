from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from project_model.models import (
    Permission,
    User,
)

from app.api.authz import authenticate_websocket_stream, has_permission, require_permission
from app.container import get_recorder_workflow_service, recorder_service
from app.services.ai_runtime import build_ai_orchestrator
from app.services.recorder_service import (
    RecorderGenerateRequest,
    RecorderOptimization,
    RecorderSaveCaseRequest,
    RecorderSessionCreate,
    generate_python_case,
    normalize_recording_steps,
    validate_recording_optimization,
)
from app.services.recorder_workflow_service import RecorderWorkflowService

router = APIRouter(prefix="/recorder", tags=["Browser Recorder"])


@router.post("/sessions")
async def create_recorder_session(
    data: RecorderSessionCreate,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    workflow: RecorderWorkflowService = Depends(get_recorder_workflow_service),
):
    try:
        created = await workflow.create_session(user.id, data)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    status = recorder_service.session_status(created)
    return {
        "id": status["id"],
        "project_id": status["project_id"],
        "state": status["state"],
        "url": status["url"],
        "requested_url": status["requested_url"],
        "navigation_error": status["navigation_error"],
    }


@router.get("/sessions/{session_id}")
async def get_recorder_session(
    session_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    return recorder_service.session_status(session)


@router.post("/sessions/{session_id}/generate")
async def generate_case(
    session_id: str,
    request: RecorderGenerateRequest,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    return {"code": generate_python_case(request), "project_id": recorder_service.session_status(session)["project_id"]}


@router.post("/sessions/{session_id}/steps/{step_id}/ai-analysis")
async def analyze_recorder_locator(
    session_id: str,
    step_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    try:
        return await recorder_service.analyze_locator_with_ai(session, step_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503, detail=f"AI locator analysis unavailable ({type(error).__name__})"
        ) from error


@router.post("/sessions/{session_id}/steps/{step_id}/jev-decision")
async def decide_recorder_locator_with_jev(
    session_id: str,
    step_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    try:
        return await recorder_service.request_jev_locator_decision(session, step_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=503, detail=f"Jev locator decision unavailable ({type(error).__name__})"
        ) from error


@router.post("/sessions/{session_id}/save-case")
async def save_recorded_case(
    session_id: str,
    request: RecorderSaveCaseRequest,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    workflow: RecorderWorkflowService = Depends(get_recorder_workflow_service),
):
    try:
        return await workflow.save_case(session_id, user.id, request)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/sessions/{session_id}/optimize")
async def optimize_recording(
    session_id: str,
    request: RecorderGenerateRequest,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
):
    session = await recorder_service.get(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Recorder session not found")
    if not request.steps or len(request.steps) > 500:
        raise HTTPException(status_code=400, detail="Optimize between 1 and 500 recorded steps.")
    import json

    from qa_core.ai.models import AICompletionRequest
    from qa_core.prompts import RECORDER_OPTIMIZATION_PROMPT

    template = RECORDER_OPTIMIZATION_PROMPT
    try:
        private_values: dict[str, str] = {}
        private_markers: dict[str, str] = {}

        def mask(value):
            if value is None:
                return None
            if value not in private_markers:
                marker = f"__RECORDER_PRIVATE_{len(private_markers) + 1}__"
                private_markers[value] = marker
                private_values[marker] = value
            return private_markers[value]

        safe_steps = []
        for step in request.steps:
            updates = {
                "description": "",
                "evidence": None,
                "locator_decision": None,
                "value": mask(step.value),
                "url": mask(step.url),
                "key": mask(step.key),
                "frame_path": [mask(selector) for selector in step.frame_path],
            }
            if step.locator:
                updates["locator"] = step.locator.model_copy(
                    update={"value": mask(step.locator.value), "name": mask(step.locator.name)}
                )
            safe_steps.append(step.model_copy(update=updates))
        result = await build_ai_orchestrator().complete(
            AICompletionRequest(
                prompt=template.format(
                    steps=json.dumps([step.model_dump() for step in safe_steps], ensure_ascii=False)
                ),
                system_instruction=template.system_instruction,
                prompt_id=template.prompt_id,
                prompt_version=template.version,
                response_schema=RecorderOptimization,
                max_tokens=4000,
            )
        )
        if result.provider == "fake" or result.fallback_used:
            raise ValueError("A real AI provider is required for recording optimization.")
        proposal = RecorderOptimization.model_validate(result.structured_data)
        validate_recording_optimization(safe_steps, proposal.steps)
        original_steps = normalize_recording_steps(request.steps)
        optimized_steps = []
        for step, original in zip(proposal.steps, original_steps, strict=True):
            optimized_steps.append(
                step.model_copy(
                    update={
                        "id": original.id,
                        "description": original.description,
                        "evidence": original.evidence,
                        "locator_decision": original.locator_decision,
                        "value": private_values.get(step.value, step.value),
                        "url": private_values.get(step.url, step.url),
                        "key": private_values.get(step.key, step.key),
                        "frame_path": [private_values.get(selector, selector) for selector in step.frame_path],
                        "locator": step.locator.model_copy(
                            update={
                                "value": private_values.get(step.locator.value, step.locator.value),
                                "name": private_values.get(step.locator.name, step.locator.name),
                            }
                        )
                        if step.locator
                        else None,
                    }
                )
            )
        optimized = request.model_copy(update={"steps": optimized_steps})
        return {
            "raw_steps": request.steps,
            "optimized_steps": optimized_steps,
            "raw_code": generate_python_case(request),
            "optimized_code": generate_python_case(optimized),
            "reasons": proposal.reasons,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": template.version,
            "validated": False,
        }
    except Exception as error:
        raise HTTPException(
            status_code=422,
            detail=f"Recording optimization failed ({type(error).__name__}); raw recording was retained.",
        ) from error


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
    recorder_service.touch(session)
    last_steps_revision = -1
    try:
        while True:
            recorder_service.touch(session)
            frame = await recorder_service.page_snapshot(session)
            revision = frame.get("steps_revision")
            if revision == last_steps_revision:
                frame.pop("steps", None)
            elif revision is not None:
                last_steps_revision = revision
            await websocket.send_json(frame)
            try:
                command = await asyncio.wait_for(websocket.receive_json(), timeout=0.35)
            except asyncio.TimeoutError:
                continue
            action = command.get("action")
            try:
                current_url = await recorder_service.apply_command(session, command)
                if current_url is not None:
                    await websocket.send_json({"type": "command_success", "action": "navigate", "url": current_url})
            except Exception as error:
                if action == "navigate":
                    recorder_service.navigation_failed(session, str(error))
                await websocket.send_json(
                    {
                        "type": "command_error",
                        "message": str(error),
                        "url": command.get("url")
                        if action == "navigate"
                        else recorder_service.session_status(session)["url"],
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
