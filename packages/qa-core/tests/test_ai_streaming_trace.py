from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    AIStreamChunk,
    ProviderHealth,
    ProviderHealthStatus,
)
from qa_core.ai.provider import (
    FakeAIProvider,
    FallbackAIProvider,
    OpenAICompatibleProvider,
    stream_provider_completion,
)
from qa_core.ai.trace import AITraceEvent


@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_sse_chunks(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def aiter_lines(self):
            yield 'data: {"model":"stream-model","choices":[{"delta":{"content":"hello "},"finish_reason":null}]}'
            yield 'data: {"model":"stream-model","choices":[{"delta":{"content":"world"},"finish_reason":null}]}'
            yield 'data: {"model":"stream-model","choices":[{"delta":{},"finish_reason":"stop"}]}'
            yield 'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6}}'
            yield "data: [DONE]"

    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def stream(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return Response()

    monkeypatch.setattr("qa_core.ai.provider.httpx.AsyncClient", Client)
    provider = OpenAICompatibleProvider(api_key="test-secret", model="stream-model", max_retries=0)
    chunks = [chunk async for chunk in provider.stream_complete(AICompletionRequest(prompt="say hello"))]

    assert captured["json"]["stream"] is True
    assert captured["method"] == "POST"
    assert "Authorization" in captured["headers"]
    assert "".join(chunk.content_delta for chunk in chunks) == "hello world"
    assert chunks[-1].usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert any(chunk.finish_reason == "stop" for chunk in chunks)


@pytest.mark.asyncio
async def test_legacy_provider_uses_complete_adapter():
    class LegacyProvider:
        async def complete(self, request):
            return AICompletionResponse(
                content=request.prompt,
                provider="legacy",
                model="legacy-model",
                input_tokens=3,
                output_tokens=2,
            )

    chunks = [
        chunk async for chunk in stream_provider_completion(LegacyProvider(), AICompletionRequest(prompt="one shot"))
    ]
    assert len(chunks) == 1
    assert chunks[0].content_delta == "one shot"
    assert chunks[0].provider == "legacy"
    assert chunks[0].usage == {"prompt_tokens": 3, "completion_tokens": 2}


@pytest.mark.asyncio
async def test_fallback_provider_uses_fake_after_pre_delta_stream_error():
    class BrokenProvider:
        provider_name = "openai-compatible"

        async def complete(self, _):
            raise RuntimeError("network failed")

        async def stream_complete(self, _):
            raise RuntimeError("connection_error")
            yield AIStreamChunk()

    provider = FallbackAIProvider(BrokenProvider(), [FakeAIProvider()])
    chunks = [chunk async for chunk in provider.stream_complete(AICompletionRequest(prompt="Hello"))]
    assert chunks
    assert chunks[0].provider == "fake"
    assert chunks[0].fallback_used is True


@pytest.mark.asyncio
async def test_fallback_health_does_not_report_fake_as_real_available():
    class UnavailableProvider:
        async def check_health(self):
            return ProviderHealthStatus(
                provider="openai-compatible",
                status=ProviderHealth.UNAVAILABLE,
                message="connection_error",
                model="real-model",
            )

        async def complete(self, _):
            raise RuntimeError("unavailable")

    fake_health = await FakeAIProvider().check_health()
    assert fake_health.status == ProviderHealth.FALLBACK_ONLY
    health = await FallbackAIProvider(UnavailableProvider(), [FakeAIProvider()]).check_health()
    assert health.status == ProviderHealth.FALLBACK_ONLY
    assert health.provider == "openai-compatible"
    assert health.model == "fake-qa-model"


@pytest.mark.asyncio
async def test_openai_stream_exception_is_classified_without_secret(monkeypatch):
    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def stream(self, *_args, **_kwargs):
            raise httpx.ConnectError("connection failed with sk-" + "a" * 48)

    monkeypatch.setattr("qa_core.ai.provider.httpx.AsyncClient", Client)
    provider = OpenAICompatibleProvider(api_key="key", max_retries=0)
    with pytest.raises(RuntimeError, match="connection_error") as caught:
        _ = [chunk async for chunk in provider.stream_complete(AICompletionRequest(prompt="test"))]
    assert "sk-" not in str(caught.value)


@pytest.mark.asyncio
async def test_closing_stream_cancels_provider_iterator():
    closed = asyncio.Event()

    class BlockingProvider:
        async def stream_complete(self, _):
            try:
                yield AIStreamChunk(content_delta="partial", provider="stub", model="stub-model")
                await asyncio.Event().wait()
            finally:
                closed.set()

    stream = stream_provider_completion(BlockingProvider(), AICompletionRequest(prompt="test"))
    first = await anext(stream)
    assert first.content_delta == "partial"
    await stream.aclose()
    assert closed.is_set()


def test_trace_redacts_nested_sensitive_values_and_preserves_usage_counts():
    event = AITraceEvent(
        run_id="run-1",
        type="model.completed",
        stage="model",
        title="done",
        metadata={
            "authorization": "Bearer abc123",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "nested": [{"cookie": "session=secret"}, "api_key=plain-secret"],
        },
        content="Generated output token=do-not-show",
    )
    rendered = json.dumps(event.model_dump(mode="json"))
    assert "abc123" not in rendered
    assert "session=secret" not in rendered
    assert "plain-secret" not in rendered
    assert "do-not-show" not in rendered
    assert event.metadata["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
