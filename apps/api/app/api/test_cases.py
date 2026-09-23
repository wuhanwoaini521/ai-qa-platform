from fastapi import APIRouter, Depends, HTTPException, status
from project_model.models import TestCase, TestCaseCreate, TestCaseUpdate
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.test_case_repo import TestCaseRepository
from app.services.test_case_service import TestCaseService

router = APIRouter(prefix="/test-cases", tags=["Test Cases"])


def get_test_case_service(session: AsyncSession = Depends(get_db)) -> TestCaseService:
    repo = TestCaseRepository(session)
    return TestCaseService(repo)


@router.get("", response_model=list[TestCase])
async def list_test_cases(
    project_id: str | None = None,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.list_test_cases(project_id=project_id)


@router.post("", response_model=TestCase, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    data: TestCaseCreate,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.create_test_case(data)


@router.get("/{case_id}", response_model=TestCase)
async def get_test_case(case_id: str, service: TestCaseService = Depends(get_test_case_service)):
    tc = await service.get_test_case(case_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test Case not found")
    return tc


@router.patch("/{case_id}", response_model=TestCase)
async def update_test_case(
    case_id: str,
    data: TestCaseUpdate,
    service: TestCaseService = Depends(get_test_case_service),
):
    tc = await service.update_test_case(case_id, data)
    if not tc:
        raise HTTPException(status_code=404, detail="Test Case not found")
    return tc
