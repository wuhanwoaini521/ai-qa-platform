from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Literal

from project_model.models import (
    AIProviderConnectionResult,
    AIProviderRuntimeState,
    AIProviderSettingsResponse,
    AIProviderSettingsUpdate,
    AIProviderStatus,
    AIStatusResponse,
)
from pydantic import BaseModel
from qa_core.ai.models import AICompletionRequest, ProviderHealth
from qa_core.ai.provider import FakeAIProvider, OpenAICompatibleProvider, clean_json_text
from qa_core.ai.registry import AIProviderRegistry
from sqlalchemy import select

from app.persistence.database import async_session_factory
from app.persistence.models import AIProviderConfigORM
from app.services.secret_store import SecretStore
from app.settings import settings

_health_lock = asyncio.Lock()
_health_cache: tuple[str, float, AIStatusResponse] | None = None


class _StructuredOutputProbe(BaseModel):
    json_mode: Literal[True]


@dataclass(frozen=True)
class AIRuntimeConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout: float
    max_retries: int
    max_request_tokens: int = 16000
    max_daily_requests: int = 1000
    max_task_calls: int = 8


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
            max_request_tokens=row.max_request_tokens,
            max_daily_requests=row.max_daily_requests,
            max_task_calls=row.max_task_calls,
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
            max_request_tokens=config.max_request_tokens,
            max_daily_requests=config.max_daily_requests,
            max_task_calls=config.max_task_calls,
        )

    @staticmethod
    def _activate(config: AIRuntimeConfig) -> None:
        from app.services.ai_execution_service import AIExecutionService

        AIProviderRegistry.configure_runtime(
            {
                "provider": config.provider,
                "api_key": config.api_key,
                "model": config.model,
                "base_url": config.base_url,
                "timeout": str(config.timeout),
                "max_retries": str(config.max_retries),
                "max_task_calls": str(config.max_task_calls),
            }
        )
        AIProviderRegistry.set_middleware(
            lambda provider: AIExecutionService(
                provider,
                max_request_tokens=config.max_request_tokens,
                max_daily_requests=config.max_daily_requests,
            )
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
            row.max_request_tokens = update.max_request_tokens
            row.max_daily_requests = update.max_daily_requests
            row.max_task_calls = update.max_task_calls
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
            max_request_tokens=update.max_request_tokens,
            max_daily_requests=update.max_daily_requests,
            max_task_calls=update.max_task_calls,
        )

    async def test_connection(
        self,
        update: AIProviderSettingsUpdate | None = None,
        *,
        verify_structured_output: bool = False,
    ) -> AIProviderConnectionResult:
        config = await self._config_for_update(update) if update else await self._effective_config()
        started = time.perf_counter()
        streaming = False
        structured_output_supported: bool | None = None
        if config.provider == "fake":
            health = await FakeAIProvider(model=config.model).check_health()
        else:
            provider = OpenAICompatibleProvider(
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
            )
            health = await provider.check_health()
            if health.status == ProviderHealth.AVAILABLE:
                # Probe only synthetic text; never send user files or logs to test connectivity.
                from app.services.ai_execution_service import AIExecutionService

                guarded = AIExecutionService(
                    provider, max_request_tokens=config.max_request_tokens, max_daily_requests=config.max_daily_requests
                )
                try:
                    text = ""
                    async for chunk in guarded.stream_complete(
                        AICompletionRequest(
                            prompt="Reply with OK. This is a synthetic connectivity probe.",
                            system_instruction="Reply with OK.",
                            prompt_id="provider_connection",
                            prompt_version="v1.0",
                            max_tokens=16,
                        )
                    ):
                        text += chunk.content_delta
                    streaming = bool(text.strip())
                    health.message = "Model returned a real streaming response to a synthetic probe."
                except Exception as error:
                    health.status = ProviderHealth.UNAVAILABLE
                    health.message = f"Model streaming probe failed ({type(error).__name__})."
            if verify_structured_output and config.provider != "fake" and health.status == ProviderHealth.AVAILABLE:
                try:
                    response = await guarded.complete(
                        AICompletionRequest(
                            prompt='Return exactly one JSON object with the property "json_mode" set to true.',
                            system_instruction="Return only the requested JSON object, with no prose or Markdown.",
                            prompt_id="provider_structured_output_probe",
                            prompt_version="v1.0",
                            max_tokens=32,
                            response_schema=_StructuredOutputProbe,
                        )
                    )
                    if response.structured_data is not None:
                        _StructuredOutputProbe.model_validate(response.structured_data)
                    else:
                        _StructuredOutputProbe.model_validate_json(clean_json_text(response.content))
                    structured_output_supported = True
                    health.message = "Model returned valid structured JSON to a synthetic completion probe."
                except Exception as error:
                    structured_output_supported = False
                    health.message = f"Model structured JSON probe failed ({type(error).__name__})."
        return AIProviderConnectionResult(
            connected=health.status in (ProviderHealth.AVAILABLE, ProviderHealth.FALLBACK_ONLY),
            provider=health.provider,
            status=health.status.value,
            message=health.message,
            model=health.model,
            streaming=streaming,
            structured_output_supported=structured_output_supported,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def get_status(self, refresh: bool = False) -> AIStatusResponse:
        """Shared health for Header, Settings and readiness; discovery alone is insufficient."""
        global _health_cache
        config = await self._effective_config()
        key = hashlib.sha256(repr(config).encode()).hexdigest()
        async with _health_lock:
            if not refresh and _health_cache and _health_cache[0] == key and time.monotonic() < _health_cache[1]:
                return _health_cache[2].model_copy()
            connection = await self.test_connection()
            real = connection.connected and connection.streaming and config.provider != "fake"
            simulated = config.provider == "fake"
            status = AIStatusResponse(
                provider=config.provider,
                model=config.model,
                base_url=config.base_url,
                status=AIProviderRuntimeState.REAL_CONNECTED
                if real
                else AIProviderRuntimeState.SIMULATION
                if simulated
                else AIProviderRuntimeState.UNAVAILABLE,
                message=connection.message,
                real_model_available=real,
                fallback_active=False,
                failure_reason=None if real else "fake_provider_selected" if simulated else "provider_probe_failed",
                health_status=AIProviderStatus.AVAILABLE
                if real
                else AIProviderStatus.DISABLED
                if simulated
                else AIProviderStatus.UNAVAILABLE,
                operational_state="REAL_AVAILABLE" if real else "SIMULATION" if simulated else "UNAVAILABLE",
                streaming=connection.streaming,
                latency_ms=connection.latency_ms,
                checked_at=connection.checked_at,
            )
            _health_cache = (key, time.monotonic() + 30, status)
            return status.model_copy()
