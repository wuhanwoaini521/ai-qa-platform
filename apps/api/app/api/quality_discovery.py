from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from project_model.models import Permission, User, UserRole
from project_model.task_models import Task

from app.api.authz import get_current_user, require_permission
from app.api.project_acl import (
    discovery_run_access,
    enforce_project_access,
    project_query_access,
)
from app.container import get_discovery_evidence_service, get_quality_discovery_service
from app.services.discovery_evidence_service import DiscoveryEvidenceNotFound, DiscoveryEvidenceService
from app.services.quality_discovery_service import (
    DiscoveryRunCreate,
    QualityDiscoveryService,
    discovery_run_dict,
)

router = APIRouter(
    prefix="/discovery",
    tags=["Quality Discovery"],
    dependencies=[Depends(discovery_run_access), Depends(project_query_access("project_id"))],
)


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_discovery_run(
    data: DiscoveryRunCreate,
    user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    await enforce_project_access(user, data.project_id)
    try:
        run = await service.create(data, str(user.id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return discovery_run_dict(run)


@router.get("/runs")
async def list_discovery_runs(
    project_id: str = Query(min_length=1, max_length=36),
    limit: int = Query(default=25, ge=1, le=100),
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    return [discovery_run_dict(row) for row in await service.list(project_id, limit)]


@router.get("/runs/{run_id}")
async def get_discovery_run(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return discovery_run_dict(run)


@router.get("/runs/{run_id}/features")
async def get_discovery_features(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("features", [])


@router.get("/runs/{run_id}/gaps")
async def get_discovery_gaps(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("gaps", [])


@router.post(
    "/runs/{run_id}/coverage/refresh",
    responses={
        403: {"description": "Insufficient permissions"},
        404: {"description": "Quality Discovery run not found"},
        409: {"description": "Discovery run is not terminal"},
    },
)
async def refresh_discovery_coverage(
    run_id: str,
    user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    await require_permission(Permission.RUN_EXECUTE)(user)
    current = await service.get(run_id)
    if current is None or (current.requested_by != str(user.id) and user.role != UserRole.ADMIN):
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    try:
        run = await service.refresh_quality_map(run_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return discovery_run_dict(run)


@router.get("/runs/{run_id}/coverage")
async def get_discovery_coverage(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("coverage", [])


@router.get("/runs/{run_id}/quality-map")
async def get_discovery_quality_map(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("quality_map", {})


@router.get("/runs/{run_id}/states")
async def get_discovery_states(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("states", [])


@router.get("/runs/{run_id}/events")
async def get_discovery_events(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return (run.result.get("events", []) or [])[-limit:]


@router.get("/runs/{run_id}/stream")
async def stream_discovery_run(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    """Live view of one run: persisted history first, then live events interleaved with browser frames."""
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return StreamingResponse(
        service.event_generator(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/journeys")
async def get_discovery_journeys(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("journeys", [])


@router.get("/runs/{run_id}/functional-spec")
async def get_discovery_functional_specification(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Quality Discovery run not found")
    return run.result.get("functional_spec", {})


@router.post("/runs/{run_id}/gaps/{gap_id}/actions/{action}")
async def execute_discovery_gap_action(
    run_id: str,
    gap_id: str,
    action: str,
    user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    permissions = {
        "create_requirement_draft": (Permission.REQUIREMENT_WRITE,),
        "generate_tests": (Permission.REQUIREMENT_WRITE, Permission.TEST_CASE_WRITE),
        "generate_automation": (Permission.AUTOMATION_EDIT,),
        "open_failure": (),
    }
    if action not in permissions:
        raise HTTPException(status_code=422, detail="Unsupported Quality Gap action")
    try:
        for permission in permissions[action]:
            await require_permission(permission)(user)
        return await service.act_on_gap(run_id, gap_id, action)
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        from app.services.quality_discovery_service import DiscoveryBlocked

        if isinstance(error, DiscoveryBlocked):
            raise HTTPException(status_code=409, detail=str(error)) from error
        raise HTTPException(
            status_code=502,
            detail=f"Quality Gap action failed ({type(error).__name__}). See AI Usage for invocation status.",
        ) from error


@router.post(
    "/runs/{run_id}/journeys/{journey_id}/pytest-draft",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Task,
)
async def create_discovery_pytest_draft(
    run_id: str,
    journey_id: str,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
) -> Task:
    try:
        return await service.create_pytest_draft(run_id, journey_id, str(user.id))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/runs/{run_id}/pause")
async def pause_discovery_run(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.pause(run_id)
    if run is None:
        raise HTTPException(status_code=409, detail="Discovery run cannot be paused in its current state")
    return discovery_run_dict(run)


@router.post("/runs/{run_id}/resume")
async def resume_discovery_run(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.resume(run_id)
    if run is None:
        raise HTTPException(status_code=409, detail="Discovery run is not paused")
    return discovery_run_dict(run)


@router.post("/runs/{run_id}/stop")
async def stop_discovery_run(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: QualityDiscoveryService = Depends(get_quality_discovery_service),
):
    run = await service.stop(run_id)
    if run is None:
        raise HTTPException(status_code=409, detail="Discovery run cannot be stopped")
    return discovery_run_dict(run)


@router.get("/runs/{run_id}/evidence")
async def list_discovery_evidence(
    run_id: str,
    kind: str | None = Query(default=None, max_length=30),
    state_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=200, ge=1, le=1000),
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    """The structured facts this run captured, filterable by kind and state."""
    try:
        return await service.list_evidence(run_id, kind=kind, state_id=state_id, limit=limit)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/evidence/summary")
async def get_discovery_evidence_summary(
    run_id: str,
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    """Raw, deduped, filtered and associated counts — each with the rule that produced it."""
    try:
        return await service.collection(run_id)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/evidence/diff")
async def get_discovery_evidence_diff(
    run_id: str,
    against: str | None = Query(default=None, max_length=36),
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    """What changed between this run and an earlier run of the same start URL."""
    try:
        return await service.diff(run_id, against)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/evidence/{evidence_id}")
async def get_discovery_evidence(
    run_id: str,
    evidence_id: str,
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    try:
        return await service.evidence_detail(run_id, evidence_id)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/runs/{run_id}/scenarios")
async def list_discovery_scenarios(
    run_id: str,
    _user: User = Depends(get_current_user),
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    try:
        return await service.scenarios(run_id)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/runs/{run_id}/scenarios/refresh")
async def refresh_discovery_scenarios(
    run_id: str,
    user: User = Depends(get_current_user),
    service: DiscoveryEvidenceService = Depends(get_discovery_evidence_service),
):
    """Re-derive candidate scenarios from evidence and match them to existing test cases."""
    await require_permission(Permission.RUN_EXECUTE)(user)
    try:
        return await service.refresh_scenarios(run_id)
    except DiscoveryEvidenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
