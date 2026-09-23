from __future__ import annotations

from datetime import datetime, timezone

from project_model.models import DashboardStats

from app.repositories.test_run_repo import TestRunRepository
from app.services.project_service import ProjectService
from app.services.requirement_service import RequirementService
from app.services.test_case_service import TestCaseService


class DashboardService:
    def __init__(
        self,
        project_service: ProjectService,
        requirement_service: RequirementService,
        test_case_service: TestCaseService,
        run_repo: TestRunRepository,
    ) -> None:
        self.project_service = project_service
        self.requirement_service = requirement_service
        self.test_case_service = test_case_service
        self.run_repo = run_repo

    async def get_stats(self) -> DashboardStats:
        projects = await self.project_service.list_projects()
        requirements = await self.requirement_service.list_requirements()
        test_cases = await self.test_case_service.list_test_cases()
        runs_orms = await self.run_repo.list_runs(limit=20)
        failures_orms = await self.run_repo.list_failures(limit=20)

        # Calculate today stats
        now = datetime.now(timezone.utc)
        runs_today = [r for r in runs_orms if r.created_at and r.created_at.date() == now.date()]
        tests_executed_today = sum(r.total for r in runs_today)
        passed_today = sum(r.passed for r in runs_today)
        pass_rate = (passed_today / tests_executed_today * 100.0) if tests_executed_today > 0 else 100.0

        recent_runs_dto = []
        for r in runs_orms[:5]:
            recent_runs_dto.append(r.id)

        return DashboardStats(
            total_projects=len(projects),
            total_requirements=len(requirements),
            total_test_cases=len(test_cases),
            total_runs=len(runs_orms),
            runs_today=len(runs_today),
            tests_executed_today=tests_executed_today,
            pass_rate_today=round(pass_rate, 1),
            total_failures=len(failures_orms),
            recent_projects=projects[:5],
            recent_requirements=requirements[:5],
            recent_test_cases=test_cases[:5],
            recent_runs=[],
        )
