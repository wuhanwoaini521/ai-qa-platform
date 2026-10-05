"""Provider middleware shared by every registered model call, including task and SSE calls."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from qa_core.ai.budget import BudgetExceededError
from qa_core.ai.correlation import request_id_context
from qa_core.ai.models import AICompletionRequest, AICompletionResponse, AIStreamChunk
from qa_core.ai.provider import clean_json_text, stream_provider_completion
from qa_core.failure.redactor import SensitiveRedactor
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.persistence import database
from app.persistence.models import AIDailyBudgetORM, AIInvocationORM, utc_now
from app.repositories.ai_repo import AIRepository

logger = logging.getLogger("app.ai.runtime")


class AIExecutionService:
    records_usage = True

    def __init__(self, inner, *, max_request_tokens: int = 16000, max_daily_requests: int = 1000):
        self.inner = inner
        self.primary = getattr(inner, "primary", inner)
        self.fallbacks = getattr(inner, "fallbacks", [])
        self.provider_name = getattr(self.primary, "provider_name", "unknown")
        self.model = getattr(self.primary, "model", "")
        self.max_request_tokens = max_request_tokens
        self.max_daily_requests = max_daily_requests

    async def check_health(self):
        return await self.inner.check_health()

    @staticmethod
    async def reserve_daily_limit(max_daily_requests: int):
        async with database.get_session() as session:
            day = utc_now().date().isoformat()
            insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
            await session.execute(
                insert(AIDailyBudgetORM)
                .values(day=day, reserved_requests=0)
                .on_conflict_do_nothing(index_elements=["day"])
            )
            reserved = await session.execute(
                update(AIDailyBudgetORM)
                .where(
                    AIDailyBudgetORM.day == day,
                    AIDailyBudgetORM.reserved_requests < max_daily_requests,
                )
                .values(reserved_requests=AIDailyBudgetORM.reserved_requests + 1)
            )
            if reserved.rowcount != 1:
                raise BudgetExceededError("AI daily request hard limit reached.")
            await session.commit()

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
            if (
                len((request.prompt + request.system_instruction + schema).encode("utf-8")) + 2
            ) // 3 + request.max_tokens > self.max_request_tokens:
                raise BudgetExceededError("AI request size exceeds configured token budget.")
            if self.provider_name != "fake":
                await self.reserve_daily_limit(self.max_daily_requests)
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
        async with database.get_session() as session:
            row = await session.get(AIInvocationORM, invocation_id)
            if row is None:
                return
            row.status = status
            row.error_type = error_type
            row.duration_ms = (time.perf_counter() - started) * 1000
            if response:
                row.provider = response.provider
                row.model = response.model
                row.fallback_used = response.fallback_used or response.provider == "fake"
                row.input_tokens = response.input_tokens if response.provider != "fake" else None
                row.output_tokens = response.output_tokens if response.provider != "fake" else None
                row.token_source = (
                    "provider" if row.input_tokens is not None or row.output_tokens is not None else "unknown"
                )
                row.retry_count = response.retry_count
            await session.commit()
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
                raise ValueError("AI provider returned an empty response.")
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
            await self._finish(invocation_id, started, status="FAILED", error_type=type(error).__name__)
            raise

    async def stream_complete(self, request: AICompletionRequest) -> AsyncIterator[AIStreamChunk]:
        request, invocation_id, started = await self._begin(request)
        response = AICompletionResponse(content="", provider=self.provider_name, model=self.model)
        stream = stream_provider_completion(self.inner, request)
        try:
            async for chunk in stream:
                chunk = chunk.model_copy(update={"invocation_id": invocation_id})
                response.content += chunk.content_delta
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
                raise ValueError("AI provider returned an empty stream.")
            if request.response_schema:
                parsed = request.response_schema.model_validate_json(clean_json_text(response.content))
                response = response.model_copy(update={"structured_data": parsed.model_dump()})
            await self._finish(invocation_id, started, response=response)
        except (asyncio.CancelledError, GeneratorExit):
            await self._finish(invocation_id, started, response=response, status="CANCELLED")
            raise
        except Exception as error:
            await self._finish(
                invocation_id, started, response=response, status="FAILED", error_type=type(error).__name__
            )
            raise
        finally:
            await stream.aclose()
