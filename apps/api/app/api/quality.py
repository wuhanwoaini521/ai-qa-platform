from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import (
    ImpactAnalysisRequest,
    ImpactAnalysisResult,
    QualityCoverageSummary,
    QualityRiskMatrix,
)

from app.container import get_quality_service
from app.services.quality_intelligence_service import QualityIntelligenceService

router = APIRouter(prefix="/quality", tags=["Quality Intelligence & Coverage"])


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
