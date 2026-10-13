import asyncio
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from qa_core.ai.correlation import request_id_context
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException

from app.api import (
    ai_router,
    artifacts_router,
    audit_router,
    auth_router,
    dashboard_router,
    debugger_router,
    decision_router,
    failures_router,
    flaky_router,
    git_pr_router,
    health_router,
    jira_router,
    jobs_router,
    onboarding_router,
    projects_router,
    qa_assistant_router,
    quality_discovery_router,
    quality_router,
    recorder_router,
    releases_router,
    requirements_router,
    runners_router,
    runs_router,
    settings_router,
    tasks_router,
    teams_router,
    test_cases_router,
    test_designs_router,
    testrail_router,
    users_router,
    workers_router,
    workspaces_router,
)
from app.api.authz import StreamTicketQuerySanitizer, authorize_request
from app.api.errors import http_error, validation_error
from app.api.language_service import router as language_service_router
from app.api.lifecycle import router as lifecycle_router
from app.api.runtime import router as runtime_router
from app.persistence.database import engine, init_db
from app.settings import config_manager, get_config

logger = logging.getLogger("app.startup")


class RequestMetricsMiddleware:
    """Track request IDs and metrics without BaseHTTPMiddleware task cancellation."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = time.time()
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        status_code = 500

        async def send_with_request_id(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_context.reset(token)
            from app.container import get_metrics_service

            get_metrics_service().record_request(
                method=scope.get("method", ""),
                path=scope.get("path", ""),
                status_code=status_code,
                duration_seconds=time.time() - started_at,
            )


async def _recover_stale_runs() -> list[str]:
    """Recovery uses the application's own session factory, independent of the request lifecycle."""
    from app.container import open_run_service

    async with open_run_service() as service:
        return await service.recover_stale_runs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    logging.getLogger().setLevel(config.logging.level)
    logger.info(
        "Config loaded path=%s AI enabled=%s provider=%s model=%s Jev enabled=%s model=%s Repair mode=%s require_jev=%s",
        config_manager.path,
        config.ai.enabled,
        config.ai.provider,
        config.ai.model,
        config.jev.enabled,
        config.jev.model,
        config.repair.mode,
        config.repair.require_jev,
    )
    # Initialize database tables
    await init_db()
    from app.container import get_requirement_lifecycle_service, recover_failure_analyses

    await recover_failure_analyses()

    await get_requirement_lifecycle_service().recover_interrupted()
    from app.container import get_ai_settings_service

    await get_ai_settings_service().load_runtime_config()
    # Close runs abandoned by a previous process: without this a crashed run stays RUNNING forever
    # and every pass-rate and coverage figure built on it stays wrong.
    try:
        recovered = await _recover_stale_runs()
        if recovered:
            logger.warning("Recovered %d stale run(s) at startup: %s", len(recovered), ", ".join(recovered))
    except Exception as error:  # pragma: no cover - startup must never fail because of recovery
        logger.warning("Stale run recovery skipped: %s", error)
    from app.container import get_task_runtime_service

    task_runtime = get_task_runtime_service()
    app.state.task_runtime = task_runtime
    await task_runtime.start()
    from app.container import get_platform_health_service

    readiness_task = asyncio.create_task(get_platform_health_service().check(refresh=True))
    app.state.readiness_task = readiness_task
    try:
        yield
    finally:
        if not readiness_task.done():
            readiness_task.cancel()
        await asyncio.gather(readiness_task, return_exceptions=True)
        await task_runtime.stop()
        from app.container import recorder_service
        from app.services.debug_session_service import debug_session_service

        await recorder_service.close_all()
        await debug_session_service.close_all()
        await engine.dispose()


app = FastAPI(
    title="AI QA Platform API",
    version="1.0.0",
    description="Production-oriented AI QA Intelligence Platform",
    lifespan=lifespan,
    # Single application-level authorization guard: authenticates every non-public request and
    # enforces the resource policy table in app/api/authz.py.
    dependencies=[Depends(authorize_request)],
)
app.add_middleware(StreamTicketQuerySanitizer)
app.add_exception_handler(HTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_config().api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(RequestMetricsMiddleware)


# Include API Routers
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(teams_router, prefix="/api")
app.include_router(workers_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(debugger_router, prefix="/api")
app.include_router(decision_router, prefix="/api")
app.include_router(lifecycle_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(recorder_router, prefix="/api")
app.include_router(requirements_router, prefix="/api")
app.include_router(test_designs_router, prefix="/api")
app.include_router(test_cases_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(git_pr_router, prefix="/api")
app.include_router(jira_router, prefix="/api")
app.include_router(testrail_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(quality_router, prefix="/api")
app.include_router(quality_discovery_router, prefix="/api")
app.include_router(releases_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(runners_router, prefix="/api")
app.include_router(failures_router, prefix="/api")
app.include_router(flaky_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(onboarding_router, prefix="/api")
app.include_router(qa_assistant_router, prefix="/api")
app.include_router(language_service_router, prefix="/api")
app.include_router(runtime_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "platform": "AI QA Platform",
        "status": "online",
        "version": "0.3.0",
        "docs": "/docs",
        "api_prefix": "/api",
    }
