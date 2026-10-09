from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from project_model.models import (
    ApplyRepairRequest,
    FailureRecord,
    FailureRecurrenceItem,
    FailureRepairWorkflow,
    TestRun,
)
from qa_core.ai.models import FailureAnalysisResponse, LocatorSemanticReview
from qa_core.healing.models import LocatorRepairProposal

from app.container import get_failure_service, get_failure_workflow_service
from app.event_stream import event_frame
from app.services.failure_service import FailureService, LocatorRepairNotApplicableError
from app.services.failure_workflow_service import FailureWorkflowService

router = APIRouter(prefix="/failures", tags=["Failures & Healing"])


@router.get("", response_model=list[FailureRecord])
async def list_failures(
    project_id: str | None = Query(default=None, description="Only failures of this project's runs"),
    limit: int = Query(default=50, ge=1, le=200),
    service: FailureService = Depends(get_failure_service),
):
    return await service.list_failures(project_id=project_id, limit=limit)


@router.get("/{failure_id}", response_model=FailureRecord)
async def get_failure(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    f = await service.get_failure(failure_id)
    if not f:
        raise HTTPException(status_code=404, detail="Failure record not found")
    return f


@router.post("/{failure_id}/diagnose", response_model=FailureRecord)
async def diagnose_failure(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.diagnose_failure(failure_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{failure_id}/analyses")
async def list_failure_analyses(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    if await service.get_failure(failure_id) is None:
        raise HTTPException(status_code=404, detail="Failure record not found")
    return await workflow.list_history(failure_id)


@router.get("/{failure_id}/repair-workflow", response_model=FailureRepairWorkflow)
async def get_repair_workflow(
    failure_id: str,
    analysis_id: str | None = Query(default=None),
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        return await workflow.get_repair_workflow(failure_id, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{failure_id}/analyses/{analysis_id}/apply")
async def apply_analysis_repair(
    failure_id: str,
    analysis_id: str,
    payload: ApplyRepairRequest = Body(...),
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        return await workflow.apply_repair(failure_id, analysis_id, payload)
    except LocatorRepairNotApplicableError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyses/{analysis_id}/rollback")
async def rollback_analysis_repair(
    failure_id: str,
    analysis_id: str,
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        return await workflow.rollback_repair(failure_id, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyses/{analysis_id}/verification/run", response_model=TestRun)
async def start_analysis_verification(
    failure_id: str,
    analysis_id: str,
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        return await workflow.start_verification(failure_id, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyses/{analysis_id}/retry/run", response_model=TestRun)
async def start_failure_retry(
    failure_id: str,
    analysis_id: str,
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        return await workflow.start_retry(failure_id, analysis_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyses/{analysis_id}/verification")
async def link_analysis_verification(
    failure_id: str,
    analysis_id: str,
    run_id: str = Query(...),
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        await workflow.attach_verification(failure_id, analysis_id, run_id)
        return {"analysis_id": analysis_id, "run_id": run_id, "verified": False}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyze/stream")
async def stream_failure_workflow(
    failure_id: str,
    request: Request,
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
    language: str = Query(default="en"),
):
    if await service.get_failure(failure_id) is None:
        raise HTTPException(status_code=404, detail="Failure record not found")
    try:
        analysis_id, start_new_analysis = await workflow.start_analysis(failure_id)
    except ValueError as error:
        status_code = 404 if str(error) == "Failure record not found" else 409
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    async def events():
        response_language = "zh-CN" if language.lower().startswith("zh") else "en"
        stream = workflow.stream(
            failure_id,
            response_language=response_language,
            analysis_id=analysis_id,
            start_new_analysis=start_new_analysis,
        )
        try:
            async for event in stream:
                if await request.is_disconnected():
                    break
                yield event_frame(event.type, event)
        finally:
            await stream.aclose()

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/{failure_id}/diagnose-ai", response_model=FailureAnalysisResponse)
async def diagnose_failure_ai(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    """Diagnose failure root cause using AI reasoning with historical run context."""
    try:
        return await service.diagnose_failure_ai(failure_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI failure diagnosis failed: {e}")


@router.post("/{failure_id}/diagnose-ai/stream")
async def stream_failure_diagnosis(
    failure_id: str,
    request: Request,
    service: FailureService = Depends(get_failure_service),
):
    if await service.get_failure(failure_id) is None:
        raise HTTPException(status_code=404, detail="Failure record not found")

    async def events():
        stream = service.stream_diagnosis(failure_id)
        try:
            async for event in stream:
                if await request.is_disconnected():
                    break
                yield event_frame(event.type, event)
        finally:
            await stream.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{failure_id}/repair-proposal", response_model=LocatorRepairProposal)
async def generate_repair_proposal(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.generate_repair_proposal(failure_id)
    except LocatorRepairNotApplicableError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{failure_id}/semantic-review", response_model=LocatorSemanticReview)
async def review_semantic_repair(
    failure_id: str,
    candidate_locator: str | None = Query(default=None),
    service: FailureService = Depends(get_failure_service),
):
    """Review proposed locator repair for semantic equivalence."""
    try:
        return await service.review_semantic_repair(failure_id, candidate_locator=candidate_locator)
    except LocatorRepairNotApplicableError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic review failed: {e}")


@router.get("/{failure_id}/recurrence", response_model=list[FailureRecurrenceItem])
async def get_failure_recurrence(
    failure_id: str,
    service: FailureService = Depends(get_failure_service),
):
    """Find previous similar failures for the same test nodeid and classification."""
    try:
        return await service.get_recurrence(failure_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{failure_id}/apply-repair")
async def apply_repair_proposal(
    failure_id: str,
    workspace_id: str = Query(..., description="Target workspace ID"),
    payload: ApplyRepairRequest = Body(...),
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        state = await workflow.get_repair_workflow(failure_id)
        if not state.analysis_id:
            raise ValueError("No repair analysis exists for this failure")
        return await workflow.apply_repair(
            failure_id,
            state.analysis_id,
            payload,
            expected_workspace_id=workspace_id,
        )
    except LocatorRepairNotApplicableError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{failure_id}/rollback-repair")
async def rollback_repair(
    failure_id: str,
    workspace_id: str = Query(..., description="Target workspace ID"),
    service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
):
    try:
        state = await workflow.get_repair_workflow(failure_id)
        if not state.analysis_id:
            raise ValueError("No repair analysis exists for this failure")
        return await workflow.rollback_repair(
            failure_id,
            state.analysis_id,
            expected_workspace_id=workspace_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
