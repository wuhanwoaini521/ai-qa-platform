from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_service import AIService
from app.services.qa_assistant_service import QAAssistantService
from app.services.task_runtime_service import TaskRuntimeService
from project_model.models import (
    QAChatRequest,
    QAContext,
)
from qa_core.ai.budget import AIBudgetGuard
from qa_core.ai.models import AIStreamChunk
from qa_core.ai.provider import FakeAIProvider, FallbackAIProvider


class NoopAIRepository:
    async def record_invocation(self, **_):
        return None


def assistant_request(action: str = "chat") -> QAChatRequest:
    return QAChatRequest(
        action=action,
        message="Explain this failure context",
        context=QAContext(project_id="project-1", current_file="tests/test_cart.py", selected_code="assert x"),
    )


@pytest.mark.asyncio
async def test_fake_provider_status_is_simulation_not_real_or_fallback(test_db_session):
    from app.services.ai_settings_service import AISettingsService

    status = await AISettingsService(repository_scope=TaskRepositoryScopeFactory()).get_status(refresh=True)
    assert status.status == "SIMULATION"
    assert status.provider == "fake"
    assert status.real_model_available is False
    assert status.streaming is False
    assert status.fallback_active is False
    assert status.failure_reason == "fake_provider_selected"


@pytest.mark.asyncio
async def test_status_is_shared_and_requires_streamed_model_response(test_db_session, monkeypatch):
    from app.services.ai_settings_service import AIRuntimeConfig, AISettingsService
    from project_model.models import AIProviderConnectionResult

    service = AISettingsService(repository_scope=TaskRepositoryScopeFactory())
    calls = []

    async def config(_self):
        return AIRuntimeConfig(
            "openai-compatible", "synthetic-key", "synthetic-model", "https://provider.invalid/v1", 3, 0
        )

    async def probe(_self, update=None):
        calls.append(True)
        return AIProviderConnectionResult(
            connected=True,
            provider="openai-compatible",
            status="AVAILABLE",
            model="synthetic-model",
            streaming=True,
            message="synthetic streamed contract",
        )

    monkeypatch.setattr(AISettingsService, "_effective_config", config)
    monkeypatch.setattr(AISettingsService, "test_connection", probe)
    status = await service.get_status(refresh=True)
    assert status.operational_state == "REAL_AVAILABLE"
    assert (await AIService(settings_service=service).get_status()) == status
    assert len(calls) == 1

    async def discovery_only(_self, update=None):
        return AIProviderConnectionResult(
            connected=True,
            provider="openai-compatible",
            status="AVAILABLE",
            model="synthetic-model",
            streaming=False,
            message="discovery only",
        )

    monkeypatch.setattr(AISettingsService, "test_connection", discovery_only)
    unavailable = await service.get_status(refresh=True)
    assert unavailable.real_model_available is False
    assert unavailable.operational_state == "UNAVAILABLE"
    assert unavailable.status == "UNAVAILABLE"
    assert unavailable.fallback_active is False


@pytest.mark.asyncio
async def test_qa_assistant_stream_has_ordered_trace_and_fake_fallback_marker():
    service = QAAssistantService(
        orchestrator=SimpleNamespace(ai_provider=FakeAIProvider()),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]
    event_types = [event.type for event in events]
    assert event_types[0] == "run.started"
    assert event_types.index("context.loaded") < event_types.index("model.started")
    assert event_types.index("model.started") < event_types.index("model.delta")
    assert event_types.index("model.delta") < event_types.index("model.completed")
    assert event_types.index("validation.completed") < event_types.index("run.completed")
    completion = next(event for event in events if event.type == "run.completed")
    assert completion.metadata["fallback_used"] is True
    assert any(event.content for event in events if event.type == "model.delta")


@pytest.mark.asyncio
async def test_qa_assistant_stream_emits_failure_instead_of_hanging():
    class BrokenProvider:
        provider_name = "openai-compatible"
        model = "test-model"

        async def stream_complete(self, _):
            raise RuntimeError("connection_error")
            yield

        async def complete(self, _):
            raise RuntimeError("connection_error")

    service = QAAssistantService(
        orchestrator=SimpleNamespace(ai_provider=BrokenProvider()),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]
    failed = next(event for event in events if event.type == "run.failed")
    assert failed.message == "connection_error"


@pytest.mark.asyncio
async def test_qa_assistant_stream_raises_clear_error_for_truncated_answer():
    class TruncatedProvider:
        provider_name = "openai-compatible"
        model = "test-model"

        def __init__(self):
            self.request = None

        async def stream_complete(self, request):
            self.request = request
            yield AIStreamChunk(
                content_delta="Partial answer",
                provider=self.provider_name,
                model=self.model,
            )
            yield AIStreamChunk(
                usage={"completion_tokens": 2000},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    provider = TruncatedProvider()
    budget_guard = AIBudgetGuard()
    service = QAAssistantService(
        orchestrator=SimpleNamespace(ai_provider=provider, budget_guard=budget_guard),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]

    failed = next(event for event in events if event.type == "run.failed")
    assert provider.request.max_tokens == 6000
    assert failed.title == "AI 输出不完整"
    assert "本次已生成 2,000 tokens" in failed.message
    assert "请求上限为 6,000 tokens" in failed.message
    assert failed.metadata["failure_reason"] == "output_limit"
    assert not any(event.type == "run.completed" for event in events)
    assert budget_guard.output_tokens_count == 2000


@pytest.mark.asyncio
async def test_qa_assistant_fallback_stream_records_usage_when_truncated_without_content():
    class EmptyTruncatedProvider:
        provider_name = "openai-compatible"
        model = "test-model"

        async def stream_complete(self, _request):
            yield AIStreamChunk(
                usage={"prompt_tokens": 20, "completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    provider = FallbackAIProvider(EmptyTruncatedProvider())
    budget_guard = AIBudgetGuard()
    service = QAAssistantService(
        orchestrator=SimpleNamespace(ai_provider=provider, budget_guard=budget_guard),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]

    failed = next(event for event in events if event.type == "run.failed")
    assert "本次已生成 2,800 tokens" in failed.message
    assert "请求上限为 6,000 tokens" in failed.message
    assert failed.metadata["failure_reason"] == "output_limit"
    assert budget_guard.input_tokens_count == 20
    assert budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_qa_assistant_reports_budget_exceeded_after_recording_truncated_usage():
    class EmptyTruncatedProvider:
        provider_name = "openai-compatible"
        model = "test-model"

        async def stream_complete(self, _request):
            yield AIStreamChunk(
                usage={"prompt_tokens": 20, "completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    budget_guard = AIBudgetGuard(max_output_tokens=100)
    service = QAAssistantService(
        orchestrator=SimpleNamespace(
            ai_provider=FallbackAIProvider(EmptyTruncatedProvider()),
            budget_guard=budget_guard,
        ),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]

    failed = next(event for event in events if event.type == "run.failed")
    assert failed.title == "AI 用量超出预算"
    assert failed.metadata["failure_reason"] == "budget_exceeded"
    assert "AI output token budget exceeded" in failed.message
    assert budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_qa_assistant_reports_budget_exceeded_for_partial_truncated_stream():
    class TruncatedProvider:
        provider_name = "openai-compatible"
        model = "test-model"

        async def stream_complete(self, _request):
            yield AIStreamChunk(
                content_delta="Partial answer",
                provider=self.provider_name,
                model=self.model,
            )
            yield AIStreamChunk(
                usage={"prompt_tokens": 20, "completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    budget_guard = AIBudgetGuard(max_output_tokens=100)
    service = QAAssistantService(
        orchestrator=SimpleNamespace(ai_provider=TruncatedProvider(), budget_guard=budget_guard),
        ai_repo=NoopAIRepository(),
    )
    events = [event async for event in service.stream_request(assistant_request())]

    failed = next(event for event in events if event.type == "run.failed")
    assert failed.title == "AI 用量超出预算"
    assert failed.metadata["failure_reason"] == "budget_exceeded"
    assert "AI output token budget exceeded" in failed.message
    assert budget_guard.input_tokens_count == 20
    assert budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_browser_jev_decision_is_saved_as_reusable_trace(monkeypatch):
    traces = []
    runtime = TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory())

    async def record_trace(_task_id, event):
        traces.append(event)

    async def reserve(_task_id):
        return True

    monkeypatch.setattr(runtime.execution.execution_ports, "record_ai_trace", record_trace)
    monkeypatch.setattr(runtime.execution.ai_service, "reserve_ai_call", reserve)

    class Repository:
        def __init__(self):
            self.task = SimpleNamespace(context={})

        async def get(self, _):
            return self.task

        async def add_event(self, *_):
            return None

        async def update_context(self, _task_id, **context):
            self.task.context.update(context)

    class RepositoryScope:
        def __init__(self):
            self.tasks = Repository()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def commit(self):
            return None

    monkeypatch.setattr(runtime.execution.execution_ports, "repository_scope", RepositoryScope)

    async def record_evidence(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runtime.execution.execution_ports, "evidence", record_evidence)

    async def verify_with_shared_pipeline(_task, _observed, _event, _candidates, _pipeline, _run_id):
        return {
            "selected_candidate": {"task_candidate_index": 1},
            "summary": {
                "engine": "Jev",
                "candidate_id": "candidate_1",
                "candidate_count": 2,
                "confidence": 0.91,
                "model": "jev-test",
                "latency_ms": 15.0,
                "verified": True,
            },
            "trace": [],
        }

    monkeypatch.setattr(runtime.execution.browser_executor, "_run_locator_decision", verify_with_shared_pipeline)
    task = SimpleNamespace(id="task-1", goal="Add product to cart")
    result = await runtime.execution.browser_executor._decision_select(
        task,
        {
            "inspect": {
                "url": "https://shop.invalid",
                "title": "Shop",
                "candidates": [
                    {"index": 1, "role": "button", "name": "Add to cart", "safe": True},
                    {"index": 2, "role": "link", "name": "View cart", "safe": True},
                ],
            }
        },
    )

    decision_trace = next(event for event in traces if event.type == "decision_completed")
    assert decision_trace.metadata["provider"] == "jev"
    assert decision_trace.metadata["candidate_count"] == 2
    assert decision_trace.metadata["selected_action"]["name"] == "Add to cart"
    assert decision_trace.metadata["confidence"] == 0.91
    assert result["choice"] == "1"
