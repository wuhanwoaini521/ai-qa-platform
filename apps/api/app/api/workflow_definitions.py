"""Authoring endpoints for versioned QA workflows.

Reading needs `project:read`, editing needs `automation:edit`, publishing needs `project:write`
(so a QA engineer can prepare a draft but a lead publishes it), and running a version needs
`run:execute`. Every route is scoped to a project the caller can access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from project_model.models import Permission, User
from pydantic import BaseModel, Field

from app.api.authz import get_current_user, require_permission
from app.api.project_acl import enforce_project_access
from app.container import get_workflow_definition_service, get_workflow_planner_service
from app.repositories.workflow_definition_repo import WorkflowVersionConflict, WorkflowVersionNotFound
from app.services.workflow_definition_service import WorkflowDefinitionService, WorkflowNameTaken
from app.services.workflow_planner_service import WorkflowPlannerService, WorkflowPlanUnavailable

router = APIRouter(tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class WorkflowGraphPayload(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowPlanRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class WorkflowSave(WorkflowGraphPayload):
    base_checksum: str | None = None


async def _definition(definition_id: str, service: WorkflowDefinitionService, user: User) -> tuple[Any, Any]:
    definition = await service.definitions.get(definition_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found.")
    await enforce_project_access(user, definition.project_id)
    return definition, service


@router.get("/projects/{project_id}/workflows")
async def list_workflows(
    project_id: str,
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    await enforce_project_access(user, project_id)
    return {
        "definitions": await service.list_for_project(project_id),
        "catalogue": service.catalogue(),
    }


@router.post("/projects/{project_id}/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    project_id: str,
    payload: WorkflowCreate,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    await enforce_project_access(user, project_id)
    try:
        definition = await service.create(project_id, payload.name, payload.description, str(user.id))
    except WorkflowNameTaken as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return await service.detail(definition)


@router.post("/projects/{project_id}/workflows/plan")
async def plan_workflow(
    project_id: str,
    payload: WorkflowPlanRequest,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    service: WorkflowPlannerService = Depends(get_workflow_planner_service),
) -> dict[str, Any]:
    """Propose a candidate graph. Nothing is saved: the caller must accept it as a draft."""
    await enforce_project_access(user, project_id)
    try:
        return await service.plan(payload.prompt, project_id=project_id, actor=str(user.id))
    except WorkflowPlanUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.get("/workflows/{definition_id}")
async def get_workflow(
    definition_id: str,
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    return await service.detail(definition)


@router.put("/workflows/{definition_id}/draft")
async def save_draft(
    definition_id: str,
    payload: WorkflowSave,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    graph = {"nodes": payload.nodes, "edges": payload.edges}
    try:
        return await service.save(definition, graph, str(user.id), base_checksum=payload.base_checksum)
    except WorkflowVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/workflows/{definition_id}/validate")
async def validate_draft(
    definition_id: str,
    payload: WorkflowGraphPayload,
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    await _definition(definition_id, service, user)
    return {"issues": await service.validate({"nodes": payload.nodes, "edges": payload.edges})}


@router.post("/workflows/{definition_id}/publish")
async def publish_workflow(
    definition_id: str,
    user: User = Depends(require_permission(Permission.PROJECT_WRITE)),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    try:
        return await service.publish(definition, str(user.id))
    except WorkflowVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("/workflows/{definition_id}/versions/{version}/restore")
async def restore_version(
    definition_id: str,
    version: int,
    user: User = Depends(require_permission(Permission.AUTOMATION_EDIT)),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    try:
        return await service.restore(definition, version, str(user.id))
    except WorkflowVersionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/workflows/{definition_id}/compare")
async def compare_versions(
    definition_id: str,
    base: int = Query(ge=1),
    head: int = Query(ge=1),
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    try:
        return await service.compare(definition, base, head)
    except WorkflowVersionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/workflows/{definition_id}/execution-diff")
async def execution_diff(
    definition_id: str,
    task_id: str = Query(min_length=1),
    version: int | None = Query(default=None, ge=1),
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    try:
        return await service.execution_diff(definition, version, task_id)
    except WorkflowVersionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
