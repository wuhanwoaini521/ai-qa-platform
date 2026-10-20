"""HTTP dependency composition root; routers receive application services only."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlalchemy_health_probe import SqlAlchemyDatabaseHealthProbe
from app.adapters.persistence.sqlalchemy_transaction import SqlAlchemyTransactionBoundary
from app.adapters.playwright.browser_runtime import browser_runtime as _browser_runtime
from app.persistence.database import async_session_factory, get_db
from app.ports.browser_runtime import BrowserRuntime
from app.repositories.ai_repo import AIRepository
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.failure_repo import FailureRepository
from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.project_access_repo import ProjectAccessRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.release_repo import ReleaseRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.security_audit_repo import SecurityAuditRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory, TaskRepositoryUnitOfWork
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.ai_service import AIService
from app.services.ai_settings_service import AISettingsService
from app.services.api_read_service import (
    ApiKeyService,
    AuditQueryService,
    FlakyQueryService,
    StreamResourceService,
    TaskEventService,
)
from app.services.automation_binding_service import AutomationBindingService
from app.services.dashboard_service import DashboardService
from app.services.debug_session_service import debug_session_service
from app.services.decision_service import DecisionService
from app.services.decision_settings_service import DecisionSettingsService
from app.services.discovery_evidence_service import DiscoveryEvidenceService
from app.services.failure_service import FailureService
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.golden_demo_service import GoldenDemoService
from app.services.health_service import HealthService
from app.services.jira_service import JiraService
from app.services.locator_repair_funnel_service import LocatorRepairFunnelService
from app.services.metrics_service import MetricsService
from app.services.onboarding_service import OnboardingService
from app.services.platform_health_service import PlatformHealthService
from app.services.pr_service import PullRequestService
from app.services.project_access_service import ProjectAccessService
from app.services.project_knowledge_service import ProjectKnowledgeQueryService
from app.services.project_service import ProjectService
from app.services.qa_assistant_service import QAAssistantService
from app.services.quality_discovery_service import QualityDiscoveryService
from app.services.quality_intelligence_service import QualityIntelligenceService
from app.services.recorder_service import BrowserRecorderService
from app.services.recorder_workflow_service import RecorderWorkflowService
from app.services.release_service import ReleaseService
from app.services.requirement_lifecycle_service import RequirementLifecycleService
from app.services.requirement_service import RequirementService
from app.services.runtime_projection import RuntimeProjection
from app.services.task_runtime_service import TaskRuntimeService
from app.services.test_case_service import TestCaseService
from app.services.test_design_service import TestDesignService
from app.services.test_run_service import TestRunService
from app.services.testrail_service import TestRailService
from app.services.workflow_canvas_service import WorkflowCanvasService
from app.services.workspace_catalog_service import WorkspaceCatalogService
from app.services.workspace_service import WorkspaceService
from app.settings import get_config


def get_project_service(session: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(ProjectRepository(session), WorkspaceRepository(session), WorkspaceService())


def get_requirement_service(session: AsyncSession = Depends(get_db)) -> RequirementService:
    return RequirementService(
        RequirementRepository(session), TestCaseRepository(session), TestDesignRepository(session)
    )


def get_repository_scope_factory() -> TaskRepositoryScopeFactory:
    return TaskRepositoryScopeFactory()


_metrics_service: MetricsService | None = None


def get_metrics_service() -> MetricsService:
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService(get_repository_scope_factory())
    return _metrics_service


def get_requirement_lifecycle_service() -> RequirementLifecycleService:
    scope = get_repository_scope_factory()
    return RequirementLifecycleService(repository_scope=scope, decisions=DecisionService(repository_scope=scope))


def get_ai_settings_service() -> AISettingsService:
    return AISettingsService(repository_scope=get_repository_scope_factory())


def get_decision_settings_service() -> DecisionSettingsService:
    return DecisionSettingsService(repository_scope=get_repository_scope_factory())


def get_decision_service() -> DecisionService:
    scope = get_repository_scope_factory()
    return DecisionService(settings_service=DecisionSettingsService(scope), repository_scope=scope)


_platform_health_service: PlatformHealthService | None = None
_database_health_probe = SqlAlchemyDatabaseHealthProbe()


def get_health_service() -> HealthService:
    return HealthService(_database_health_probe)


def get_platform_health_service() -> PlatformHealthService:
    global _platform_health_service
    if _platform_health_service is None:
        _platform_health_service = PlatformHealthService(
            repository_scope=get_repository_scope_factory(),
            database_health_probe=_database_health_probe,
        )
    return _platform_health_service


def get_qa_assistant_service() -> QAAssistantService:
    return QAAssistantService(repository_scope=get_repository_scope_factory())


def get_golden_demo_service() -> GoldenDemoService:
    return GoldenDemoService(repository_scope=get_repository_scope_factory())


async def recover_failure_analyses() -> None:
    """Close analyses a previous process left RUNNING, releasing their repair rows as well."""
    async with async_session_factory() as session:
        workflow = FailureWorkflowService(
            get_failure_service(session),
            run_service=build_run_service(session),
            repository_scope=get_repository_scope_factory(),
        )
        await workflow.recover_interrupted_analyses()


async def recover_ai_invocations() -> int:
    """Close AI calls a previous process left RUNNING so usage never reports a stuck invocation."""
    return await AIRepository().recover_interrupted_invocations()


async def recover_quality_discovery_runs() -> int:
    """Pause explorations a previous process abandoned so an operator can resume them."""
    return await get_quality_discovery_service().recover_interrupted_runs()


def get_job_queue_service():
    from app.services.job_queue_service import JobQueueService

    return JobQueueService(repository_scope=get_repository_scope_factory())


def get_test_case_service(session: AsyncSession = Depends(get_db)) -> TestCaseService:
    return TestCaseService(TestCaseRepository(session), RequirementRepository(session), TestDesignRepository(session))


def get_discovery_evidence_service(session: AsyncSession = Depends(get_db)) -> DiscoveryEvidenceService:
    """Evidence is read through the request session, exactly like the workflow canvas."""
    return DiscoveryEvidenceService(
        evidence=DiscoveryEvidenceRepository(session),
        discovery=QualityDiscoveryRepository(session),
        cases=TestCaseRepository(session),
    )


def get_binding_service(session: AsyncSession = Depends(get_db)):
    return AutomationBindingService(
        AutomationBindingRepository(session),
        TestCaseRepository(session),
        WorkspaceRepository(session),
        WorkspaceService(),
    )


def get_test_design_service(session: AsyncSession = Depends(get_db)) -> TestDesignService:
    return TestDesignService(TestDesignRepository(session), RequirementRepository(session))


def build_run_service(session: AsyncSession) -> TestRunService:
    repositories = TaskRepositoryUnitOfWork(session)
    return TestRunService(
        repositories.test_runs,
        repositories.workspaces,
        WorkspaceService(),
        repository_scope=get_repository_scope_factory(),
        repositories=repositories,
        runner_repo=repositories.runner_profiles,
    )


def get_run_service(session: AsyncSession = Depends(get_db)) -> TestRunService:
    return build_run_service(session)


@asynccontextmanager
async def open_run_service() -> AsyncGenerator[TestRunService, None]:
    async with async_session_factory() as session:
        yield build_run_service(session)


def get_project_access_service(session: AsyncSession = Depends(get_db)) -> ProjectAccessService:
    return ProjectAccessService(ProjectAccessRepository(session))


@asynccontextmanager
async def open_project_access_service() -> AsyncGenerator[ProjectAccessService, None]:
    async with async_session_factory() as session:
        yield ProjectAccessService(ProjectAccessRepository(session))


def get_dashboard_service(session: AsyncSession = Depends(get_db)) -> DashboardService:
    workspace_repo = WorkspaceRepository(session)
    project_service = ProjectService(ProjectRepository(session), workspace_repo, WorkspaceService())
    requirement_service = RequirementService(
        RequirementRepository(session), TestCaseRepository(session), TestDesignRepository(session)
    )
    test_case_service = TestCaseService(
        TestCaseRepository(session), RequirementRepository(session), TestDesignRepository(session)
    )
    return DashboardService(project_service, requirement_service, test_case_service, TestRunRepository(session))


def get_ai_service(session: AsyncSession = Depends(get_db)) -> AIService:
    scope = get_repository_scope_factory()
    return AIService(
        ai_repo=AIRepository(),
        requirement_repo=RequirementRepository(session),
        test_design_repo=TestDesignRepository(session),
        test_case_repo=TestCaseRepository(session),
        test_run_repo=TestRunRepository(session),
        project_repo=ProjectRepository(session),
        settings_service=AISettingsService(repository_scope=scope),
    )


def get_failure_service(session: AsyncSession = Depends(get_db)) -> FailureService:
    return FailureService(
        run_repo=TestRunRepository(session),
        workspace_repo=WorkspaceRepository(session),
        workspace_service=WorkspaceService(),
        history_repo=RunHistoryRepository(),
        ai_repo=AIRepository(),
        failure_repo=FailureRepository(session),
        transaction=SqlAlchemyTransactionBoundary(session),
        repository_scope=get_repository_scope_factory(),
    )


def get_failure_workflow_service(
    service: FailureService = Depends(get_failure_service),
    session: AsyncSession = Depends(get_db),
) -> FailureWorkflowService:
    return FailureWorkflowService(
        service,
        run_service=build_run_service(session),
        repository_scope=get_repository_scope_factory(),
    )


def get_pr_service(session: AsyncSession = Depends(get_db)) -> PullRequestService:
    return PullRequestService(
        workspace_service=WorkspaceService(),
        workspace_repo=WorkspaceRepository(session),
        project_repo=ProjectRepository(session),
        requirement_repo=RequirementRepository(session),
        test_case_repo=TestCaseRepository(session),
        binding_repo=AutomationBindingRepository(session),
        test_run_repo=TestRunRepository(session),
        run_history_repo=RunHistoryRepository(session),
    )


def get_jira_service(session: AsyncSession = Depends(get_db)) -> JiraService:
    return JiraService(
        requirement_repo=RequirementRepository(session),
        audit_repo=IntegrationAuditRepository(session),
        test_run_repo=TestRunRepository(session),
    )


def get_quality_service(session: AsyncSession = Depends(get_db)) -> QualityIntelligenceService:
    return build_quality_service(session)


def get_locator_repair_funnel_service() -> LocatorRepairFunnelService:
    return LocatorRepairFunnelService(get_repository_scope_factory())


def build_quality_service(session: AsyncSession) -> QualityIntelligenceService:
    return QualityIntelligenceService(
        requirement_repo=RequirementRepository(session),
        test_case_repo=TestCaseRepository(session),
        test_design_repo=TestDesignRepository(session),
        binding_repo=AutomationBindingRepository(session),
        test_run_repo=TestRunRepository(session),
        history_repo=RunHistoryRepository(lambda: session),
        workspace_service=WorkspaceService(),
    )


def get_release_service(session: AsyncSession = Depends(get_db)) -> ReleaseService:
    run_repo = TestRunRepository(session)
    history_repo = RunHistoryRepository(lambda: session)
    return ReleaseService(
        release_repo=ReleaseRepository(session),
        test_run_repo=run_repo,
        quality_service=build_quality_service(session),
        history_repo=history_repo,
    )


def get_onboarding_service(
    session: AsyncSession = Depends(get_db),
    run_service: TestRunService = Depends(get_run_service),
) -> OnboardingService:
    return OnboardingService(
        project_repo=ProjectRepository(session),
        workspace_repo=WorkspaceRepository(session),
        run_service=run_service,
        workspace_base_dir=get_config().app.workspace_storage_dir,
    )


def get_testrail_service(session: AsyncSession = Depends(get_db)) -> TestRailService:
    return TestRailService(
        test_run_repo=TestRunRepository(session),
        test_case_repo=TestCaseRepository(session),
        audit_repo=IntegrationAuditRepository(session),
    )


def get_audit_query_service(session: AsyncSession = Depends(get_db)) -> AuditQueryService:
    return AuditQueryService(IntegrationAuditRepository(session), SecurityAuditRepository())


def get_flaky_query_service() -> FlakyQueryService:
    return FlakyQueryService(RunHistoryRepository())


def get_api_key_service() -> ApiKeyService:
    return ApiKeyService(ApiKeyRepository())


def get_stream_resource_service(session: AsyncSession = Depends(get_db)) -> StreamResourceService:
    return StreamResourceService(
        TestRunRepository(session),
        TaskRepository(session),
        ProjectRepository(session),
        recorder_service,
        debug_session_service,
        QualityDiscoveryRepository(session),
        ProjectAccessRepository(session),
    )


def get_task_event_service() -> TaskEventService:
    return TaskEventService(async_session_factory)


def get_workspace_catalog_service() -> WorkspaceCatalogService:
    return WorkspaceCatalogService(TaskRepositoryScopeFactory())


def get_runtime_projection(session: AsyncSession = Depends(get_db)) -> RuntimeProjection:
    return RuntimeProjection(session)


def get_project_knowledge_service(session: AsyncSession = Depends(get_db)) -> ProjectKnowledgeQueryService:
    return ProjectKnowledgeQueryService(session)


_quality_discovery_service: QualityDiscoveryService | None = None


def get_quality_discovery_service() -> QualityDiscoveryService:
    global _quality_discovery_service
    if _quality_discovery_service is None:
        scope = get_repository_scope_factory()
        _quality_discovery_service = QualityDiscoveryService(
            async_session_factory,
            browser_runtime=get_browser_runtime(),
            decisions=DecisionService(repository_scope=scope),
            workspace_service=WorkspaceService(),
            task_commands=get_task_runtime_service().commands,
        )
    return _quality_discovery_service


_task_runtime_service: TaskRuntimeService | None = None


def get_task_runtime_service() -> TaskRuntimeService:
    global _task_runtime_service
    if _task_runtime_service is None:
        _task_runtime_service = TaskRuntimeService(
            repository_scope=TaskRepositoryScopeFactory(),
            browser_runtime=get_browser_runtime(),
            recorder_session_resolver=recorder_service.get,
        )
    return _task_runtime_service


def get_workflow_canvas_service(
    session: AsyncSession = Depends(get_db),
    run_service: TestRunService = Depends(get_run_service),
    failure_service: FailureService = Depends(get_failure_service),
    workflow: FailureWorkflowService = Depends(get_failure_workflow_service),
    bindings: AutomationBindingService = Depends(get_binding_service),
) -> WorkflowCanvasService:
    # Read discovery rows through the request session: the canvas must see exactly what the
    # request sees, not a process-wide service holding its own session factory.
    return WorkflowCanvasService(
        runs=run_service,
        failures=failure_service,
        workflow=workflow,
        discovery=QualityDiscoveryRepository(session),
        evidence=DiscoveryEvidenceRepository(session),
        bindings=bindings,
    )


def get_recorder_workflow_service(session: AsyncSession = Depends(get_db)) -> RecorderWorkflowService:
    case_repo = TestCaseRepository(session)
    return RecorderWorkflowService(
        project_repo=ProjectRepository(session),
        test_case_repo=case_repo,
        binding_service=AutomationBindingService(
            AutomationBindingRepository(session), case_repo, WorkspaceRepository(session), WorkspaceService()
        ),
        recorder=recorder_service,
    )


def get_browser_runtime() -> BrowserRuntime:
    return _browser_runtime


recorder_service = BrowserRecorderService(
    browser_runtime=_browser_runtime, repository_scope=get_repository_scope_factory()
)
