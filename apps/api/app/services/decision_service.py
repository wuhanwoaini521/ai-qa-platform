from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from urllib.parse import urlsplit
from uuid import uuid4

from project_model.models import (
    DecisionConnectionResult,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DecisionSignalRequest,
    JevRuntimeCheckResponse,
    JevSettingsUpdate,
)
from qa_core.ai.budget import BudgetExceededError
from qa_core.failure.redactor import SensitiveRedactor

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
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
            retries=config.retries,
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
        repository_scope: RepositoryScopeFactory | None = None,
    ) -> None:
        self.repository_scope = repository_scope
        self.settings_service = settings_service or DecisionSettingsService(repository_scope)
        self.provider_registry = provider_registry or default_provider_registry()
        self.ai_repo = ai_repo or AIRepository()

    def _fallback(
        self,
        request: DecisionRequest,
        reason: str,
        *,
        confidence: float | None = None,
        minimum_confidence: float | None = None,
        attempted_provider: str | None = None,
        attempted_model: str | None = None,
        attempted_choice: str | None = None,
        probabilities: dict[str, float] | None = None,
    ) -> DecisionResult:
        choice = next((option.key for option in request.options if option.key.lower() == "unknown"), None)
        return DecisionResult(
            choice=choice,
            confidence=confidence,
            probabilities=probabilities or {},
            provider="fallback",
            attempted_provider=attempted_provider,
            attempted_model=attempted_model,
            attempted_choice=attempted_choice,
            minimum_confidence=minimum_confidence,
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
        decision_value: float | None = None,
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
                decision_value=(
                    decision_value
                    if decision_value is not None
                    else (
                        result.probability
                        if result and result.probability is not None
                        else result.score
                        if result
                        else None
                    )
                ),
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
            result = self._fallback(
                request,
                "provider_disabled",
                minimum_confidence=config.minimum_confidence,
            )
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
        provider_attempted = False
        try:
            from app.services.ai_execution_service import AIExecutionService
            from app.services.ai_settings_service import AISettingsService

            policy = await AISettingsService(self.repository_scope)._effective_config()
            request = request.model_copy(update={"state": SensitiveRedactor.redact_value(request.state)})
            if policy.budget_enabled and (
                len(json.dumps(request.model_dump(), ensure_ascii=False).encode("utf-8")) // 3 + 100
                > policy.max_request_tokens
            ):
                raise BudgetExceededError("Decision request exceeds configured token budget.")
            if reserve_task_call is not None and not await reserve_task_call():
                error_code = "task_ai_budget_exhausted"
            else:
                if policy.budget_enabled and self.repository_scope is not None:
                    await AIExecutionService.reserve_daily_limit(policy.max_daily_requests, self.repository_scope)
                provider = self.provider_registry.create(config.provider, config)
                provider_attempted = True
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
                accepted_result = remote_result.model_copy(update={"minimum_confidence": config.minimum_confidence})
                duration = (time.perf_counter() - started) * 1000
                await self._record(
                    decision_name=request.name,
                    provider=accepted_result.provider,
                    model=accepted_result.model,
                    duration_ms=duration,
                    result=accepted_result,
                    status="SUCCESS",
                    usage=accepted_result.usage,
                    task_id=task_id,
                    run_id=run_id,
                )
                logger.info(
                    "Decision completed run_id=%s name=%s provider=%s model=%s timeout_seconds=%s minimum_confidence=%s latency_ms=%.1f confidence=%s",
                    run_id,
                    request.name,
                    accepted_result.provider,
                    accepted_result.model,
                    config.timeout,
                    config.minimum_confidence,
                    duration,
                    accepted_result.confidence,
                )
                log_ai_execution(
                    logger,
                    run_id=run_id,
                    feature=request.name,
                    provider=accepted_result.provider,
                    model=accepted_result.model or "",
                    duration_ms=duration,
                    status="SUCCESS",
                    fallback_used=accepted_result.fallback_used,
                )
                return accepted_result
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
        result = self._fallback(
            request,
            error_code or "unknown_error",
            confidence=remote_result.confidence if remote_result else None,
            minimum_confidence=config.minimum_confidence,
            attempted_provider=config.provider if provider_attempted else None,
            attempted_model=(remote_result.model if remote_result else config.model) if provider_attempted else None,
            attempted_choice=remote_result.choice if remote_result else None,
            probabilities=remote_result.probabilities if remote_result else None,
        )
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

    async def ask_probability(
        self,
        request: DecisionSignalRequest,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        reserve_task_call=None,
        daily_request_reserve: int = 0,
    ) -> DecisionResult:
        return await self._ask_signal(
            request,
            signal_type="noul",
            run_id=run_id,
            task_id=task_id,
            reserve_task_call=reserve_task_call,
            daily_request_reserve=daily_request_reserve,
        )

    async def ask_score(
        self,
        request: DecisionSignalRequest,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        reserve_task_call=None,
        daily_request_reserve: int = 0,
    ) -> DecisionResult:
        return await self._ask_signal(
            request,
            signal_type="score",
            run_id=run_id,
            task_id=task_id,
            reserve_task_call=reserve_task_call,
            daily_request_reserve=daily_request_reserve,
        )

    async def _ask_signal(
        self,
        request: DecisionSignalRequest,
        *,
        signal_type: str,
        run_id: str | None,
        task_id: str | None,
        reserve_task_call,
        daily_request_reserve: int,
    ) -> DecisionResult:
        run_id = run_id or uuid4().hex
        config = await self.settings_service.get_runtime_config()
        started = time.perf_counter()
        decision_name = request.name
        if not config.enabled:
            result = DecisionResult(
                provider="fallback",
                minimum_confidence=config.minimum_confidence,
                fallback_used=True,
                reason="provider_disabled",
            )
            await self._record(
                decision_name=decision_name,
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
                feature=decision_name,
                provider="fallback",
                model="",
                duration_ms=0,
                status="FALLBACK",
                fallback_used=True,
            )
            return result

        error_code: str | None = None
        remote_result: DecisionResult | None = None
        provider_attempted = False
        try:
            from app.services.ai_execution_service import AIExecutionService
            from app.services.ai_settings_service import AISettingsService

            policy = await AISettingsService(self.repository_scope)._effective_config()
            request = request.model_copy(update={"state": SensitiveRedactor.redact_value(request.state)})
            if policy.budget_enabled and (
                len(json.dumps(request.model_dump(), ensure_ascii=False).encode("utf-8")) // 3 + 100
                > policy.max_request_tokens
            ):
                raise BudgetExceededError("Decision signal exceeds configured token budget.")
            if reserve_task_call is not None and not await reserve_task_call():
                error_code = "task_ai_budget_exhausted"
            else:
                if policy.budget_enabled and self.repository_scope is not None:
                    daily_limit = max(0, policy.max_daily_requests - max(0, daily_request_reserve))
                    await AIExecutionService.reserve_daily_limit(daily_limit, self.repository_scope)
                provider = self.provider_registry.create(config.provider, config)
                method = getattr(provider, f"ask_{'probability' if signal_type == 'noul' else 'score'}", None)
                if method is None:
                    raise DecisionProviderError("invalid_request")
                provider_attempted = True
                remote_result = await asyncio.wait_for(method(request), timeout=config.timeout + 1)
            if error_code is None and remote_result is not None:
                value = remote_result.probability if signal_type == "noul" else remote_result.score
                if remote_result.provider != config.provider or remote_result.fallback_used:
                    error_code = "unexpected_provider"
                elif value is None:
                    error_code = "signal_missing"
                elif (
                    not isinstance(remote_result.confidence, (int, float))
                    or isinstance(remote_result.confidence, bool)
                    or not math.isfinite(remote_result.confidence)
                    or not 0 <= remote_result.confidence <= 1
                ):
                    error_code = "confidence_missing"
                elif remote_result.confidence < config.minimum_confidence:
                    error_code = "below_minimum_confidence"
                else:
                    accepted = remote_result.model_copy(update={"minimum_confidence": config.minimum_confidence})
                    duration = (time.perf_counter() - started) * 1000
                    await self._record(
                        decision_name=decision_name,
                        provider=accepted.provider,
                        model=accepted.model,
                        duration_ms=duration,
                        result=accepted,
                        status="SUCCESS",
                        usage=accepted.usage,
                        task_id=task_id,
                        run_id=run_id,
                    )
                    log_ai_execution(
                        logger,
                        run_id=run_id,
                        feature=decision_name,
                        provider=accepted.provider,
                        model=accepted.model or "",
                        duration_ms=duration,
                        status="SUCCESS",
                        fallback_used=False,
                    )
                    return accepted
        except asyncio.TimeoutError:
            error_code = "timeout"
        except DecisionProviderError as error:
            error_code = error.code
        except BudgetExceededError:
            error_code = "budget_exceeded"
        except Exception as error:
            error_code = "unknown_error"
            logger.warning(
                "Decision signal failed name=%s signal_type=%s error_type=%s",
                decision_name,
                signal_type,
                type(error).__name__,
            )

        duration = (time.perf_counter() - started) * 1000
        attempted_confidence = remote_result.confidence if remote_result else None
        if (
            not isinstance(attempted_confidence, (int, float))
            or isinstance(attempted_confidence, bool)
            or not math.isfinite(attempted_confidence)
            or not 0 <= attempted_confidence <= 1
        ):
            attempted_confidence = None
        result = DecisionResult(
            provider="fallback",
            attempted_provider=config.provider if provider_attempted else None,
            attempted_model=(remote_result.model if remote_result else config.model) if provider_attempted else None,
            confidence=attempted_confidence,
            minimum_confidence=config.minimum_confidence,
            usage=remote_result.usage if remote_result else None,
            fallback_used=True,
            reason=error_code or "unknown_error",
        )
        attempted_value = (
            (remote_result.probability if signal_type == "noul" else remote_result.score) if remote_result else None
        )
        await self._record(
            decision_name=decision_name,
            provider=config.provider,
            model=config.model,
            duration_ms=duration,
            result=result,
            status="FALLBACK",
            error_type=error_code,
            usage=remote_result.usage if remote_result else None,
            task_id=task_id,
            run_id=run_id,
            decision_value=attempted_value,
        )
        log_ai_execution(
            logger,
            run_id=run_id,
            feature=decision_name,
            provider=config.provider,
            model=config.model,
            duration_ms=duration,
            status="FALLBACK",
            fallback_used=True,
        )
        return result

    async def test_connection(self, update: JevSettingsUpdate | None = None) -> DecisionConnectionResult:
        config = await self.settings_service.config_for_test(update)
        if not config.enabled:
            return DecisionConnectionResult(
                connected=False,
                code="provider_disabled",
                message="Jev is disabled by the effective AppConfig.",
                model=config.model,
                latency_ms=0,
            )
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

            policy = await AISettingsService(self.repository_scope)._effective_config()
            if policy.budget_enabled and self.repository_scope is not None:
                await AIExecutionService.reserve_daily_limit(policy.max_daily_requests, self.repository_scope)
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
        except BudgetExceededError:
            code = "budget_exceeded"
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

    async def runtime_check(self) -> JevRuntimeCheckResponse:
        config = await self.settings_service.get_runtime_config()
        from app.services.ai_settings_service import AISettingsService

        policy = await AISettingsService(self.repository_scope)._effective_config()
        if self.repository_scope is None:
            budget = None
        else:
            async with self.repository_scope() as repositories:
                budget = await repositories.ai_budgets.get_by_day(utc_now().date().isoformat())
        budget_available = (
            not policy.budget_enabled or budget is None or budget.reserved_requests < policy.max_daily_requests
        )
        parsed = urlsplit(config.base_url)
        base_url_valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
        reasons = []
        if not config.enabled:
            reasons.append("provider_disabled")
        if not config.api_key:
            reasons.append("missing_api_key")
        if config.provider != "jev":
            reasons.append("unsupported_provider")
        if not config.model.strip():
            reasons.append("missing_model")
        if not base_url_valid:
            reasons.append("invalid_base_url")
        if not 0 <= config.minimum_confidence <= 1:
            reasons.append("invalid_minimum_confidence")
        if not 0 < config.timeout <= 120:
            reasons.append("invalid_timeout")
        if not budget_available:
            reasons.append("budget_exceeded")
        if reasons:
            return JevRuntimeCheckResponse(
                connectivity="NOT_CHECKED",
                runtime="DISABLED" if not config.enabled else "BLOCKED",
                enabled=config.enabled,
                api_key_configured=bool(config.api_key),
                provider=config.provider,
                model=config.model,
                base_url_valid=base_url_valid,
                minimum_confidence=config.minimum_confidence,
                budget_available=budget_available,
                reasons=reasons,
            )

        started = time.perf_counter()
        result = await self.choose(
            DecisionRequest(
                name="jev_runtime_check",
                state={"purpose": "runtime readiness check"},
                instructions="Choose the only available option to verify a usable runtime decision.",
                options=[DecisionOption(key="ok", description="Runtime decision is available.")],
            )
        )
        latency = round((time.perf_counter() - started) * 1000, 1)
        response_received = result.reason in {"below_minimum_confidence", "confidence_missing"}
        connected = result.provider == config.provider or response_received
        not_checked = result.reason in {"budget_exceeded", "task_ai_budget_exhausted"}
        ready = connected and not result.fallback_used and result.choice == "ok"
        reason = result.reason
        if connected and not ready and reason is None:
            reason = "unexpected_probe_decision"
        return JevRuntimeCheckResponse(
            connectivity="CONNECTED" if connected else "NOT_CHECKED" if not_checked else "FAILED",
            runtime="READY" if ready else "BLOCKED",
            enabled=config.enabled,
            api_key_configured=bool(config.api_key),
            provider=config.provider,
            model=config.model,
            base_url_valid=base_url_valid,
            minimum_confidence=config.minimum_confidence,
            budget_available=budget_available,
            latency_ms=latency,
            reasons=[] if ready else [reason or "decision_unavailable"],
        )


def _token_count(usage: dict[str, int | float | None] | None, field: str) -> int | None:
    value = usage.get(field) if usage else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
