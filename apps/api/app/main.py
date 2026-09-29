import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ai_router,
    artifacts_router,
    audit_router,
    auth_router,
    dashboard_router,
    failures_router,
    flaky_router,
    git_pr_router,
    health_router,
    jira_router,
    jobs_router,
    onboarding_router,
    projects_router,
    qa_assistant_router,
    quality_router,
    releases_router,
    requirements_router,
    runners_router,
    runs_router,
    teams_router,
    test_cases_router,
    test_designs_router,
    testrail_router,
    users_router,
    workers_router,
    workspaces_router,
)
from app.api.authz import authorize_request
from app.persistence.database import init_db
from app.services.metrics_service import metrics_service
from app.settings import settings

logger = logging.getLogger("app.startup")


async def _recover_stale_runs() -> list[str]:
    """Recovery uses the application's own session factory, independent of the request lifecycle."""
    from app.api.runs import open_run_service

    async with open_run_service() as service:
        return await service.recover_stale_runs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    await init_db()
    # Close runs abandoned by a previous process: without this a crashed run stays RUNNING forever
    # and every pass-rate and coverage figure built on it stays wrong.
    try:
        recovered = await _recover_stale_runs()
        if recovered:
            logger.warning("Recovered %d stale run(s) at startup: %s", len(recovered), ", ".join(recovered))
    except Exception as error:  # pragma: no cover - startup must never fail because of recovery
        logger.warning("Stale run recovery skipped: %s", error)
    yield


app = FastAPI(
    title="AI QA Platform API",
    version="1.0.0",
    description="Production-oriented AI QA Intelligence Platform",
    lifespan=lifespan,
    # Single application-level authorization guard: authenticates every non-public request and
    # enforces the resource policy table in app/api/authz.py.
    dependencies=[Depends(authorize_request)],
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    metrics_service.record_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration,
    )
    return response


# Include API Routers
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(teams_router, prefix="/api")
app.include_router(workers_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(requirements_router, prefix="/api")
app.include_router(test_designs_router, prefix="/api")
app.include_router(test_cases_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(git_pr_router, prefix="/api")
app.include_router(jira_router, prefix="/api")
app.include_router(testrail_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(quality_router, prefix="/api")
app.include_router(releases_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(runners_router, prefix="/api")
app.include_router(failures_router, prefix="/api")
app.include_router(flaky_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(onboarding_router, prefix="/api")
app.include_router(qa_assistant_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "platform": "AI QA Platform",
        "status": "online",
        "version": "0.3.0",
        "docs": "/docs",
        "api_prefix": "/api",
    }
