from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Project, ProjectCreate, ProjectUpdate

from app.container import get_project_service
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[Project])
async def list_projects(service: ProjectService = Depends(get_project_service)):
    return await service.list_projects()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, service: ProjectService = Depends(get_project_service)):
    return await service.create_project(data)


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, service: ProjectService = Depends(get_project_service)):
    proj = await service.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
):
    proj = await service.update_project(project_id, data)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj
