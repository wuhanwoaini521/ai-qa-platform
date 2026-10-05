from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

from project_model.models import (
    DecisionConnectionResult,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    JevSettingsUpdate,
)
from qa_core.ai.budget import BudgetExceededError
from qa_core.failure.redactor import SensitiveRedactor

from app.repositories.ai_repo import AIRepository
from app.services.ai_observability import log_ai_execution
from app.services.decision_provider import DecisionProviderRegistry
from app.services.decision_settings_service import DecisionSettingsService
from app.services.jev_provider import DecisionProviderError, JevDecisionProvider

logger = logging.getLogger("app.decision")

CONNECTION_ERRORS = {
    "missing_api_key": ("missing_api_key", "请先配置 Jev API Key。"),
    "invalid_api_key": ("invalid_api_key", "Jev API Key 无效或无权访问。"),
    "timeout": ("timeout", "连接 Jev 超时，请检查超时设置或网络。"),
    "network_error": ("network_error", "无法连接 Jev 服务，请检查网络和 API 地址。"),
    "invalid_response": ("invalid_response", "Jev 返回的数据格式不符合预期。"),
    "unsupported_model": ("unsupported_model", "Jev 不支持所配置的模型或 API 地址。"),
    "rate_limited": ("rate_limited", "Jev 请求频率受限，请稍后重试。"),
    "invalid_request": ("invalid_response", "Jev 拒绝了连接测试请求，请检查模型和 API 地址。"),
    "upstream_error": ("unknown_error", "Jev 服务暂时不可用。"),
}


def default_provider_registry() -> DecisionProviderRegistry:
    registry = DecisionProviderRegistry()
    registry.register(
        "jev",
        lambda config: JevDecisionProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout,
        ),
    )
    return registry


class DecisionService:
    """Provider-neutral decision API, with confidence policy and safe abstention fallback."""

    def __init__(
        self,
        settings_service: DecisionSettingsService | None = None,
        provider_registry: DecisionProviderRegistry | None = None,
        ai_repo: AIRepository | None = None,
    ) -> None:
        self.settings_service = settings_service or DecisionSettingsService()
        self.provider_registry = provider_registry or default_provider_registry()
        self.ai_repo = ai_repo or AIRepository()

    def _fallback(self, request: DecisionRequest, reason: str) -> DecisionResult:
        choice = next((option.key for option in request.options if option.key.lower() == "unknown"), None)
        return DecisionResult(
            choice=choice,
            confidence=None,
            probabilities={},
            provider="fallback",
            fallback_used=True,
            reason=reason,
        )

    async def _record(
        self,
        *,
        decision_name: str,
        provider: str,
        model: str | None,
        duration_ms: float,
        result: DecisionResult | None,
        status: str,
        error_type: str | None = None,
        usage: dict[str, int | float | None] | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        try:
            await self.ai_repo.record_invocation(
                task=decision_name,
                decision_name=decision_name,
                provider=provider,
                model=model or "",
                duration_ms=duration_ms,
                input_tokens=_token_count(usage, "input_tokens"),
                output_tokens=_token_count(usage, "output_tokens"),
                fallback_used=bool(result and result.fallback_used),
                status=status,
                error_type=error_type,
                decision_choice=result.choice if result else None,
                decision_confidence=result.confidence if result else None,
                task_id=task_id,
                run_id=run_id,
            )
        except Exception as error:  # telemetry must never turn a safe decision into a failed test run
            logger.warning("Decision telemetry write failed (%s)", type(error).__name__)

    async def choose(
        self,
        request: DecisionRequest,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        reserve_task_call=None,
        allow_missing_confidence: bool = False,
    ) -> DecisionResult:
        run_id = run_id or uuid4().hex
        if len({option.key for option in request.options}) != len(request.options):
            raise ValueError("Decision option keys must be unique")

        config = await self.settings_service.get_runtime_config()
        started = time.perf_counter()
        if not config.enabled:
            result = self._fallback(request, "provider_disabled")
            await self._record(
                decision_name=request.name,
                provider="fallback",
                model=None,
                duration_ms=0,
                result=result,
                status="FALLBACK",
                error_type="provider_disabled",
                task_id=task_id,
                run_id=run_id,
            )
            log_ai_execution(
                logger,
                run_id=run_id,
                feature=request.name,
                provider="fallback",
                model="",
                duration_ms=0,
                status="FALLBACK",
                fallback_used=True,
            )
            return result

        error_code: str | None = None
        remote_result: DecisionResult | None = None
        try:
            from app.services.ai_execution_service import AIExecutionService
            from app.services.ai_settings_service import AISettingsService

            policy = await AISettingsService()._effective_config()
            request = request.model_copy(update={"state": SensitiveRedactor.redact_value(request.state)})
            if (
                len(json.dumps(request.model_dump(), ensure_ascii=False).encode("utf-8")) // 3 + 100
                > policy.max_request_tokens
            ):
                raise BudgetExceededError("Decision request exceeds configured token budget.")
            if reserve_task_call is not None and not await reserve_task_call():
                error_code = "task_ai_budget_exhausted"
            else:
                await AIExecutionService.reserve_daily_limit(policy.max_daily_requests)
                provider = self.provider_registry.create(config.provider, config)
                remote_result = await asyncio.wait_for(provider.choose(request), timeout=config.timeout + 1)
            if error_code == "task_ai_budget_exhausted":
                pass
            elif remote_result.confidence is None and not allow_missing_confidence:
                error_code = "confidence_missing"
            elif (
                remote_result is not None
                and remote_result.confidence is not None
                and remote_result.confidence < config.minimum_confidence
            ):
                error_code = "below_minimum_confidence"
            elif remote_result is not None:
                duration = (time.perf_counter() - started) * 1000
                await self._record(
                    decision_name=request.name,
                    provider=remote_result.provider,
                    model=remote_result.model,
                    duration_ms=duration,
                    result=remote_result,
                    status="SUCCESS",
                    usage=remote_result.usage,
                    task_id=task_id,
                    run_id=run_id,
                )
                logger.info(
                    "Decision completed run_id=%s name=%s provider=%s model=%s latency_ms=%.1f confidence=%s",
                    run_id,
                    request.name,
                    remote_result.provider,
                    remote_result.model,
                    duration,
                    remote_result.confidence,
                )
                log_ai_execution(
                    logger,
                    run_id=run_id,
                    feature=request.name,
                    provider=remote_result.provider,
                    model=remote_result.model or "",
                    duration_ms=duration,
                    status="SUCCESS",
                    fallback_used=remote_result.fallback_used,
                )
                return remote_result
        except asyncio.TimeoutError:
            error_code = "timeout"
        except DecisionProviderError as error:
            error_code = error.code
        except BudgetExceededError:
            error_code = "budget_exceeded"
        except Exception as error:
            error_code = "unknown_error"
            logger.warning("Decision provider failed name=%s error_type=%s", request.name, type(error).__name__)

        duration = (time.perf_counter() - started) * 1000
        result = self._fallback(request, error_code or "unknown_error")
        await self._record(
            decision_name=request.name,
            provider=config.provider,
            model=config.model,
            duration_ms=duration,
            result=result,
            status="FALLBACK",
            error_type=error_code,
            usage=remote_result.usage if remote_result else None,
            task_id=task_id,
            run_id=run_id,
        )
        logger.info(
            "Decision fallback run_id=%s name=%s provider=%s latency_ms=%.1f reason=%s",
            run_id,
            request.name,
            config.provider,
            duration,
            error_code,
        )
        log_ai_execution(
            logger,
            run_id=run_id,
            feature=request.name,
            provider=config.provider,
            model=config.model,
            duration_ms=duration,
            status="FALLBACK",
            fallback_used=True,
        )
        return result

    async def test_connection(self, update: JevSettingsUpdate) -> DecisionConnectionResult:
        config = await self.settings_service.config_for_test(update)
        request = DecisionRequest(
            name="connection_test",
            state="This is a connection test. Choose the option 'ok'.",
            instructions="This is only a connectivity probe. Choose 'ok'.",
            options=[
                DecisionOption(key="ok", description="The Jev API connection is working."),
                DecisionOption(key="failed", description="The Jev API connection is not working."),
            ],
        )
        started = time.perf_counter()
        try:
            from app.services.ai_execution_service import AIExecutionService
            from app.services.ai_settings_service import AISettingsService

            policy = await AISettingsService()._effective_config()
            await AIExecutionService.reserve_daily_limit(policy.max_daily_requests)
            provider = self.provider_registry.create(config.provider, config)
            result = await asyncio.wait_for(provider.choose(request), timeout=config.timeout + 1)
            latency = (time.perf_counter() - started) * 1000
            await self._record(
                decision_name="connection_test",
                provider=result.provider,
                model=result.model,
                duration_ms=latency,
                result=result,
                status="SUCCESS",
                usage=result.usage,
            )
            return DecisionConnectionResult(
                connected=True,
                code="connected",
                message="已收到格式有效的 Jev 决策响应。",
                choice=result.choice,
                model=result.model,
                latency_ms=round(latency, 1),
            )
        except asyncio.TimeoutError:
            code = "timeout"
        except DecisionProviderError as error:
            code = error.code
        except Exception as error:
            code = "unknown_error"
            logger.warning("Jev connection test failed error_type=%s", type(error).__name__)

        latency = (time.perf_counter() - started) * 1000
        safe_code, message = CONNECTION_ERRORS.get(code, CONNECTION_ERRORS["upstream_error"])
        await self._record(
            decision_name="connection_test",
            provider=config.provider,
            model=config.model,
            duration_ms=latency,
            result=None,
            status="FAILED",
            error_type=safe_code,
        )
        return DecisionConnectionResult(
            connected=False,
            code=safe_code,
            message=message,
            model=config.model,
            latency_ms=round(latency, 1),
        )


def _token_count(usage: dict[str, int | float | None] | None, field: str) -> int | None:
    value = usage.get(field) if usage else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
