from __future__ import annotations

from project_model.models import DashboardStats

from app.services.project_service import ProjectService
from app.services.requirement_service import RequirementService
from app.services.test_case_service import TestCaseService


class DashboardService:
    def __init__(
        self,
        project_service: ProjectService,
        requirement_service: RequirementService,
        test_case_service: TestCaseService,
    ) -> None:
        self.project_service = project_service
        self.requirement_service = requirement_service
        self.test_case_service = test_case_service

    async def get_stats(self) -> DashboardStats:
        projects = await self.project_service.list_projects()
        requirements = await self.requirement_service.list_requirements()
        test_cases = await self.test_case_service.list_test_cases()

        return DashboardStats(
            total_projects=len(projects),
            total_requirements=len(requirements),
            total_test_cases=len(test_cases),
            total_runs=0,
            recent_projects=projects[:5],
            recent_requirements=requirements[:5],
            recent_test_cases=test_cases[:5],
        )
