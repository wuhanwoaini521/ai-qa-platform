from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from project_model.models import (
    ApplyRepairRequest,
    FailureRecord,
    FailureRecurrenceItem,
)
from qa_core.ai.models import FailureAnalysisResponse, LocatorSemanticReview
from qa_core.healing.models import LocatorRepairProposal
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.event_stream import event_frame
from app.persistence.database import get_db
from app.repositories.ai_repo import AIRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.failure_service import FailureService, LocatorRepairNotApplicableError
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/failures", tags=["Failures & Healing"])


def get_failure_service(session: AsyncSession = Depends(get_db)) -> FailureService:
    run_repo = TestRunRepository(session)
    workspace_repo = WorkspaceRepository(session)
    workspace_service = WorkspaceService()
    # RunHistoryRepository manages its own session context; keep it separate from this request's
    # session so history reads cannot detach ORM rows that the failure service later updates.
    history_repo = RunHistoryRepository()
    # Invocation telemetry owns its transaction; keep the request session attached to its ORM rows.
    ai_repo = AIRepository()
    return FailureService(
        run_repo=run_repo,
        workspace_repo=workspace_repo,
        workspace_service=workspace_service,
        history_repo=history_repo,
        ai_repo=ai_repo,
    )


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
async def list_failure_analyses(failure_id: str, service: FailureService = Depends(get_failure_service)):
    if await service.get_failure(failure_id) is None:
        raise HTTPException(status_code=404, detail="Failure record not found")
    return await FailureWorkflowService(service).list_history(failure_id)


@router.post("/{failure_id}/analyses/{analysis_id}/verification")
async def link_analysis_verification(
    failure_id: str, analysis_id: str, run_id: str = Query(...), service: FailureService = Depends(get_failure_service)
):
    try:
        await FailureWorkflowService(service).attach_verification(failure_id, analysis_id, run_id)
        return {"analysis_id": analysis_id, "run_id": run_id, "verified": False}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{failure_id}/analyze/stream")
async def stream_failure_workflow(
    failure_id: str, request: Request, service: FailureService = Depends(get_failure_service)
):
    if await service.get_failure(failure_id) is None:
        raise HTTPException(status_code=404, detail="Failure record not found")

    async def events():
        stream = FailureWorkflowService(service).stream(failure_id)
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
    payload: ApplyRepairRequest = ...,
    service: FailureService = Depends(get_failure_service),
):
    try:
        return await service.apply_repair(workspace_id, payload, failure_id=failure_id)
    except LocatorRepairNotApplicableError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
