from __future__ import annotations

from typing import Any

from platform_config import ConfigManager, sanitize_config_value

from app.ports.repository_scope import RepositoryScopeFactory
from app.settings import config_manager, get_config


class EffectiveConfigService:
    def __init__(self, repository_scope: RepositoryScopeFactory | None = None) -> None:
        self.repository_scope = repository_scope

    async def diagnostics(self) -> dict[str, Any]:
        config = get_config()
        legacy_db_settings_detected = False
        if self.repository_scope is not None:
            async with self.repository_scope() as repositories:
                legacy_db_settings_detected = bool(
                    await repositories.provider_settings.get_default()
                    or await repositories.decision_settings.get_jev()
                )

        ai_status = (
            "DISABLED"
            if not config.ai.enabled
            else "SIMULATION"
            if config.ai.provider == "fake"
            else "READY_CONFIGURED"
            if config.ai.api_key.get_secret_value()
            else "BLOCKED_MISSING_API_KEY"
        )
        jev_status = (
            "DISABLED"
            if not config.jev.enabled or not config.features.jev_decision
            else "READY_CONFIGURED"
            if config.jev.api_key.get_secret_value()
            else "BLOCKED_MISSING_API_KEY"
        )
        repair_status = (
            "DISABLED"
            if not config.repair.enabled or not config.features.ai_repair or config.repair.mode == "OFF"
            else "READY_CONFIGURED"
            if config.ai.enabled and config.ai.provider != "fake" and config.ai.api_key.get_secret_value()
            and (not config.repair.require_jev or jev_status == "READY_CONFIGURED")
            else "BLOCKED"
        )
        return {
            "config_path": str(config_manager.path),
            "schema_version": config.version,
            "source_of_truth": "config/config.yaml",
            "restart_required_fields": sorted(ConfigManager.RESTART_REQUIRED_FIELDS),
            "legacy_database_settings_detected": legacy_db_settings_detected,
            "runtime_state": {"ai": ai_status, "jev": jev_status, "repair": repair_status},
            "config": sanitize_config_value(config.model_dump(mode="python")),
        }

    def sources(self) -> dict[str, str]:
        return config_manager.source_map()
