"""API access to the shared typed configuration snapshot.

New production code should use ``get_config()`` and its section models. ``settings`` is a
read-compatible adapter for existing tests and older modules; it never loads another source.
"""

from __future__ import annotations

from pathlib import Path

from platform_config import AppConfig, ConfigManager

config_manager = ConfigManager()


def get_config() -> AppConfig:
    return config_manager.get()


def _legacy_values(config: AppConfig) -> dict[str, object]:
    return {
        "api_host": config.api.host,
        "api_port": config.api.port,
        "database_url": config.database.url,
        "auth_required": config.app.auth_required,
        "app_secret_key": config.app.secret_key.get_secret_value(),
        "auth_token_ttl_seconds": config.app.auth_token_ttl_seconds,
        "runtime_dir": config.app.runtime_dir,
        "workspace_storage_dir": config.app.workspace_storage_dir,
        "artifact_storage_dir": config.app.artifact_storage_dir,
        "qa_ai_provider": config.ai.provider,
        "qa_ai_api_key": config.ai.api_key.get_secret_value(),
        "qa_ai_base_url": config.ai.base_url,
        "qa_ai_model": config.ai.model,
        "qa_ai_timeout": config.ai.timeout_seconds,
        "qa_ai_max_retries": config.ai.retries,
        "browser_proxy_url": config.browser.proxy_url.get_secret_value(),
        "browser_proxy_bypass": config.browser.proxy_bypass,
        "jev_enabled": config.jev.enabled,
        "jev_api_key": config.jev.api_key.get_secret_value(),
        "jev_model": config.jev.model,
        "jev_base_url": config.jev.base_url,
        "jev_timeout": config.jev.timeout_seconds,
        "jev_minimum_confidence": config.jev.minimum_confidence,
        "failure_auto_repair_mode": config.repair.mode,
        "failure_auto_repair_max_attempts": config.repair.max_attempts,
        "cors_origins": config.api.cors_origins,
    }


_LEGACY_PATHS = {
    "api_host": ("api", "host"),
    "api_port": ("api", "port"),
    "database_url": ("database", "url"),
    "auth_required": ("app", "auth_required"),
    "app_secret_key": ("app", "secret_key"),
    "auth_token_ttl_seconds": ("app", "auth_token_ttl_seconds"),
    "runtime_dir": ("app", "runtime_dir"),
    "workspace_storage_dir": ("app", "workspace_storage_dir"),
    "artifact_storage_dir": ("app", "artifact_storage_dir"),
    "qa_ai_provider": ("ai", "provider"),
    "qa_ai_api_key": ("ai", "api_key"),
    "qa_ai_base_url": ("ai", "base_url"),
    "qa_ai_model": ("ai", "model"),
    "qa_ai_timeout": ("ai", "timeout_seconds"),
    "qa_ai_max_retries": ("ai", "retries"),
    "browser_proxy_url": ("browser", "proxy_url"),
    "browser_proxy_bypass": ("browser", "proxy_bypass"),
    "jev_enabled": ("jev", "enabled"),
    "jev_api_key": ("jev", "api_key"),
    "jev_model": ("jev", "model"),
    "jev_base_url": ("jev", "base_url"),
    "jev_timeout": ("jev", "timeout_seconds"),
    "jev_minimum_confidence": ("jev", "minimum_confidence"),
    "failure_auto_repair_mode": ("repair", "mode"),
    "failure_auto_repair_max_attempts": ("repair", "max_attempts"),
    "cors_origins": ("api", "cors_origins"),
}


class _SettingsCompatibilityView:
    def __getattr__(self, name: str):
        try:
            return _legacy_values(get_config())[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name: str, value: object) -> None:
        """Preserve test monkeypatches as immutable snapshot swaps, never in-place mutation."""
        path = _LEGACY_PATHS.get(name)
        if path is None:
            raise AttributeError(name)
        config = get_config()
        section = getattr(config, path[0])
        if name in {"app_secret_key", "qa_ai_api_key", "browser_proxy_url", "jev_api_key"}:
            from pydantic import SecretStr

            value = SecretStr(str(value))
        section_copy = section.model_copy(update={path[1]: value})
        config_copy = config.model_copy(update={path[0]: section_copy})
        config_manager.replace_for_test(config_copy)


settings = _SettingsCompatibilityView()

# Preserve the previous import-time directory setup, now based on the single AppConfig snapshot.
for _path in (get_config().app.runtime_dir, get_config().app.workspace_storage_dir, get_config().app.artifact_storage_dir):
    Path(_path).mkdir(parents=True, exist_ok=True)
