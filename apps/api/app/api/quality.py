from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from project_model.models import (
    ImpactAnalysisRequest,
    ImpactAnalysisResult,
    LocatorRepairFunnelResponse,
    QualityCoverageSummary,
    QualityRiskMatrix,
    User,
)

from app.api.authz import get_current_user
from app.api.project_acl import enforce_project_access, project_query_access
from app.container import get_locator_repair_funnel_service, get_quality_service
from app.services.locator_repair_funnel_service import LocatorRepairFunnelService
from app.services.quality_intelligence_service import QualityIntelligenceService

router = APIRouter(
    prefix="/quality",
    tags=["Quality Intelligence & Coverage"],
    dependencies=[Depends(project_query_access("project_id"))],
)


@router.get("/repair-funnel", response_model=LocatorRepairFunnelResponse)
async def get_locator_repair_funnel(
    project_id: str = Query(...),
    service: LocatorRepairFunnelService = Depends(get_locator_repair_funnel_service),
):
    return await service.summarize(project_id)


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
    user: User = Depends(get_current_user),
):
    await enforce_project_access(user, body.project_id)
    return await service.analyze_impact_and_select_regression(
        project_id=body.project_id,
        changed_files=body.changed_files,
        workspace_id=body.workspace_id,
    )
