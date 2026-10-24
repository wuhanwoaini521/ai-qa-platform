from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import async_session_factory
from app.repositories.ai_budget_repo import AIDailyBudgetRepository
from app.repositories.ai_provider_settings_repo import AIProviderSettingsRepository, DecisionProviderSettingsRepository
from app.repositories.artifact_repo import ArtifactRepository
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.breakpoint_repo import BreakpointRepository
from app.repositories.browser_session_repo import BrowserSessionRepository
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository
from app.repositories.failure_analysis_repo import FailureAnalysisRepository
from app.repositories.failure_repo import FailureRepository
from app.repositories.golden_demo_repo import GoldenDemoRepository
from app.repositories.job_repo import JobRepository
from app.repositories.locator_history_repo import LocatorHistoryRepository
from app.repositories.locator_repair_repo import LocatorRepairRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.runner_profile_repo import RunnerProfileRepository
from app.repositories.task_evidence_repo import TaskEvidenceRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.worker_repo import WorkerRepository
from app.repositories.workspace_repo import WorkspaceRepository


class TaskRepositoryUnitOfWork:
    """Repository set and transaction boundary for one task use case."""

    def __init__(self, session: AsyncSession) -> None:
        self.tasks = TaskRepository(session)
        self.evidence = TaskEvidenceRepository(session, self.tasks)
        self.artifacts = ArtifactRepository(session)
        self.failures = FailureRepository(session)
        self.failure_analyses = FailureAnalysisRepository(session)
        self.breakpoints = BreakpointRepository(session)
        self.projects = ProjectRepository(session)
        self.requirements = RequirementRepository(session)
        self.test_cases = TestCaseRepository(session)
        self.test_designs = TestDesignRepository(session)
        self.test_runs = TestRunRepository(session)
        self.automation_bindings = AutomationBindingRepository(session)
        self.workspaces = WorkspaceRepository(session)
        self.provider_settings = AIProviderSettingsRepository(session)
        self.decision_settings = DecisionProviderSettingsRepository(session)
        self.ai_budgets = AIDailyBudgetRepository(session)
        self.jobs = JobRepository(session)
        self.locator_history = LocatorHistoryRepository(session)
        self.locator_repairs = LocatorRepairRepository(session)
        self.browser_sessions = BrowserSessionRepository(session)
        self.runner_profiles = RunnerProfileRepository(lambda: session)
        self.workers = WorkerRepository(session)
        self.golden_demo = GoldenDemoRepository(session)
        self.discovery = QualityDiscoveryRepository(session)
        self.discovery_evidence = DiscoveryEvidenceRepository(session)
        self.discovery_suggestions = DiscoverySuggestionRepository(session)
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class TaskRepositoryScopeFactory:
    """Open task repositories without exposing SQLAlchemy sessions to use cases."""

    def __init__(self, session_factory: Callable[..., Any] | None = None) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[TaskRepositoryUnitOfWork]:
        session_factory = self._session_factory or async_session_factory
        async with session_factory() as session:
            unit = TaskRepositoryUnitOfWork(session)
            try:
                yield unit
            except BaseException:
                await unit.rollback()
                raise
