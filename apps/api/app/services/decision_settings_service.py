from __future__ import annotations

from dataclasses import dataclass

from project_model.models import JevSettingsResponse, JevSettingsUpdate
from sqlalchemy import select

from app.persistence.database import async_session_factory
from app.persistence.models import DecisionProviderConfigORM
from app.services.secret_store import SecretStore
from app.settings import settings

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


class DecisionSettingsService:
    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self.secret_store = secret_store or SecretStore(master_key=settings.app_secret_key)

    async def _row(self) -> DecisionProviderConfigORM | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DecisionProviderConfigORM).where(DecisionProviderConfigORM.provider == PROVIDER_NAME)
            )
            return result.scalar_one_or_none()

    async def get_response(self) -> JevSettingsResponse:
        row = await self._row()
        if row is None:
            api_key_configured = bool(settings.jev_api_key)
            return JevSettingsResponse(
                enabled=settings.jev_enabled,
                api_key_configured=api_key_configured,
                api_key_masked="••••••••••••" if api_key_configured else None,
                model=settings.jev_model,
                base_url=settings.jev_base_url,
                timeout=settings.jev_timeout,
                minimum_confidence=settings.jev_minimum_confidence,
            )
        api_key = self.secret_store.decrypt_secret(row.encrypted_api_key or "")
        return JevSettingsResponse(
            enabled=row.enabled,
            api_key_configured=bool(api_key),
            api_key_masked="••••••••••••" if api_key else None,
            model=row.model,
            base_url=row.base_url,
            timeout=row.timeout,
            minimum_confidence=row.minimum_confidence,
        )

    async def get_runtime_config(self) -> DecisionRuntimeConfig:
        row = await self._row()
        if row is None:
            return DecisionRuntimeConfig(
                provider=PROVIDER_NAME,
                enabled=settings.jev_enabled,
                api_key=settings.jev_api_key,
                model=settings.jev_model,
                base_url=settings.jev_base_url,
                timeout=settings.jev_timeout,
                minimum_confidence=settings.jev_minimum_confidence,
            )
        return DecisionRuntimeConfig(
            provider=PROVIDER_NAME,
            enabled=row.enabled,
            api_key=self.secret_store.decrypt_secret(row.encrypted_api_key or ""),
            model=row.model,
            base_url=row.base_url,
            timeout=row.timeout,
            minimum_confidence=row.minimum_confidence,
        )

    async def config_for_test(self, update: JevSettingsUpdate) -> DecisionRuntimeConfig:
        stored = await self.get_runtime_config()
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
        )

    async def save(self, update: JevSettingsUpdate) -> JevSettingsResponse:
        model = update.model.strip()
        base_url = update.base_url.strip().rstrip("/")
        async with async_session_factory() as session:
            row = await session.get(DecisionProviderConfigORM, PROVIDER_NAME)
            if row is None:
                initial_key = update.api_key.strip() if update.api_key and update.api_key.strip() else settings.jev_api_key
                row = DecisionProviderConfigORM(
                    provider=PROVIDER_NAME,
                    enabled=update.enabled,
                    encrypted_api_key=self.secret_store.encrypt_secret(initial_key) if initial_key else None,
                    model=model,
                    base_url=base_url,
                    timeout=update.timeout,
                    minimum_confidence=update.minimum_confidence,
                )
                session.add(row)
            else:
                row.enabled = update.enabled
                row.model = model
                row.base_url = base_url
                row.timeout = update.timeout
                row.minimum_confidence = update.minimum_confidence

            if update.clear_api_key:
                row.encrypted_api_key = None
            elif update.api_key and update.api_key.strip():
                row.encrypted_api_key = self.secret_store.encrypt_secret(update.api_key.strip())

            await session.commit()
        return await self.get_response()
