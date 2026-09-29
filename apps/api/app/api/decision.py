from __future__ import annotations

from fastapi import APIRouter, Depends
from project_model.models import (
    DecisionConnectionResult,
    DecisionPlaygroundResult,
    DecisionRequest,
    JevSettingsResponse,
    JevSettingsUpdate,
    Permission,
    User,
)

from app.api.authz import get_current_user, require_permission
from app.services.decision_service import DecisionService
from app.services.decision_settings_service import DecisionSettingsService

router = APIRouter(prefix="/decision", tags=["Decision Layer"])


@router.get("/settings", response_model=JevSettingsResponse)
async def get_jev_settings(
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
) -> JevSettingsResponse:
    return await DecisionSettingsService().get_response()


@router.put("/settings", response_model=JevSettingsResponse)
async def save_jev_settings(
    update: JevSettingsUpdate,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
) -> JevSettingsResponse:
    return await DecisionSettingsService().save(update)


@router.post("/test-connection", response_model=DecisionConnectionResult)
async def test_jev_connection(
    update: JevSettingsUpdate,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
) -> DecisionConnectionResult:
    return await DecisionService().test_connection(update)


@router.post("/choose", response_model=DecisionPlaygroundResult)
async def decide(
    request: DecisionRequest,
    _: User = Depends(get_current_user),
    __: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
) -> DecisionPlaygroundResult:
    result = await DecisionService().choose(request)
    return DecisionPlaygroundResult(decision_name=request.name, **result.model_dump())
