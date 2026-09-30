from __future__ import annotations

import re

import pytest
from app.api.qa_assistant import get_assistant_service
from app.main import app
from app.services.qa_assistant_service import QAAssistantService
from qa_core.ai.provider import FakeAIProvider, FallbackAIProvider
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


class NoopAIRepository:
    async def record_invocation(self, **_):
        return None


@pytest.mark.asyncio
async def test_chat_stream_returns_ordered_sse_and_sync_route_stays_compatible(client):
    service = QAAssistantService(
        orchestrator=ProductionQAOrchestrator(ai_provider=FakeAIProvider()),
        ai_repo=NoopAIRepository(),
    )
    app.dependency_overrides[get_assistant_service] = lambda: service
    request = {
        "action": "chat",
        "message": "Explain the current workspace",
        "context": {"project_id": "project-1", "current_file": "tests/test_cart.py"},
    }
    try:
        streamed = await client.post("/api/qa-assistant/chat/stream", json=request)
        assert streamed.status_code == 200, streamed.text
        assert streamed.headers["content-type"].startswith("text/event-stream")
        event_names = re.findall(r"^event: ([^\r\n]+)", streamed.text, re.MULTILINE)
        assert event_names[0] == "run.started"
        assert event_names.index("context.loaded") < event_names.index("model.started")
        assert event_names.index("model.started") < event_names.index("model.delta")
        assert event_names.index("model.completed") < event_names.index("run.completed")
        assert "QA Assistant analysis completed" in streamed.text

        legacy = await client.post("/api/qa-assistant/chat", json=request)
        assert legacy.status_code == 200, legacy.text
        assert isinstance(legacy.json()["response"], str)
        assert "action_type" in legacy.json()
    finally:
        app.dependency_overrides.pop(get_assistant_service, None)


@pytest.mark.asyncio
async def test_chat_stream_surfaces_fake_fallback_and_provider_failure(client):
    class BrokenProvider:
        provider_name = "openai-compatible"
        model = "unreachable-model"

        async def stream_complete(self, _):
            raise RuntimeError("connection_error")
            yield

        async def complete(self, _):
            raise RuntimeError("connection_error")

    request = {
        "action": "chat",
        "message": "Summarize the current test",
        "context": {"project_id": "project-1"},
    }
    fallback_service = QAAssistantService(
        orchestrator=ProductionQAOrchestrator(ai_provider=FallbackAIProvider(BrokenProvider(), [FakeAIProvider()])),
        ai_repo=NoopAIRepository(),
    )
    app.dependency_overrides[get_assistant_service] = lambda: fallback_service
    try:
        fallback = await client.post("/api/qa-assistant/chat/stream", json=request)
        assert fallback.status_code == 200
        assert "event: run.completed" in fallback.text
        assert '"fallback_used": true' in fallback.text
        assert '"provider": "fake"' in fallback.text

        app.dependency_overrides[get_assistant_service] = lambda: QAAssistantService(
            orchestrator=ProductionQAOrchestrator(ai_provider=BrokenProvider()),
            ai_repo=NoopAIRepository(),
        )
        failed = await client.post("/api/qa-assistant/chat/stream", json=request)
        assert failed.status_code == 200
        assert "event: run.failed" in failed.text
        assert "connection_error" in failed.text
    finally:
        app.dependency_overrides.pop(get_assistant_service, None)
