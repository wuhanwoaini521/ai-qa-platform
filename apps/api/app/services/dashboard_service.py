from __future__ import annotations

import statistics
from datetime import datetime, timezone

from project_model.models import DashboardStats, FlakyClassification

from app.repositories.run_history_repo import RunHistoryRepository
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
        history_repo: RunHistoryRepository | None = None,
    ) -> None:
        self.project_service = project_service
        self.requirement_service = requirement_service
        self.test_case_service = test_case_service
        self.run_repo = run_repo
        self.history_repo = history_repo or RunHistoryRepository(lambda: run_repo.session)

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

        # Flaky and recovery intelligence
        flaky_tests = await self.history_repo.list_flaky_tests()
        flaky_count = sum(1 for f in flaky_tests if f.flaky_score.classification == FlakyClassification.LIKELY_FLAKY)
        rerun_recoveries = sum(f.trend.retry_count for f in flaky_tests)

        # Average duration across recent executions
        durations = [r.duration_ms for r in runs_orms if r.duration_ms > 0]
        avg_dur = statistics.mean(durations) if durations else 0.0

        return DashboardStats(
            total_projects=len(projects),
            total_requirements=len(requirements),
            total_test_cases=len(test_cases),
            total_runs=len(runs_orms),
            runs_today=len(runs_today),
            tests_executed_today=tests_executed_today,
            pass_rate_today=round(pass_rate, 1),
            total_failures=len(failures_orms),
            flaky_tests_count=flaky_count,
            rerun_recovery_count=rerun_recoveries,
            average_test_duration_ms=round(avg_dur, 2),
            recent_projects=projects[:5],
            recent_requirements=requirements[:5],
            recent_test_cases=test_cases[:5],
            recent_runs=[],
        )
