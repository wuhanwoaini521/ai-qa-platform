from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from project_model.models import (
    DecisionConnectionResult,
    DecisionPlaygroundResult,
    DecisionRequest,
    DecisionSamplesEvaluationRequest,
    DecisionSamplesEvaluationResponse,
    JevRuntimeCheckResponse,
    JevSettingsResponse,
    JevSettingsUpdate,
    Permission,
    User,
)

from app.api.authz import get_current_user, require_permission
from app.container import get_decision_service, get_decision_settings_service
from app.services.decision_sample_evaluation import evaluate_decision_samples
from app.services.decision_service import DecisionService
from app.services.decision_settings_service import DecisionSettingsService

router = APIRouter(prefix="/decision", tags=["Decision Layer"])


@router.get("/settings", response_model=JevSettingsResponse)
async def get_jev_settings(
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: DecisionSettingsService = Depends(get_decision_settings_service),
) -> JevSettingsResponse:
    return await service.get_response()


@router.put("/settings", response_model=JevSettingsResponse)
async def save_jev_settings(
    update: JevSettingsUpdate,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: DecisionSettingsService = Depends(get_decision_settings_service),
) -> JevSettingsResponse:
    try:
        return await service.save(update)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/test-connection", response_model=DecisionConnectionResult)
async def test_jev_connection(
    update: JevSettingsUpdate | None = None,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionConnectionResult:
    return await service.test_connection(update)


@router.post("/runtime-check", response_model=JevRuntimeCheckResponse)
async def check_jev_runtime(
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: DecisionService = Depends(get_decision_service),
) -> JevRuntimeCheckResponse:
    return await service.runtime_check()


@router.post("/evaluate-samples", response_model=DecisionSamplesEvaluationResponse)
async def evaluate_samples(
    request: DecisionSamplesEvaluationRequest,
    _: User = Depends(get_current_user),
) -> DecisionSamplesEvaluationResponse:
    try:
        result = evaluate_decision_samples(
            request.samples,
            threshold=request.threshold,
            input_cost_per_million_usd=request.input_cost_per_million_usd,
            output_cost_per_million_usd=request.output_cost_per_million_usd,
        )
        return DecisionSamplesEvaluationResponse.model_validate(result)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/choose", response_model=DecisionPlaygroundResult)
async def decide(
    request: DecisionRequest,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionPlaygroundResult:
    result = await service.choose(request)
    return DecisionPlaygroundResult(decision_name=request.name, **result.model_dump())
