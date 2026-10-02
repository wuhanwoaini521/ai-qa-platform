from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from project_model.models import (
    AIProviderConnectionResult,
    AIProviderSettingsResponse,
    AIProviderSettingsUpdate,
    AIStatusResponse,
    AIUsageSummary,
    Permission,
    RequirementAnalysisDTO,
    TestCaseGenerationItem,
    TestDesignSuggestion,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authz import require_permission
from app.persistence.database import get_db
from app.repositories.ai_repo import AIRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.ai_service import AIService
from app.services.ai_settings_service import AISettingsService

router = APIRouter(prefix="/ai", tags=["Production AI Intelligence"])


def get_ai_settings_service() -> AISettingsService:
    return AISettingsService()


@router.get("/settings", response_model=AIProviderSettingsResponse)
async def get_ai_provider_settings(service: AISettingsService = Depends(get_ai_settings_service)):
    """Read normal AI provider settings without exposing its API key."""
    return await service.get_settings()


@router.put("/settings", response_model=AIProviderSettingsResponse)
async def save_ai_provider_settings(
    update: AIProviderSettingsUpdate,
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: AISettingsService = Depends(get_ai_settings_service),
):
    return await service.save(update)


@router.post("/test-connection", response_model=AIProviderConnectionResult)
async def test_ai_provider_connection(
    update: AIProviderSettingsUpdate,
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: AISettingsService = Depends(get_ai_settings_service),
):
    return await service.test_connection(update)


def get_ai_service(session: AsyncSession = Depends(get_db)) -> AIService:
    return AIService(
        # AIRepository commits invocation telemetry in its own session. Passing the request
        # session through a lambda would let record_invocation close the caller's session.
        ai_repo=AIRepository(),
        requirement_repo=RequirementRepository(session),
        test_design_repo=TestDesignRepository(session),
        test_case_repo=TestCaseRepository(session),
        test_run_repo=TestRunRepository(session),
        project_repo=ProjectRepository(session),
    )


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status(service: AIService = Depends(get_ai_service)):
    """Retrieve current AI Provider operational health (never exposes API secrets)."""
    return await service.get_status()


@router.get("/usage", response_model=AIUsageSummary)
async def get_ai_usage(
    limit: int = Query(default=50, ge=1, le=200),
    since: datetime | None = None,
    feature: str | None = Query(default=None, max_length=100),
    service: AIService = Depends(get_ai_service),
):
    """Retrieve historical AI invocation telemetry and token usage."""
    return await service.get_usage(limit=limit, since=since, feature=feature)


@router.get("/system-health")
async def system_health(refresh: bool = False):
    """Detailed checks require authentication; public probes retain their small response."""
    from app.services.platform_health_service import platform_health_service

    return await platform_health_service.check(refresh=refresh)


@router.get("/prompts")
async def prompt_versions():
    from qa_core.prompts import PROMPT_REGISTRY

    return [{"feature": item.prompt_id, "version": item.version} for item in PROMPT_REGISTRY.values()]


@router.post("/requirements/{requirement_id}/analyze", response_model=RequirementAnalysisDTO)
async def analyze_requirement(
    requirement_id: str,
    service: AIService = Depends(get_ai_service),
):
    """Analyze a requirement for testability, edge case risks, and coverage dimensions."""
    try:
        return await service.analyze_requirement(requirement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI Requirement Analysis failed ({type(e).__name__}). See AI Usage for invocation status.",
        )


@router.post("/requirements/{requirement_id}/generate-designs", response_model=list[TestDesignSuggestion])
async def generate_test_designs(
    requirement_id: str,
    service: AIService = Depends(get_ai_service),
):
    """Generate structured test design proposals across functional, boundary, negative, and API dimensions."""
    try:
        return await service.generate_test_designs(requirement_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI Test Design Generation failed ({type(e).__name__}). See AI Usage for invocation status.",
        )


@router.post("/test-designs/{test_design_id}/generate-cases", response_model=list[TestCaseGenerationItem])
async def generate_test_cases(
    test_design_id: str,
    service: AIService = Depends(get_ai_service),
):
    """Generate comprehensive test cases for a specific test design."""
    try:
        return await service.generate_test_cases(test_design_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI Test Case Generation failed ({type(e).__name__}). See AI Usage for invocation status.",
        )
