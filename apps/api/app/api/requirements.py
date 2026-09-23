from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import Requirement, RequirementCreate, RequirementUpdate
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.requirement_repo import RequirementRepository
from app.services.requirement_service import RequirementService

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def get_requirement_service(session: AsyncSession = Depends(get_db)) -> RequirementService:
    repo = RequirementRepository(session)
    return RequirementService(repo)


@router.get("", response_model=list[Requirement])
async def list_requirements(
    project_id: str | None = None,
    service: RequirementService = Depends(get_requirement_service),
):
    return await service.list_requirements(project_id=project_id)


@router.post("", response_model=Requirement, status_code=status.HTTP_201_CREATED)
async def create_requirement(
    data: RequirementCreate,
    service: RequirementService = Depends(get_requirement_service),
):
    return await service.create_requirement(data)


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
    req = await service.update_requirement(req_id, data)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req
