"""Authoring endpoints for versioned QA workflows.

Reading needs `project:read`, editing needs `automation:edit`, publishing needs `project:write`
(so a QA engineer can prepare a draft but a lead publishes it), and running a version needs
`run:execute`. Every route is scoped to a project the caller can access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from project_model.models import Permission, User
from pydantic import BaseModel, Field

from app.api.authz import get_current_user, require_permission
from app.api.project_acl import enforce_project_access
from app.container import get_task_runtime_service, get_workflow_definition_service, get_workflow_planner_service
from app.services.task_runtime_service import TaskRuntimeService
from app.services.workflow_definition_service import WorkflowDefinitionService, WorkflowNameTaken
from app.services.workflow_errors import (
    WorkflowConcurrentModification,
    WorkflowGraphValidationError,
    WorkflowVersionConflict,
    WorkflowVersionNotFound,
)
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


class WorkflowLaunch(BaseModel):
    version: int | None = Field(default=None, ge=1)
    inputs: dict[str, Any] = Field(default_factory=dict)


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
    except WorkflowGraphValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except WorkflowVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except WorkflowConcurrentModification as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONCURRENT_MODIFICATION", "message": str(error)},
        ) from error


@router.post("/workflows/{definition_id}/validate")
async def validate_draft(
    definition_id: str,
    payload: WorkflowGraphPayload,
    user: User = Depends(get_current_user),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
) -> dict[str, Any]:
    await _definition(definition_id, service, user)
    try:
        return {"issues": await service.validate({"nodes": payload.nodes, "edges": payload.edges})}
    except WorkflowGraphValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.post("/workflows/{definition_id}/execute", status_code=status.HTTP_202_ACCEPTED)
async def execute_workflow(
    definition_id: str,
    payload: WorkflowLaunch,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=100),
    user: User = Depends(require_permission(Permission.RUN_EXECUTE)),
    service: WorkflowDefinitionService = Depends(get_workflow_definition_service),
    runtime: TaskRuntimeService = Depends(get_task_runtime_service),
) -> dict[str, Any]:
    definition, service = await _definition(definition_id, service, user)
    try:
        existing = await runtime.commands.workflow_replay(
            definition_id=definition.id,
            owner_id=str(user.id),
            idempotency_key=idempotency_key,
            inputs=payload.inputs,
            requested_version=payload.version,
        )
        if existing is not None:
            return {
                "task_id": existing.id,
                "execution_id": existing.workflow_execution_id,
                "definition_id": existing.workflow_definition_id,
                "version_id": existing.workflow_version_id,
                "version": existing.workflow_version,
                "checksum": existing.workflow_checksum,
                "status": existing.status.value,
            }
        version = await service.published_version(definition, payload.version)
        plan, version = await service.compile_plan(
            definition, version.version, inputs=payload.inputs, for_execution=True
        )
        node_kinds = {
            str(node.get("kind")): str(node.get("key")) for node in ((version.graph or {}).get("nodes") or [])
        }
        failure_id = str(payload.inputs.get("failure_id") or "")
        task = await runtime.commands.create_workflow(
            project_id=definition.project_id,
            owner_id=str(user.id),
            goal=f"Run {definition.name} v{version.version}",
            inputs=payload.inputs,
            plan=plan,
            node_kinds=node_kinds,
            definition_id=definition.id,
            version_id=version.id,
            version=version.version,
            checksum=version.checksum,
            idempotency_key=idempotency_key,
            failure_id=failure_id,
            requested_version=payload.version,
        )
        return {
            "task_id": task.id,
            "execution_id": task.workflow_execution_id,
            "definition_id": task.workflow_definition_id,
            "version_id": task.workflow_version_id,
            "version": task.workflow_version,
            "checksum": task.workflow_checksum,
            "status": task.status.value,
        }
    except WorkflowVersionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except WorkflowVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except ValueError as error:
        message = str(error)
        code = (
            status.HTTP_409_CONFLICT if message.startswith("Idempotency key") else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=message) from error


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
    except WorkflowConcurrentModification as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONCURRENT_MODIFICATION", "message": str(error)},
        ) from error


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
