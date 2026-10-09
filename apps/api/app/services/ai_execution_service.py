"""Provider middleware shared by every registered model call, including task and SSE calls."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from qa_core.ai.budget import BudgetExceededError
from qa_core.ai.correlation import request_id_context
from qa_core.ai.models import AICompletionRequest, AICompletionResponse, AIStreamChunk
from qa_core.ai.provider import (
    clean_json_text,
    empty_response_error,
    is_output_limit_finish_reason,
    output_limit_error,
    stream_provider_completion,
)
from qa_core.failure.redactor import SensitiveRedactor

from app.persistence.models import utc_now
from app.ports.repository_scope import RepositoryScopeFactory
from app.repositories.ai_repo import AIRepository

logger = logging.getLogger("app.ai.runtime")


class AIExecutionService:
    records_usage = True

    def __init__(
        self,
        inner,
        *,
        max_request_tokens: int = 1_000_000,
        max_daily_requests: int = 1000,
        budget_enabled: bool = True,
        repository_scope: RepositoryScopeFactory | None = None,
    ):
        self.inner = inner
        self.primary = getattr(inner, "primary", inner)
        self.fallbacks = getattr(inner, "fallbacks", [])
        self.provider_name = getattr(self.primary, "provider_name", "unknown")
        self.model = getattr(self.primary, "model", "")
        self.max_request_tokens = max_request_tokens
        self.max_daily_requests = max_daily_requests
        self.budget_enabled = budget_enabled
        self.repository_scope = repository_scope

    async def check_health(self):
        return await self.inner.check_health()

    @staticmethod
    async def reserve_daily_limit(max_daily_requests: int, repository_scope: RepositoryScopeFactory):
        async with repository_scope() as repositories:
            day = utc_now().date().isoformat()
            if not await repositories.ai_budgets.reserve(day, max_daily_requests):
                raise BudgetExceededError("AI daily request hard limit reached.")
            await repositories.commit()

    async def _begin(self, request: AICompletionRequest):
        request = request.model_copy(
            update={
                "prompt": SensitiveRedactor.redact_text(request.prompt),
                "system_instruction": SensitiveRedactor.redact_text(request.system_instruction),
                "request_id": request.request_id or request_id_context.get(),
            }
        )
        # This is a conservative preflight size bound, never recorded as measured token usage.
        import json

        schema = json.dumps(request.response_schema.model_json_schema()) if request.response_schema else ""
        try:
            estimated_input_tokens = (
                len((request.prompt + request.system_instruction + schema).encode("utf-8")) + 2
            ) // 3
            reserved_output_tokens = request.max_tokens or 0
            if self.budget_enabled and estimated_input_tokens + reserved_output_tokens > self.max_request_tokens:
                raise BudgetExceededError("AI request size exceeds configured token budget.")
            if self.budget_enabled and self.provider_name != "fake":
                if self.repository_scope is None:
                    raise RuntimeError("Real AI execution requires a repository scope")
                await self.reserve_daily_limit(self.max_daily_requests, self.repository_scope)
        except BudgetExceededError:
            await AIRepository().record_invocation(
                task=request.prompt_id or "unversioned",
                provider=self.provider_name,
                model=self.model,
                status="FAILED",
                error_type="BudgetExceededError",
                prompt_version=request.prompt_version,
                request_id=request.request_id,
                task_id=request.task_id,
                run_id=request.run_id,
            )
            raise
        record = await AIRepository().record_invocation(
            task=request.prompt_id or "unversioned",
            provider=self.provider_name,
            model=self.model,
            status="RUNNING",
            prompt_version=request.prompt_version,
            request_id=request.request_id,
            task_id=request.task_id,
            run_id=request.run_id,
        )
        return request, record.id, time.perf_counter()

    async def _finish(self, invocation_id: str, started: float, *, response=None, status="SUCCESS", error_type=None):
        row = await AIRepository().finish_invocation(
            invocation_id,
            status=status,
            error_type=error_type,
            duration_ms=(time.perf_counter() - started) * 1000,
            response=response,
        )
        if row is None:
            return
        logger.info(
            "AI invocation ai_run_id=%s request_id=%s task_id=%s run_id=%s feature=%s provider=%s status=%s error_type=%s",
            row.id,
            row.request_id,
            row.task_id,
            row.run_id,
            row.task,
            row.provider,
            row.status,
            row.error_type,
        )

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        request, invocation_id, started = await self._begin(request)
        try:
            response = await self.inner.complete(request)
            response = response.model_copy(update={"invocation_id": invocation_id})
            if not response.content.strip() and response.structured_data is None:
                raise empty_response_error(streamed=False)
            if request.response_schema:
                parsed = (
                    request.response_schema.model_validate(response.structured_data)
                    if response.structured_data is not None
                    else request.response_schema.model_validate_json(clean_json_text(response.content))
                )
                response = response.model_copy(update={"structured_data": parsed.model_dump()})
            await self._finish(invocation_id, started, response=response)
            return response
        except asyncio.CancelledError:
            await self._finish(invocation_id, started, status="CANCELLED")
            raise
        except Exception as error:
            await self._finish(
                invocation_id,
                started,
                status="FAILED",
                error_type=getattr(error, "code", None) or type(error).__name__,
            )
            raise

    async def stream_complete(self, request: AICompletionRequest) -> AsyncIterator[AIStreamChunk]:
        request, invocation_id, started = await self._begin(request)
        response = AICompletionResponse(content="", provider=self.provider_name, model=self.model)
        stream = stream_provider_completion(self.inner, request)
        finish_reason = None
        try:
            async for chunk in stream:
                chunk = chunk.model_copy(update={"invocation_id": invocation_id})
                response.content += chunk.content_delta
                finish_reason = chunk.finish_reason or finish_reason
                response.provider = chunk.provider
                response.model = chunk.model or response.model
                response.fallback_used = response.fallback_used or chunk.fallback_used
                if chunk.usage:
                    for source, target in (
                        ("prompt_tokens", "input_tokens"),
                        ("completion_tokens", "output_tokens"),
                        ("input_tokens", "input_tokens"),
                        ("output_tokens", "output_tokens"),
                    ):
                        value = chunk.usage.get(source)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            setattr(response, target, value)
                yield chunk
            if not response.content.strip():
                if is_output_limit_finish_reason(finish_reason) or (
                    request.max_tokens is not None
                    and response.output_tokens is not None
                    and response.output_tokens >= request.max_tokens
                ):
                    raise output_limit_error(
                        max_tokens=request.max_tokens,
                        output_tokens=response.output_tokens,
                    )
                raise empty_response_error(streamed=True)
            if request.response_schema:
                parsed = request.response_schema.model_validate_json(clean_json_text(response.content))
                response = response.model_copy(update={"structured_data": parsed.model_dump()})
            await self._finish(invocation_id, started, response=response)
        except (asyncio.CancelledError, GeneratorExit):
            await self._finish(invocation_id, started, response=response, status="CANCELLED")
            raise
        except Exception as error:
            await self._finish(
                invocation_id,
                started,
                response=response,
                status="FAILED",
                error_type=getattr(error, "code", None) or type(error).__name__,
            )
            raise
        finally:
            await stream.aclose()
