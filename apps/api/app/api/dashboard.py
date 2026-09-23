from fastapi import APIRouter, Depends
from project_model.models import DashboardStats
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.dashboard_service import DashboardService
from app.services.project_service import ProjectService
from app.services.requirement_service import RequirementService
from app.services.test_case_service import TestCaseService
from app.services.workspace_service import WorkspaceService

router = APIRouter(tags=["Dashboard"])


def get_dashboard_service(session: AsyncSession = Depends(get_db)) -> DashboardService:
    workspace_service = WorkspaceService()
    project_repo = ProjectRepository(session)
    workspace_repo = WorkspaceRepository(session)
    requirement_repo = RequirementRepository(session)
    test_case_repo = TestCaseRepository(session)
    run_repo = TestRunRepository(session)

    project_service = ProjectService(project_repo, workspace_repo, workspace_service)
    requirement_service = RequirementService(requirement_repo)
    test_case_service = TestCaseService(test_case_repo)

    return DashboardService(project_service, requirement_service, test_case_service, run_repo)


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(service: DashboardService = Depends(get_dashboard_service)):
    return await service.get_stats()
