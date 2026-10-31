"""Lifecycle projections and structured workflows over the existing domain entities."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from project_model.models import Permission
from pydantic import BaseModel, Field
from qa_core.ai.budget import BudgetExceededError
from qa_core.ai.provider import AIProviderError

from app.api.authz import require_permission
from app.api.project_acl import project_path_access, requirement_id_access
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


@router.post("/requirements/{requirement_id}/assertions/draft", dependencies=[Depends(requirement_id_access)])
async def draft_assertions(
    requirement_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    """Draft assertions grounded in acceptance criteria. Drafts are never applied automatically."""
    try:
        return await service.draft_assertions(requirement_id)
    except BudgetExceededError as error:
        raise HTTPException(429, str(error)) from error
    except AIProviderError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post(
    "/requirements/{requirement_id}/assertions/{assertion_id}/adoption", dependencies=[Depends(requirement_id_access)]
)
async def set_assertion_adoption(
    requirement_id: str,
    assertion_id: str,
    adopted: bool = Body(embed=True),
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    """Record the human adoption decision for one drafted assertion."""
    try:
        return await service.set_assertion_adoption(requirement_id, assertion_id, adopted)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/requirements/{requirement_id}/assertions/script", dependencies=[Depends(requirement_id_access)])
async def generate_assertion_script(
    requirement_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    """Return a script draft built from human-adopted assertions. Nothing is written to disk."""
    try:
        return await service.generate_assertion_script(requirement_id)
    except BudgetExceededError as error:
        raise HTTPException(429, str(error)) from error
    except AIProviderError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class AssertionScriptSavePayload(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1)
    assertion_ids: list[str] = Field(min_length=1, max_length=30)


@router.post("/requirements/{requirement_id}/assertions/script/save", dependencies=[Depends(requirement_id_access)])
async def save_assertion_script(
    requirement_id: str,
    payload: AssertionScriptSavePayload,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    """Save a human-approved script and record which adopted assertions it implements."""
    try:
        return await service.save_assertion_script(
            requirement_id, path=payload.path, code=payload.code, assertion_ids=payload.assertion_ids
        )
    except RequirementAnalysisBusy as error:
        raise HTTPException(409, str(error)) from error
    except FileExistsError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/requirements/{requirement_id}/assertions/runs", dependencies=[Depends(requirement_id_access)])
async def assertion_runs(
    requirement_id: str,
    service: RequirementLifecycleService = Depends(get_requirement_lifecycle_service),
):
    """Return each assertion with its latest real TestRun execution, or NEVER_RUN."""
    try:
        return await service.assertion_runs(requirement_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


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
