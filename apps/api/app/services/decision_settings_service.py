from __future__ import annotations

from dataclasses import dataclass

from project_model.models import JevSettingsResponse, JevSettingsUpdate

from app.ports.repository_scope import RepositoryScopeFactory
from app.services.secret_store import SecretStore
from app.settings import get_config

PROVIDER_NAME = "jev"


@dataclass(frozen=True)
class DecisionRuntimeConfig:
    provider: str
    enabled: bool
    api_key: str
    model: str
    base_url: str
    timeout: float
    minimum_confidence: float
    retries: int = 1


class DecisionSettingsService:
    def __init__(
        self, repository_scope: RepositoryScopeFactory | None = None, secret_store: SecretStore | None = None
    ) -> None:
        self.repository_scope = repository_scope
        self.secret_store = secret_store

    async def get_response(self) -> JevSettingsResponse:
        config = await self.get_runtime_config()
        api_key = config.api_key
        return JevSettingsResponse(
            enabled=config.enabled,
            api_key_configured=bool(api_key),
            api_key_masked="••••••••••••" if api_key else None,
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout,
            minimum_confidence=config.minimum_confidence,
        )

    async def get_runtime_config(self) -> DecisionRuntimeConfig:
        config = get_config().jev
        return DecisionRuntimeConfig(
            provider=config.provider,
            enabled=config.enabled and get_config().features.jev_decision,
            api_key=config.api_key.get_secret_value(),
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            minimum_confidence=config.minimum_confidence,
            retries=config.retries,
        )

    async def config_for_test(self, update: JevSettingsUpdate | None = None) -> DecisionRuntimeConfig:
        stored = await self.get_runtime_config()
        if update is None:
            return stored
        candidate_key = update.api_key.strip() if update.api_key is not None else ""
        if update.clear_api_key:
            candidate_key = ""
        elif not candidate_key:
            candidate_key = stored.api_key
        return DecisionRuntimeConfig(
            provider=PROVIDER_NAME,
            enabled=update.enabled,
            api_key=candidate_key,
            model=update.model,
            base_url=update.base_url,
            timeout=update.timeout,
            minimum_confidence=update.minimum_confidence,
            retries=stored.retries,
        )

    async def save(self, update: JevSettingsUpdate) -> JevSettingsResponse:
        raise RuntimeError("Jev runtime settings are managed by config/config.yaml; edit it and call reload")
