from __future__ import annotations

import asyncio
import hashlib
import logging
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

from app.ports.repository_scope import RepositoryScopeFactory
from app.services.secret_store import SecretStore
from app.settings import get_config

_health_lock = asyncio.Lock()
_health_cache: tuple[str, float, AIStatusResponse] | None = None
logger = logging.getLogger("app.ai.config")


class _StructuredOutputProbe(BaseModel):
    json_mode: Literal[True]


@dataclass(frozen=True)
class AIRuntimeConfig:
    enabled: bool
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout: float
    max_retries: int
    max_request_tokens: int = 1_000_000
    max_daily_requests: int = 1000
    max_task_calls: int = 8
    max_requests_per_run: int = 50
    max_input_tokens_per_run: int = 100_000
    max_output_tokens_per_run: int = 50_000
    budget_enabled: bool = True


class AISettingsService:
    """Persists the normal AI provider separately from Jev and activates it for API requests."""

    def __init__(
        self, repository_scope: RepositoryScopeFactory | None = None, secret_store: SecretStore | None = None
    ) -> None:
        self.repository_scope = repository_scope
        self.secret_store = secret_store or SecretStore(master_key=get_config().app.secret_key.get_secret_value())

    def _environment_config(self) -> AIRuntimeConfig:
        config = get_config().ai
        budget = config.budget
        return AIRuntimeConfig(
            enabled=config.enabled,
            provider=config.provider,
            api_key=config.api_key.get_secret_value(),
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.retries,
            max_request_tokens=budget.max_request_tokens,
            max_daily_requests=budget.max_daily_requests,
            max_task_calls=budget.max_task_calls,
            max_requests_per_run=budget.max_requests_per_run,
            max_input_tokens_per_run=budget.max_input_tokens_per_run,
            max_output_tokens_per_run=budget.max_output_tokens_per_run,
            budget_enabled=budget.enabled,
        )

    async def _effective_config(self) -> AIRuntimeConfig:
        return self._environment_config()

    @staticmethod
    def _response(config: AIRuntimeConfig) -> AIProviderSettingsResponse:
        masked = SecretStore.mask_secret(config.api_key)
        return AIProviderSettingsResponse(
            enabled=config.enabled,
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

    def _activate(self, config: AIRuntimeConfig) -> None:
        from app.services.ai_execution_service import AIExecutionService

        AIProviderRegistry.configure_runtime(
            {
                "enabled": str(config.enabled).lower(),
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
                budget_enabled=config.budget_enabled,
                repository_scope=self.repository_scope,
            )
        )
        logger.info(
            "AI runtime activated enabled=%s provider=%s model=%s timeout_seconds=%s max_request_tokens=%s",
            config.enabled,
            config.provider,
            config.model,
            config.timeout,
            config.max_request_tokens,
        )

    async def get_settings(self) -> AIProviderSettingsResponse:
        config = await self._effective_config()
        self._activate(config)
        return self._response(config)

    async def load_runtime_config(self) -> None:
        """Activate the one validated AppConfig snapshot for every AI consumer."""
        self._activate(await self._effective_config())

    async def save(self, update: AIProviderSettingsUpdate) -> AIProviderSettingsResponse:
        raise RuntimeError("AI runtime settings are managed by config/config.yaml; edit it and call reload")

    async def _config_for_update(self, update: AIProviderSettingsUpdate) -> AIRuntimeConfig:
        current = await self._effective_config()
        api_key = (
            ""
            if update.clear_api_key
            else (update.api_key.strip() if update.api_key and update.api_key.strip() else current.api_key)
        )
        return AIRuntimeConfig(
            enabled=current.enabled,
            provider=update.provider,
            api_key=api_key,
            model=update.model.strip(),
            base_url=update.base_url.strip().rstrip("/"),
            timeout=update.timeout,
            max_retries=update.max_retries,
            max_request_tokens=update.max_request_tokens,
            max_daily_requests=update.max_daily_requests,
            max_task_calls=update.max_task_calls,
            max_requests_per_run=current.max_requests_per_run,
            max_input_tokens_per_run=current.max_input_tokens_per_run,
            max_output_tokens_per_run=current.max_output_tokens_per_run,
            budget_enabled=current.budget_enabled,
        )

    async def test_connection(
        self,
        update: AIProviderSettingsUpdate | None = None,
        *,
        verify_structured_output: bool = False,
    ) -> AIProviderConnectionResult:
        config = await self._config_for_update(update) if update else await self._effective_config()
        if not config.enabled:
            return AIProviderConnectionResult(
                connected=False,
                provider=config.provider,
                status=ProviderHealth.UNAVAILABLE.value,
                message="AI is disabled by the effective AppConfig.",
                model=config.model,
                streaming=False,
                structured_output_supported=None,
                latency_ms=0,
            )
        started = time.perf_counter()
        streaming = False
        structured_output_supported: bool | None = None
        if config.provider == "fake":
            health = await FakeAIProvider(model=config.model).check_health()
        else:
            # DeepSeek V4 enables thinking by default. Keep the tiny health probes
            # focused on final text so their token budget is not consumed by reasoning.
            probe_thinking_mode = "disabled" if config.model.casefold().startswith("deepseek-") else None
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
                    provider,
                    max_request_tokens=config.max_request_tokens,
                    max_daily_requests=config.max_daily_requests,
                    budget_enabled=config.budget_enabled,
                    repository_scope=self.repository_scope,
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
                            thinking_mode=probe_thinking_mode,
                        )
                    ):
                        text += chunk.content_delta
                    streaming = bool(text.strip())
                    health.message = "Model returned a real streaming response to a synthetic probe."
                except Exception as error:
                    health.status = ProviderHealth.UNAVAILABLE
                    code = getattr(error, "code", None) or type(error).__name__
                    safe_message = getattr(error, "safe_message", None)
                    detail = f": {safe_message}" if isinstance(safe_message, str) else ""
                    health.message = f"Model streaming probe failed ({code}){detail}."
            if verify_structured_output and config.provider != "fake" and health.status == ProviderHealth.AVAILABLE:
                try:
                    response = await guarded.complete(
                        AICompletionRequest(
                            prompt='Return exactly one JSON object with the property "json_mode" set to true.',
                            system_instruction="Return only the requested JSON object, with no prose or Markdown.",
                            prompt_id="provider_structured_output_probe",
                            prompt_version="v1.0",
                            max_tokens=32,
                            thinking_mode=probe_thinking_mode,
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
                    code = getattr(error, "code", None) or type(error).__name__
                    safe_message = getattr(error, "safe_message", None)
                    detail = f": {safe_message}" if isinstance(safe_message, str) else ""
                    health.message = f"Model structured JSON probe failed ({code}){detail}."
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
