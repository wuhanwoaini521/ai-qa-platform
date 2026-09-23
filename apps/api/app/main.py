from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    dashboard_router,
    failures_router,
    health_router,
    projects_router,
    qa_assistant_router,
    requirements_router,
    runs_router,
    test_cases_router,
    test_designs_router,
    workspaces_router,
)
from app.persistence.database import init_db
from app.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    await init_db()
    yield


app = FastAPI(
    title="AI QA Platform API",
    version="0.2.0",
    description="Backend API services for AI QA Engineering Platform",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(requirements_router, prefix="/api")
app.include_router(test_designs_router, prefix="/api")
app.include_router(test_cases_router, prefix="/api")
app.include_router(workspaces_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(failures_router, prefix="/api")
app.include_router(qa_assistant_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "platform": "AI QA Platform",
        "status": "online",
        "docs": "/docs",
        "api_prefix": "/api",
    }
