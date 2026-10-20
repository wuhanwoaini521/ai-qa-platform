"""Lifecycle projections and structured workflows over the existing domain entities."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from project_model.models import Permission

from app.api.authz import require_permission
from app.api.project_acl import project_path_access
from app.container import (
    get_golden_demo_service,
    get_project_knowledge_service,
    get_requirement_lifecycle_service,
)
from app.event_stream import event_frame
from app.services.golden_demo_service import DEMO_SOURCE, GoldenDemoService
from app.services.project_knowledge_service import ProjectKnowledgeQueryService
from app.services.requirement_lifecycle_service import RequirementAnalysisBusy, RequirementLifecycleService

router = APIRouter(tags=["QA Lifecycle"])


@router.get("/demo-shop/index.html")
async def demo_shop():
    return FileResponse(
        DEMO_SOURCE / "site" / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"}
    )


@router.get("/demo-shop/catalog.json")
async def demo_catalog():
    return FileResponse(
        DEMO_SOURCE / "site" / "catalog.json", media_type="application/json", headers={"Cache-Control": "no-cache"}
    )


@router.get("/demo-shop/discovery-fixture.html")
async def demo_discovery_fixture():
    """A page whose element and request counts are known, so a discovery run can be checked against them."""
    return _fixture("discovery-fixture.html")


@router.get("/demo-shop/discovery-fixture-b.html")
async def demo_discovery_fixture_b():
    """The same fixture with one more control and one more request, for the incremental comparison."""
    return _fixture("discovery-fixture-b.html")


def _fixture(name: str) -> FileResponse:
    return FileResponse(
        DEMO_SOURCE / "site" / name,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/projects/golden-demo/seed", dependencies=[Depends(require_permission(Permission.AUTOMATION_EDIT))])
async def seed_demo(service: GoldenDemoService = Depends(get_golden_demo_service)):
    try:
        return await service.seed()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post(
    "/projects/{project_id}/demo/reset",
    dependencies=[Depends(project_path_access("project_id")), Depends(require_permission(Permission.AUTOMATION_EDIT))],
)
async def reset_demo(project_id: str, service: GoldenDemoService = Depends(get_golden_demo_service)):
    try:
        return await service.seed(reset=True, project_id=project_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/knowledge", dependencies=[Depends(project_path_access("project_id"))])
async def project_knowledge(
    project_id: str,
    focus: str | None = None,
    hops: int = Query(2, ge=0, le=2),
    requirement_id: str | None = None,
    service: ProjectKnowledgeQueryService = Depends(get_project_knowledge_service),
):
    try:
        return await service.build(project_id, focus=focus, hops=hops, requirement_id=requirement_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/projects/{project_id}/knowledge/explain")
async def explain_knowledge(
    project_id: str,
    entity_id: str,
    service: ProjectKnowledgeQueryService = Depends(get_project_knowledge_service),
):
    try:
        return await service.explain(project_id, entity_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/requirements/{requirement_id}/lifecycle/analyze/stream")
async def analyze_requirement(
    requirement_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    try:
        stream = service.stream(requirement_id)
        first = await anext(stream)
    except RequirementAnalysisBusy as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    async def events():
        try:
            yield event_frame("trace", first)
            async for event in stream:
                yield event_frame("trace", event)
        finally:
            await stream.aclose()

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/requirements/{requirement_id}/lifecycle/designs")
async def adopt_scenarios(
    requirement_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    try:
        return await service.adopt_designs(requirement_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post(
    "/test-designs/{design_id}/lifecycle/case", dependencies=[Depends(require_permission(Permission.TEST_CASE_WRITE))]
)
async def adopt_case(
    design_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    try:
        return await service.adopt_case(design_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
