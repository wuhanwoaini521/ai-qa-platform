from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel
from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    AIStreamChunk,
    ProviderHealth,
    ProviderHealthStatus,
)
from qa_core.ai.provider import (
    AIProviderError,
    FakeAIProvider,
    FallbackAIProvider,
    OpenAICompatibleProvider,
    stream_provider_completion,
)
from qa_core.ai.registry import AIProviderRegistry
from qa_core.ai.trace import AITraceEvent
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_repairs_invalid_streamed_schema_within_the_same_timeout():
    class Summary(BaseModel):
        summary: str

    class InvalidStreamProvider:
        provider_name = "test"
        model = "test-model"

        def __init__(self):
            self.repair_calls = 0

        async def stream_complete(self, _request):
            yield AIStreamChunk(content_delta='{"summary":', provider=self.provider_name, model=self.model)
            yield AIStreamChunk(usage={"prompt_tokens": 4, "completion_tokens": 2})

        async def complete(self, _request):
            self.repair_calls += 1
            return AICompletionResponse(
                content='{"summary":"recovered"}',
                structured_data={"summary": "recovered"},
                input_tokens=3,
                output_tokens=1,
                provider=self.provider_name,
                model=self.model,
            )

    provider = InvalidStreamProvider()
    orchestrator = ProductionQAOrchestrator(ai_provider=provider)
    response = await orchestrator.complete_streaming(
        AICompletionRequest(prompt="diagnose", response_schema=Summary),
        timeout_seconds=2,
    )

    assert response.structured_data == {"summary": "recovered"}
    assert provider.repair_calls == 1
    assert orchestrator.budget_guard.requests_count == 2
    assert orchestrator.budget_guard.input_tokens_count == 7
    assert orchestrator.budget_guard.output_tokens_count == 3


@pytest.mark.asyncio
async def test_failure_diagnosis_uses_bounded_output_budget_for_complete_streamed_json():
    class DiagnosisProvider:
        provider_name = "test"
        model = "test-model"

        def __init__(self):
            self.max_tokens = None

        async def stream_complete(self, request):
            self.max_tokens = request.max_tokens
            yield AIStreamChunk(
                content_delta=json.dumps(
                    {
                        "classification": "LOCATOR_CHANGED",
                        "root_cause": "The original selector no longer matches.",
                        "evidence": ["The failed locator timed out."],
                        "hypotheses": [],
                        "recommended_actions": ["Inspect the current page controls."],
                        "confidence": 0.9,
                    }
                ),
                finish_reason="stop",
                provider=self.provider_name,
                model=self.model,
            )

    provider = DiagnosisProvider()
    orchestrator = ProductionQAOrchestrator(ai_provider=provider)

    async def on_progress(_generated_chars, _elapsed_seconds):
        return None

    result = await orchestrator.diagnose_failure_ai(
        error_message="TimeoutError: locator not found",
        test_nodeid="tests/test_checkout.py::test_checkout",
        on_progress=on_progress,
    )

    assert result.classification == "LOCATOR_CHANGED"
    assert provider.max_tokens == 5000


@pytest.mark.asyncio
async def test_stream_output_limit_is_not_retried_as_schema_repair():
    class Summary(BaseModel):
        summary: str

    class TruncatedProvider:
        provider_name = "test"
        model = "test-model"

        def __init__(self):
            self.complete_calls = 0

        async def stream_complete(self, _request):
            yield AIStreamChunk(content_delta='{"summary":"partial', provider=self.provider_name)
            yield AIStreamChunk(
                usage={"completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
            )

        async def complete(self, _request):
            self.complete_calls += 1
            raise AssertionError("a truncated stream must not trigger a second, non-stream request")

    provider = TruncatedProvider()
    orchestrator = ProductionQAOrchestrator(ai_provider=provider)
    with pytest.raises(AIProviderError, match="输出长度上限") as caught:
        await orchestrator.complete_streaming(
            AICompletionRequest(prompt="analyze", response_schema=Summary, max_tokens=6000),
            timeout_seconds=2,
        )

    assert caught.value.code == "output_limit"
    assert "2,800 tokens" in caught.value.safe_message
    assert "6,000 tokens" in caught.value.safe_message
    assert provider.complete_calls == 0
    assert orchestrator.budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_fallback_stream_output_limit_preserves_and_records_usage():
    class EmptyTruncatedProvider:
        provider_name = "test"
        model = "test-model"

        async def stream_complete(self, _request):
            yield AIStreamChunk(
                usage={"prompt_tokens": 20, "completion_tokens": 2800},
                finish_reason="length",
                provider=self.provider_name,
                model=self.model,
            )

    orchestrator = ProductionQAOrchestrator(ai_provider=FallbackAIProvider(EmptyTruncatedProvider()))

    with pytest.raises(AIProviderError) as caught:
        await orchestrator.complete_streaming(
            AICompletionRequest(prompt="analyze", max_tokens=6000),
            timeout_seconds=2,
        )

    assert caught.value.code == "output_limit"
    assert caught.value.input_tokens == 20
    assert caught.value.output_tokens == 2800
    assert orchestrator.budget_guard.input_tokens_count == 20
    assert orchestrator.budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_empty_stream_uses_configured_fallback_and_reports_when_unrecovered():
    class EmptyProvider:
        provider_name = "empty"

        async def stream_complete(self, _request):
            yield AIStreamChunk(finish_reason="stop", provider=self.provider_name)

    request = AICompletionRequest(
        prompt="diagnose the following test failure: timeout",
        prompt_id="failure_diagnosis",
    )
    recovered = ProductionQAOrchestrator(ai_provider=FallbackAIProvider(EmptyProvider(), [FakeAIProvider()]))
    result = await recovered.complete_streaming(request, timeout_seconds=2)
    assert result.content
    assert result.fallback_used is True

    unrecovered = ProductionQAOrchestrator(ai_provider=FallbackAIProvider(EmptyProvider()))
    with pytest.raises(AIProviderError) as caught:
        await unrecovered.complete_streaming(request, timeout_seconds=2)
    assert caught.value.code == "empty_stream"
    assert "没有返回可用文本" in caught.value.safe_message


@pytest.mark.asyncio
async def test_non_streaming_assistant_output_limit_records_usage_and_uses_larger_budget(monkeypatch):
    requested_max_tokens = []

    def handler(_request):
        requested_max_tokens.append(json.loads(_request.content)["max_tokens"])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "partial"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 2800},
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "qa_core.ai.provider.httpx.AsyncClient", lambda *args, **kwargs: original_client(transport=transport)
    )
    provider = OpenAICompatibleProvider(api_key="test-secret", base_url="https://mock-ai.local/v1", max_retries=0)
    orchestrator = ProductionQAOrchestrator(ai_provider=provider)

    with pytest.raises(AIProviderError) as caught:
        await orchestrator.assist_code_chat(action="chat", message="analyze")

    assert caught.value.code == "output_limit"
    assert "2,800 tokens" in caught.value.safe_message
    assert "6,000 tokens" in caught.value.safe_message
    assert requested_max_tokens == [6000]
    assert caught.value.input_tokens == 20
    assert caught.value.output_tokens == 2800
    assert orchestrator.budget_guard.input_tokens_count == 20
    assert orchestrator.budget_guard.output_tokens_count == 2800


@pytest.mark.asyncio
async def test_stream_cleanup_cannot_exceed_diagnosis_timeout(monkeypatch):
    class Summary(BaseModel):
        summary: str

    class HangingCloseStream:
        def __init__(self):
            self.yielded = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.yielded:
                raise StopAsyncIteration
            self.yielded = True
            return AIStreamChunk(content_delta='{"summary":"done"}')

        async def aclose(self):
            await asyncio.Event().wait()

    stream = HangingCloseStream()
    monkeypatch.setattr(
        "qa_core.orchestrator.orchestrator.stream_provider_completion",
        lambda *_: stream,
    )
    orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())

    with pytest.raises(RuntimeError, match="AI completion timed out after 0.01 seconds"):
        await orchestrator.complete_streaming(
            AICompletionRequest(prompt="diagnose", response_schema=Summary),
            timeout_seconds=0.01,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fallbacks", [None, []])
async def test_real_provider_outage_does_not_create_simulated_success(fallbacks):
    class Unavailable:
        async def complete(self, _):
            raise RuntimeError("actual provider unavailable")

        async def stream_complete(self, _):
            raise RuntimeError("actual provider unavailable")
            yield AIStreamChunk()

    provider = FallbackAIProvider(Unavailable(), fallbacks)
    with pytest.raises(RuntimeError, match="actual provider unavailable"):
        await provider.complete(AICompletionRequest(prompt="diagnose"))
    with pytest.raises(RuntimeError, match="AI provider unavailable"):
        _ = [chunk async for chunk in provider.stream_complete(AICompletionRequest(prompt="diagnose"))]


@pytest.mark.asyncio
async def test_complete_does_not_return_success_shaped_response_when_all_providers_fail():
    class Unavailable:
        async def complete(self, _):
            raise RuntimeError("connection_error")

    provider = FallbackAIProvider(Unavailable(), [Unavailable()])
    with pytest.raises(AIProviderError) as caught:
        await provider.complete(AICompletionRequest(prompt="diagnose"))

    assert caught.value.code == "provider_unavailable"
    assert "分析未完成" in caught.value.safe_message


def test_real_provider_registry_has_no_implicit_fake_fallback():
    AIProviderRegistry.reset()
    try:
        AIProviderRegistry.configure_runtime(
            {"provider": "openai-compatible", "api_key": "", "base_url": "http://127.0.0.1:1/v1"}
        )
        provider = AIProviderRegistry.get_provider()
        assert isinstance(provider, FallbackAIProvider)
        assert provider.fallbacks == []
    finally:
        AIProviderRegistry.reset()


@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_sse_chunks(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

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
    chunks = [
        chunk
        async for chunk in provider.stream_complete(AICompletionRequest(prompt="say hello", thinking_mode="disabled"))
    ]

    assert captured["json"]["stream"] is True
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["method"] == "POST"
    assert "Authorization" in captured["headers"]
    assert "".join(chunk.content_delta for chunk in chunks) == "hello world"
    assert chunks[-1].usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert any(chunk.finish_reason == "stop" for chunk in chunks)


@pytest.mark.asyncio
async def test_openai_compatible_provider_accepts_non_streaming_json_response(monkeypatch):
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def aread(self):
            return json.dumps(
                {
                    "model": "json-model",
                    "choices": [{"message": {"content": "recovered"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                }
            ).encode()

    class Client:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("qa_core.ai.provider.httpx.AsyncClient", Client)
    provider = OpenAICompatibleProvider(api_key="test-secret", model="configured-model", max_retries=0)

    chunks = [chunk async for chunk in provider.stream_complete(AICompletionRequest(prompt="diagnose"))]

    assert len(chunks) == 1
    assert chunks[0].content_delta == "recovered"
    assert chunks[0].model == "json-model"
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].usage == {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}


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
