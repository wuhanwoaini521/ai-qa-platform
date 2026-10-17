from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Project, ProjectCreate, ProjectUpdate, User

from app.api.authz import get_current_user
from app.api.project_acl import is_admin, visible_project_ids
from app.container import get_project_service
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[Project])
async def list_projects(
    service: ProjectService = Depends(get_project_service),
    user: User = Depends(get_current_user),
):
    projects = await service.list_projects()
    allowed = await visible_project_ids(user)
    if allowed is None:
        return projects
    return [p for p in projects if p.id in allowed]


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
    user: User = Depends(get_current_user),
):
    return await service.create_project(data, owner_id=user.id)


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    user: User = Depends(get_current_user),
):
    allowed = await visible_project_ids(user)
    if allowed is not None and project_id not in allowed:
        raise HTTPException(status_code=404, detail="Project not found")
    proj = await service.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
    user: User = Depends(get_current_user),
):
    allowed = await visible_project_ids(user)
    if allowed is not None and project_id not in allowed:
        raise HTTPException(status_code=404, detail="Project not found")
    # Ownership transfer is the "claim a legacy project" lever, so it stays admin-only: an owner
    # must not be able to hand a project to another user or widen it to an arbitrary team.
    ownership_fields = {"owner_id", "team_id"} & data.model_fields_set
    if ownership_fields and not is_admin(user):
        raise HTTPException(status_code=403, detail="Only an administrator may change ownership")
    proj = await service.update_project(project_id, data)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj
