from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.requirements import router as requirements_router
from app.api.test_cases import router as test_cases_router
from app.api.test_designs import router as test_designs_router
from app.api.workspaces import router as workspaces_router

__all__ = [
    "dashboard_router",
    "health_router",
    "projects_router",
    "requirements_router",
    "test_cases_router",
    "test_designs_router",
    "workspaces_router",
]
