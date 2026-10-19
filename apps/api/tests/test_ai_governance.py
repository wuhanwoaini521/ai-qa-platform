from __future__ import annotations

import asyncio

import pytest
from app.persistence.models import AIInvocationORM
from app.repositories.ai_repo import AIRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_execution_service import AIExecutionService
from app.services.task_ai_service import TaskAIService
from qa_core.ai.budget import BudgetExceededError
from qa_core.ai.models import AICompletionRequest, AICompletionResponse, AIStreamChunk, CodeAssistantResponse
from qa_core.ai.provider import AIProviderError
from sqlalchemy import select


class Provider:
    provider_name = "test-real"
    model = "reported-model"

    async def complete(self, request):
        return AICompletionResponse(
            content="answer", provider=self.provider_name, model=self.model, input_tokens=7, output_tokens=3
        )


def test_deepseek_browser_planning_disables_reasoning_token_mode():
    assert TaskAIService._provider_thinking_mode(Provider()) is None
    assert TaskAIService._provider_thinking_mode(type("DeepSeek", (), {"model": "deepseek-flash"})()) == "disabled"


@pytest.mark.asyncio
async def test_shared_usage_records_reported_tokens_and_prompt_version(test_db_session):
    service = AIExecutionService(Provider(), repository_scope=TaskRepositoryScopeFactory())
    response = await service.complete(
        AICompletionRequest(
            prompt="probe",
            prompt_id="probe",
            prompt_version="v2",
            task_id="task-synthetic",
            run_id="run-synthetic",
            request_id="request-synthetic",
        )
    )
    summary = await AIRepository().get_usage_summary()
    assert summary.total_requests == summary.successful_requests == 1
    assert (summary.total_input_tokens, summary.total_output_tokens) == (7, 3)
    assert summary.invocations[0].prompt_version == "v2"
    assert summary.invocations[0].token_source == "provider"
    assert summary.invocations[0].id == response.invocation_id
    assert summary.invocations[0].task_id == "task-synthetic"
    assert summary.invocations[0].run_id == "run-synthetic"
    assert summary.invocations[0].request_id == "request-synthetic"


@pytest.mark.asyncio
async def test_a_dead_process_leaves_no_running_invocation_behind(test_db_session):
    repo = AIRepository()
    record = await repo.record_invocation(
        task="failure_diagnosis", provider="test-real", model="reported-model", status="RUNNING"
    )

    recovered = await repo.recover_interrupted_invocations()

    assert recovered >= 1
    summary = await repo.get_usage_summary()
    row = next(item for item in summary.invocations if item.id == record.id)
    # A crashed call must not read as permanently running in the usage view.
    assert row.status == "INTERRUPTED"
    assert row.error_type == "process_interrupted"


@pytest.mark.asyncio
async def test_daily_hard_limit_is_atomic_across_concurrent_calls(test_db_session):
    provider = Provider()
    service = AIExecutionService(provider, max_daily_requests=2, repository_scope=TaskRepositoryScopeFactory())
    results = await asyncio.gather(
        *(service.complete(AICompletionRequest(prompt="probe")) for _ in range(5)), return_exceptions=True
    )
    assert sum(isinstance(result, AICompletionResponse) for result in results) == 2
    assert sum(isinstance(result, BudgetExceededError) for result in results) == 3


@pytest.mark.asyncio
async def test_schema_invalid_completion_is_failed_not_successful(test_db_session):
    with pytest.raises(ValueError):
        await AIExecutionService(Provider(), repository_scope=TaskRepositoryScopeFactory()).complete(
            AICompletionRequest(prompt="probe", response_schema=CodeAssistantResponse)
        )
    summary = await AIRepository().get_usage_summary()
    assert summary.failed_requests == 1
    assert summary.successful_requests == 0


@pytest.mark.asyncio
async def test_stream_unknown_tokens_and_fallback_are_explicit(test_db_session):
    class Streaming(Provider):
        async def stream_complete(self, _):
            yield AIStreamChunk(content_delta="offline", provider="fake", model="fake-model", fallback_used=True)

    chunks = [
        chunk
        async for chunk in AIExecutionService(
            Streaming(), repository_scope=TaskRepositoryScopeFactory()
        ).stream_complete(AICompletionRequest(prompt="probe"))
    ]
    assert chunks[0].fallback_used
    summary = await AIRepository().get_usage_summary()
    assert summary.fallback_requests == summary.unknown_token_requests == 1
    assert summary.total_input_tokens == summary.total_output_tokens == 0
    assert summary.invocations[0].input_tokens is None


@pytest.mark.asyncio
async def test_cancelling_stream_persists_cancelled_and_closes_iterator(test_db_session):
    closed = asyncio.Event()

    class Streaming(Provider):
        async def stream_complete(self, _):
            try:
                yield AIStreamChunk(content_delta="partial", provider=self.provider_name, model=self.model)
                await asyncio.Event().wait()
            finally:
                closed.set()

    stream = AIExecutionService(Streaming(), repository_scope=TaskRepositoryScopeFactory()).stream_complete(
        AICompletionRequest(prompt="probe")
    )
    await anext(stream)
    await stream.aclose()
    assert closed.is_set()
    async with test_db_session() as session:
        row = (await session.execute(select(AIInvocationORM))).scalar_one()
        assert row.status == "CANCELLED"


@pytest.mark.asyncio
async def test_empty_stream_is_failed(test_db_session):
    class Empty(Provider):
        async def stream_complete(self, _):
            yield AIStreamChunk(content_delta="", provider=self.provider_name, model=self.model)

    with pytest.raises(AIProviderError) as caught:
        _ = [
            chunk
            async for chunk in AIExecutionService(
                Empty(), repository_scope=TaskRepositoryScopeFactory()
            ).stream_complete(AICompletionRequest(prompt="probe"))
        ]
    assert caught.value.code == "empty_stream"
    summary = await AIRepository().get_usage_summary()
    assert summary.failed_requests == 1
    assert summary.invocations[0].error_type == "empty_stream"


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["length", "stop"])
async def test_nonempty_truncated_stream_is_classified_as_output_limit(test_db_session, finish_reason):
    class Truncated(Provider):
        async def stream_complete(self, _):
            yield AIStreamChunk(content_delta='{"reply":', provider=self.provider_name, model=self.model)
            yield AIStreamChunk(
                usage={"completion_tokens": 6000},
                finish_reason=finish_reason,
                provider=self.provider_name,
                model=self.model,
            )

    with pytest.raises(AIProviderError) as caught:
        _ = [
            chunk
            async for chunk in AIExecutionService(
                Truncated(), repository_scope=TaskRepositoryScopeFactory()
            ).stream_complete(
                AICompletionRequest(prompt="probe", max_tokens=6000, response_schema=CodeAssistantResponse)
            )
        ]

    assert caught.value.code == "output_limit"
    assert caught.value.input_tokens is None
    assert caught.value.output_tokens == 6000
    summary = await AIRepository().get_usage_summary()
    assert summary.failed_requests == 1
    assert summary.total_output_tokens == 6000
    assert summary.invocations[0].error_type == "output_limit"


@pytest.mark.asyncio
async def test_output_limit_is_classified_in_invocation_record(test_db_session):
    class Truncated(Provider):
        async def stream_complete(self, _):
            yield AIStreamChunk(
                usage={"completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    with pytest.raises(AIProviderError) as caught:
        _ = [
            chunk
            async for chunk in AIExecutionService(
                Truncated(), repository_scope=TaskRepositoryScopeFactory()
            ).stream_complete(AICompletionRequest(prompt="probe", max_tokens=6000))
        ]

    assert caught.value.code == "output_limit"
    assert "2,800 tokens" in caught.value.safe_message
    assert "6,000 tokens" in caught.value.safe_message
    summary = await AIRepository().get_usage_summary()
    assert summary.failed_requests == 1
    assert summary.invocations[0].error_type == "output_limit"
