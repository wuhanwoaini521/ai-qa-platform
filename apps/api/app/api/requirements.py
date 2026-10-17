from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Requirement, RequirementCreate, RequirementUpdate, User

from app.api.authz import get_current_user
from app.api.project_acl import (
    enforce_project_access,
    project_query_access,
    requirement_access,
    visible_project_ids,
)
from app.container import get_requirement_service
from app.services.requirement_service import RequirementService

router = APIRouter(
    prefix="/requirements",
    tags=["Requirements"],
    dependencies=[Depends(requirement_access), Depends(project_query_access("project_id"))],
)


@router.get("", response_model=list[Requirement])
async def list_requirements(
    project_id: str | None = None,
    service: RequirementService = Depends(get_requirement_service),
    user: User = Depends(get_current_user),
):
    if project_id:
        return await service.list_requirements(project_id=project_id)
    allowed = await visible_project_ids(user)
    if allowed is None:
        return await service.list_requirements()
    return [r for r in await service.list_requirements() if r.project_id in allowed]


@router.post("", response_model=Requirement, status_code=status.HTTP_201_CREATED)
async def create_requirement(
    data: RequirementCreate,
    service: RequirementService = Depends(get_requirement_service),
    user: User = Depends(get_current_user),
):
    await enforce_project_access(user, data.project_id)
    try:
        return await service.create_requirement(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/{req_id}", response_model=Requirement)
async def get_requirement(req_id: str, service: RequirementService = Depends(get_requirement_service)):
    req = await service.get_requirement(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.patch("/{req_id}", response_model=Requirement)
async def update_requirement(
    req_id: str,
    data: RequirementUpdate,
    service: RequirementService = Depends(get_requirement_service),
):
    try:
        req = await service.update_requirement(req_id, data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req
