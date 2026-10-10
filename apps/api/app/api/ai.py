from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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

from app.api.authz import require_permission
from app.container import get_ai_service, get_ai_settings_service, get_platform_health_service
from app.services.ai_service import AIService
from app.services.ai_settings_service import AISettingsService
from app.services.operation_trace import stream_operation
from app.services.platform_health_service import PlatformHealthService

router = APIRouter(prefix="/ai", tags=["Production AI Intelligence"])


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
    try:
        return await service.save(update)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/test-connection", response_model=AIProviderConnectionResult)
async def test_ai_provider_connection(
    update: AIProviderSettingsUpdate | None = None,
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: AISettingsService = Depends(get_ai_settings_service),
):
    return await service.test_connection(update, verify_structured_output=True)


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
async def system_health(
    refresh: bool = False,
    service: PlatformHealthService = Depends(get_platform_health_service),
):
    """Detailed checks require authentication; public probes retain their small response."""
    return await service.check(refresh=refresh)


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


@router.post("/requirements/{requirement_id}/analyze/stream")
async def stream_requirement_analysis(requirement_id: str, service: AIService = Depends(get_ai_service)):
    return StreamingResponse(
        stream_operation(lambda: service.analyze_requirement(requirement_id), "分析需求"),
        media_type="text/event-stream",
    )


@router.post("/requirements/{requirement_id}/generate-designs/stream")
async def stream_design_generation(requirement_id: str, service: AIService = Depends(get_ai_service)):
    return StreamingResponse(
        stream_operation(lambda: service.generate_test_designs(requirement_id), "生成测试设计"),
        media_type="text/event-stream",
    )


@router.post("/test-designs/{design_id}/generate-cases/stream")
async def stream_case_generation(design_id: str, service: AIService = Depends(get_ai_service)):
    return StreamingResponse(
        stream_operation(lambda: service.generate_test_cases(design_id), "生成测试用例"), media_type="text/event-stream"
    )
