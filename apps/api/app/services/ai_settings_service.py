from __future__ import annotations

from dataclasses import dataclass

from project_model.models import (
    AIProviderConnectionResult,
    AIProviderSettingsResponse,
    AIProviderSettingsUpdate,
)
from qa_core.ai.models import ProviderHealth
from qa_core.ai.provider import FakeAIProvider, OpenAICompatibleProvider
from qa_core.ai.registry import AIProviderRegistry
from sqlalchemy import select

from app.persistence.database import async_session_factory
from app.persistence.models import AIProviderConfigORM
from app.services.secret_store import SecretStore
from app.settings import settings


@dataclass(frozen=True)
class AIRuntimeConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout: float
    max_retries: int


class AISettingsService:
    """Persists the normal AI provider separately from Jev and activates it for API requests."""

    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self.secret_store = secret_store or SecretStore(master_key=settings.app_secret_key)

    def _environment_config(self) -> AIRuntimeConfig:
        return AIRuntimeConfig(
            provider=settings.qa_ai_provider,
            api_key=settings.qa_ai_api_key,
            model=settings.qa_ai_model,
            base_url=settings.qa_ai_base_url,
            timeout=settings.qa_ai_timeout,
            max_retries=settings.qa_ai_max_retries,
        )

    async def _row(self) -> AIProviderConfigORM | None:
        async with async_session_factory() as session:
            result = await session.execute(select(AIProviderConfigORM).where(AIProviderConfigORM.id == "default"))
            return result.scalar_one_or_none()

    @staticmethod
    def _config_from_row(row: AIProviderConfigORM, secret_store: SecretStore) -> AIRuntimeConfig:
        return AIRuntimeConfig(
            provider=row.provider,
            api_key=secret_store.decrypt_secret(row.encrypted_api_key or ""),
            model=row.model,
            base_url=row.base_url,
            timeout=row.timeout,
            max_retries=row.max_retries,
        )

    async def _effective_config(self) -> AIRuntimeConfig:
        row = await self._row()
        return self._config_from_row(row, self.secret_store) if row else self._environment_config()

    @staticmethod
    def _response(config: AIRuntimeConfig) -> AIProviderSettingsResponse:
        masked = SecretStore.mask_secret(config.api_key)
        return AIProviderSettingsResponse(
            provider=config.provider,
            api_key_configured=bool(config.api_key),
            api_key_masked=masked or None,
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    @staticmethod
    def _activate(config: AIRuntimeConfig) -> None:
        AIProviderRegistry.configure_runtime(
            {
                "provider": config.provider,
                "api_key": config.api_key,
                "model": config.model,
                "base_url": config.base_url,
                "timeout": str(config.timeout),
                "max_retries": str(config.max_retries),
            }
        )

    async def get_settings(self) -> AIProviderSettingsResponse:
        config = await self._effective_config()
        self._activate(config)
        return self._response(config)

    async def load_runtime_config(self) -> None:
        """Load persisted UI settings on startup; fall back to environment defaults."""
        self._activate(await self._effective_config())

    async def save(self, update: AIProviderSettingsUpdate) -> AIProviderSettingsResponse:
        async with async_session_factory() as session:
            result = await session.execute(select(AIProviderConfigORM).where(AIProviderConfigORM.id == "default"))
            row = result.scalar_one_or_none()
            current_key = (
                self.secret_store.decrypt_secret(row.encrypted_api_key or "") if row else settings.qa_ai_api_key
            )
            if update.clear_api_key:
                api_key = ""
            elif update.api_key and update.api_key.strip():
                api_key = update.api_key.strip()
            else:
                api_key = current_key

            encrypted_key = self.secret_store.encrypt_secret(api_key) if api_key else None
            if row is None:
                row = AIProviderConfigORM(id="default")
                session.add(row)
            row.provider = update.provider
            row.encrypted_api_key = encrypted_key
            row.model = update.model.strip()
            row.base_url = update.base_url.strip().rstrip("/")
            row.timeout = update.timeout
            row.max_retries = update.max_retries
            await session.commit()
            await session.refresh(row)
            config = self._config_from_row(row, self.secret_store)

        self._activate(config)
        return self._response(config)

    async def _config_for_update(self, update: AIProviderSettingsUpdate) -> AIRuntimeConfig:
        current = await self._effective_config()
        api_key = (
            ""
            if update.clear_api_key
            else (update.api_key.strip() if update.api_key and update.api_key.strip() else current.api_key)
        )
        return AIRuntimeConfig(
            provider=update.provider,
            api_key=api_key,
            model=update.model.strip(),
            base_url=update.base_url.strip().rstrip("/"),
            timeout=update.timeout,
            max_retries=update.max_retries,
        )

    async def test_connection(self, update: AIProviderSettingsUpdate | None = None) -> AIProviderConnectionResult:
        config = await self._config_for_update(update) if update else await self._effective_config()
        if config.provider == "fake":
            health = await FakeAIProvider(model=config.model).check_health()
        else:
            health = await OpenAICompatibleProvider(
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
            ).check_health()
        return AIProviderConnectionResult(
            connected=health.status in (ProviderHealth.AVAILABLE, ProviderHealth.FALLBACK_ONLY),
            provider=health.provider,
            status=health.status.value,
            message=health.message,
            model=health.model,
        )
