from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import TestDesign, TestDesignCreate, TestDesignUpdate
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.test_design_repo import TestDesignRepository
from app.services.test_design_service import TestDesignService

router = APIRouter(prefix="/test-designs", tags=["Test Designs"])


def get_test_design_service(session: AsyncSession = Depends(get_db)) -> TestDesignService:
    repo = TestDesignRepository(session)
    return TestDesignService(repo)


@router.get("", response_model=list[TestDesign])
async def list_test_designs(
    requirement_id: str,
    service: TestDesignService = Depends(get_test_design_service),
):
    return await service.list_by_requirement(requirement_id)


@router.post("", response_model=TestDesign, status_code=status.HTTP_201_CREATED)
async def create_test_design(
    data: TestDesignCreate,
    service: TestDesignService = Depends(get_test_design_service),
):
    return await service.create_test_design(data)


@router.get("/{design_id}", response_model=TestDesign)
async def get_test_design(design_id: str, service: TestDesignService = Depends(get_test_design_service)):
    item = await service.get_test_design(design_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test Design not found")
    return item


@router.patch("/{design_id}", response_model=TestDesign)
async def update_test_design(
    design_id: str,
    data: TestDesignUpdate,
    service: TestDesignService = Depends(get_test_design_service),
):
    item = await service.update_test_design(design_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Test Design not found")
    return item
