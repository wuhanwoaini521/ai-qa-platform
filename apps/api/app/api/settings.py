from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from platform_config import ConfigLoadError
from project_model.models import Permission, User

from app.api.authz import require_permission
from app.services.ai_settings_service import AISettingsService
from app.services.effective_config_service import EffectiveConfigService
from app.settings import config_manager, get_config

router = APIRouter(prefix="/settings", tags=["Runtime Configuration"])
logger = logging.getLogger("app.config")


def get_effective_config_service() -> EffectiveConfigService:
    from app.container import get_repository_scope_factory

    return EffectiveConfigService(get_repository_scope_factory())


def get_runtime_ai_settings_service() -> AISettingsService:
    from app.container import get_ai_settings_service

    return get_ai_settings_service()


@router.get("/effective")
async def get_effective_config(
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: EffectiveConfigService = Depends(get_effective_config_service),
):
    return await service.diagnostics()


@router.get("/sources")
async def get_config_sources(
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    service: EffectiveConfigService = Depends(get_effective_config_service),
):
    return {"config_path": str(config_manager.path), "sources": service.sources()}


@router.post("/reload")
async def reload_config(
    _user: User = Depends(require_permission(Permission.SECURITY_ADMIN)),
    ai_settings: AISettingsService = Depends(get_runtime_ai_settings_service),
):
    try:
        result = config_manager.reload()
    except ConfigLoadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not result.applied:
        return {
            "applied": False,
            "config_path": result.config_path,
            "changed": list(result.changed),
            "restart_required": list(result.restart_required),
        }
    await ai_settings.load_runtime_config()
    logging.getLogger().setLevel(get_config().logging.level)
    logger.info("Runtime config reloaded changed_fields=%s", ",".join(result.changed))
    return {
        "applied": True,
        "config_path": result.config_path,
        "changed": list(result.changed),
        "restart_required": [],
    }
