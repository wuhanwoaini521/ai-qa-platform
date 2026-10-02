"""Lifecycle projections and structured workflows over the existing domain entities."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from project_model.models import Permission
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import require_permission
from app.api.event_stream import event_frame
from app.persistence.database import get_db
from app.services.golden_demo_service import DEMO_SOURCE, GoldenDemoService
from app.services.project_knowledge_service import ProjectKnowledgeService
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


@router.post("/projects/golden-demo/seed", dependencies=[Depends(require_permission(Permission.AUTOMATION_EDIT))])
async def seed_demo():
    try:
        return await GoldenDemoService().seed()
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post(
    "/projects/{project_id}/demo/reset", dependencies=[Depends(require_permission(Permission.AUTOMATION_EDIT))]
)
async def reset_demo(project_id: str):
    try:
        return await GoldenDemoService().seed(reset=True, project_id=project_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/knowledge")
async def project_knowledge(
    project_id: str,
    focus: str | None = None,
    hops: int = Query(2, ge=0, le=2),
    requirement_id: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await ProjectKnowledgeService(session).build(
            project_id, focus=focus, hops=hops, requirement_id=requirement_id
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/projects/{project_id}/knowledge/explain")
async def explain_knowledge(project_id: str, entity_id: str, session: AsyncSession = Depends(get_db)):
    try:
        return await ProjectKnowledgeService(session).explain(project_id, entity_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/requirements/{requirement_id}/lifecycle/analyze/stream")
async def analyze_requirement(requirement_id: str):
    service = RequirementLifecycleService()
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
async def adopt_scenarios(requirement_id: str):
    try:
        return await RequirementLifecycleService().adopt_designs(requirement_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post(
    "/test-designs/{design_id}/lifecycle/case", dependencies=[Depends(require_permission(Permission.TEST_CASE_WRITE))]
)
async def adopt_case(design_id: str):
    try:
        return await RequirementLifecycleService().adopt_case(design_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
