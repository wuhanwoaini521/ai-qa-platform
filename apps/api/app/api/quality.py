from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import (
    ImpactAnalysisRequest,
    ImpactAnalysisResult,
    QualityCoverageSummary,
    QualityRiskMatrix,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import get_db
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_design_repo import TestDesignRepository
from app.repositories.test_run_repo import TestRunRepository
from app.services.quality_intelligence_service import QualityIntelligenceService
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/quality", tags=["Quality Intelligence & Coverage"])


def get_quality_service(session: AsyncSession = Depends(get_db)) -> QualityIntelligenceService:
    req_repo = RequirementRepository(session)
    tc_repo = TestCaseRepository(session)
    td_repo = TestDesignRepository(session)
    binding_repo = AutomationBindingRepository(session)
    run_repo = TestRunRepository(session)
    history_repo = RunHistoryRepository(lambda: session)
    ws_service = WorkspaceService()

    return QualityIntelligenceService(
        requirement_repo=req_repo,
        test_case_repo=tc_repo,
        test_design_repo=td_repo,
        binding_repo=binding_repo,
        test_run_repo=run_repo,
        history_repo=history_repo,
        workspace_service=ws_service,
    )


@router.get("/coverage", response_model=QualityCoverageSummary)
async def get_quality_coverage(
    project_id: str = Query(...),
    service: QualityIntelligenceService = Depends(get_quality_service),
):
    return await service.calculate_coverage(project_id)


@router.get("/risk-matrix", response_model=QualityRiskMatrix)
async def get_quality_risk_matrix(
    project_id: str = Query(...),
    service: QualityIntelligenceService = Depends(get_quality_service),
):
    return await service.calculate_risk_matrix(project_id)


@router.post("/impact-analysis", response_model=ImpactAnalysisResult)
async def analyze_impact_and_select_regression(
    body: ImpactAnalysisRequest,
    service: QualityIntelligenceService = Depends(get_quality_service),
):
    return await service.analyze_impact_and_select_regression(
        project_id=body.project_id,
        changed_files=body.changed_files,
        workspace_id=body.workspace_id,
    )
