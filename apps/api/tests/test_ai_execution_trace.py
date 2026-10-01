from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services.ai_service import AIService
from app.services.qa_assistant_service import QAAssistantService
from app.services.task_runtime_service import TaskRuntimeService
from project_model.models import (
    QAChatRequest,
    QAContext,
)
from qa_core.ai.models import ProviderHealth, ProviderHealthStatus
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
async def test_fake_provider_status_is_simulation_not_real_or_fallback():
    service = object.__new__(AIService)
    service.orchestrator = SimpleNamespace(ai_provider=FakeAIProvider())
    status = await service.get_status()
    assert status.status == "SIMULATION"
    assert status.provider == "fake"
    assert status.model == "fake-qa-model"
    assert status.real_model_available is False
    assert status.fallback_active is False
    assert status.failure_reason == "fake_provider_selected"


class HealthyRealProvider:
    provider_name = "openai-compatible"
    model = "test-model"

    async def check_health(self):
        return ProviderHealthStatus(
            provider=self.provider_name,
            status=ProviderHealth.AVAILABLE,
            message="healthy",
            model=self.model,
            base_url="https://provider.invalid/v1",
        )


@pytest.mark.asyncio
async def test_real_provider_status_is_explicitly_connected():
    service = object.__new__(AIService)
    service.orchestrator = SimpleNamespace(ai_provider=HealthyRealProvider())
    status = await service.get_status()
    assert status.status == "REAL_CONNECTED"
    assert status.provider == "openai-compatible"
    assert status.model == "test-model"
    assert status.real_model_available is True
    assert status.fallback_active is False


@pytest.mark.asyncio
async def test_openai_health_failure_with_fake_backup_is_fallback_not_real():
    class UnhealthyProvider(HealthyRealProvider):
        async def check_health(self):
            return ProviderHealthStatus(
                provider=self.provider_name,
                status=ProviderHealth.UNAVAILABLE,
                message="Connection error: connection_error",
                model=self.model,
                base_url="https://provider.invalid/v1",
            )

    service = object.__new__(AIService)
    service.orchestrator = SimpleNamespace(ai_provider=FallbackAIProvider(UnhealthyProvider(), [FakeAIProvider()]))
    status = await service.get_status()
    assert status.status == "FALLBACK"
    assert status.provider == "openai-compatible"
    assert status.model == "fake-qa-model"
    assert status.real_model_available is False
    assert status.fallback_active is True
    assert status.failure_reason == "connection_error"


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
async def test_browser_jev_decision_is_saved_as_reusable_trace(monkeypatch):
    traces = []
    runtime = TaskRuntimeService()

    async def record_trace(_task_id, event):
        traces.append(event)

    async def reserve(_task_id):
        return True

    monkeypatch.setattr(runtime, "_record_ai_trace", record_trace)
    monkeypatch.setattr(runtime, "_reserve_ai_call", reserve)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def commit(self):
            return None

    class Repository:
        def __init__(self, _):
            self.task = SimpleNamespace(context={})

        async def get(self, _):
            return self.task

        async def add_event(self, *_):
            return None

    monkeypatch.setattr("app.services.task_runtime_service.async_session_factory", Session)
    monkeypatch.setattr("app.services.task_runtime_service.TaskRepository", Repository)

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

    monkeypatch.setattr(runtime, "_run_locator_decision", verify_with_shared_pipeline)
    task = SimpleNamespace(id="task-1", goal="Add product to cart")
    result = await runtime._decision_select(
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
