from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import (
    AIStatusResponse,
    AIUsageSummary,
    RequirementAnalysisDTO,
    TestCaseGenerationItem,
    TestDesignSuggestion,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.ai_repo import AIRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["Production AI Intelligence"])


def get_ai_service(session: AsyncSession = Depends(get_db)) -> AIService:
    return AIService(
        ai_repo=AIRepository(lambda: session),
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
async def get_ai_usage(limit: int = 50, service: AIService = Depends(get_ai_service)):
    """Retrieve historical AI invocation telemetry and token usage."""
    return await service.get_usage(limit=limit)


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
        raise HTTPException(status_code=500, detail=f"AI Requirement Analysis failed: {e}")


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
        raise HTTPException(status_code=500, detail=f"AI Test Design Generation failed: {e}")


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
        raise HTTPException(status_code=500, detail=f"AI Test Case Generation failed: {e}")
