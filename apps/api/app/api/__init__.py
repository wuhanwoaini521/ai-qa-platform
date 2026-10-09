from app.api.ai import router as ai_router
from app.api.artifacts import router as artifacts_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.debugger import router as debugger_router
from app.api.decision import router as decision_router
from app.api.failures import router as failures_router
from app.api.flaky import router as flaky_router
from app.api.git_pr import router as git_pr_router
from app.api.health import router as health_router
from app.api.jira import router as jira_router
from app.api.jobs import router as jobs_router
from app.api.onboarding import router as onboarding_router
from app.api.projects import router as projects_router
from app.api.qa_assistant import router as qa_assistant_router
from app.api.quality import router as quality_router
from app.api.recorder import router as recorder_router
from app.api.releases import router as releases_router
from app.api.settings import router as settings_router
from app.api.requirements import router as requirements_router
from app.api.runners import router as runners_router
from app.api.runs import router as runs_router
from app.api.tasks import router as tasks_router
from app.api.teams import router as teams_router
from app.api.test_cases import router as test_cases_router
from app.api.test_designs import router as test_designs_router
from app.api.testrail import router as testrail_router
from app.api.users import router as users_router
from app.api.workers import router as workers_router
from app.api.workspaces import router as workspaces_router

__all__ = [
    "ai_router",
    "artifacts_router",
    "audit_router",
    "auth_router",
    "dashboard_router",
    "debugger_router",
    "decision_router",
    "failures_router",
    "flaky_router",
    "git_pr_router",
    "health_router",
    "jira_router",
    "jobs_router",
    "projects_router",
    "recorder_router",
    "onboarding_router",
    "qa_assistant_router",
    "quality_router",
    "releases_router",
    "settings_router",
    "requirements_router",
    "runners_router",
    "runs_router",
    "teams_router",
    "test_cases_router",
    "test_designs_router",
    "tasks_router",
    "testrail_router",
    "users_router",
    "workers_router",
    "workspaces_router",
]
