from __future__ import annotations

from dataclasses import replace

import pytest
from app.persistence.models import AIProviderConfigORM
from app.services.ai_settings_service import AIRuntimeConfig, AISettingsService
from project_model.models import AIProviderConnectionResult
from qa_core.ai.models import AICompletionResponse, AIStreamChunk, ProviderHealth, ProviderHealthStatus
from qa_core.ai.provider import AIProviderError, FallbackAIProvider, OpenAICompatibleProvider
from qa_core.ai.registry import AIProviderRegistry
from sqlalchemy import select


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unavailable_real_model_does_not_claim_an_active_fallback(monkeypatch):
    service = AISettingsService()

    async def config():
        return replace(service._environment_config(), provider="openai-compatible", api_key="synthetic-key")

    async def disconnected():
        return AIProviderConnectionResult(
            connected=False,
            streaming=False,
            code="KEY_MISSING",
            message="No model key",
            provider="openai-compatible",
            status="UNAVAILABLE",
            model="test-model",
        )

    monkeypatch.setattr(service, "_effective_config", config)
    monkeypatch.setattr(service, "test_connection", disconnected)
    status = await service.get_status(refresh=True)
    assert status.status.value == "UNAVAILABLE"
    assert status.operational_state == "UNAVAILABLE"
    assert not status.fallback_active
    assert not status.real_model_available


def payload(**overrides):
    return {
        "provider": "openai-compatible",
        "api_key": "normal-ai-secret",
        "model": "test-model",
        "base_url": "https://ai.example/v1",
        "timeout": 12,
        "max_retries": 1,
        **overrides,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_status_api_reports_unconfigured_without_network_probe(client, monkeypatch):
    config = AIRuntimeConfig(
        enabled=True,
        provider="openai-compatible",
        api_key="",
        model="test-model",
        base_url="https://provider.invalid/v1",
        timeout=12,
        max_retries=1,
    )

    async def effective_config(_self):
        return config

    async def forbidden_probe(_self):
        raise AssertionError("unconfigured provider must not be probed")

    monkeypatch.setattr(AISettingsService, "_effective_config", effective_config)
    monkeypatch.setattr(OpenAICompatibleProvider, "check_health", forbidden_probe)

    response = await client.get("/api/ai/status")

    assert response.status_code == 200, response.text
    assert response.json()["operational_state"] == "UNCONFIGURED"
    assert response.json()["health_status"] == "UNCONFIGURED"
    assert response.json()["fallback_active"] is False
    assert response.json()["real_model_available"] is False
    assert '"api_key"' not in response.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_provider_settings_are_runtime_managed_and_not_persisted(client, test_db_session, monkeypatch):
    configured = AIRuntimeConfig(
        enabled=True,
        provider="openai-compatible",
        api_key="synthetic-runtime-key",
        model="configured-model",
        base_url="https://configured.invalid/v1",
        timeout=12,
        max_retries=1,
    )

    async def effective_config(_self):
        return configured

    monkeypatch.setattr(AISettingsService, "_effective_config", effective_config)
    AIProviderRegistry.reset()
    try:
        initial = await client.get("/api/ai/settings")
        assert initial.status_code == 200
        assert initial.json()["provider"] == configured.provider
        assert initial.json()["model"] == configured.model
        assert initial.json()["api_key_configured"] is True
        assert "synthetic-runtime-key" not in initial.text

        rejected = await client.put("/api/ai/settings", json=payload())
        assert rejected.status_code == 409, rejected.text
        assert "normal-ai-secret" not in rejected.text

        active = AIProviderRegistry.get_provider()
        assert isinstance(active.inner, FallbackAIProvider)
        assert active.primary.api_key == configured.api_key
        assert active.primary.model == configured.model

        async with test_db_session() as session:
            row = (await session.execute(select(AIProviderConfigORM))).scalar_one_or_none()
            assert row is None
    finally:
        AIProviderRegistry.reset()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_connection_test_uses_unsaved_settings_and_requires_admin(client, role_client, monkeypatch):
    configured = AIRuntimeConfig(
        enabled=True,
        provider="openai-compatible",
        api_key="synthetic-runtime-key",
        model="configured-model",
        base_url="https://configured.invalid/v1",
        timeout=12,
        max_retries=1,
    )

    async def effective_config(_self):
        return configured

    monkeypatch.setattr(AISettingsService, "_effective_config", effective_config)

    async def healthy(self):
        return ProviderHealthStatus(
            provider="openai-compatible",
            status=ProviderHealth.AVAILABLE,
            message="stub connection passed",
            model=self.model,
            base_url=self.base_url,
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "check_health", healthy)

    async def streaming(self, request):
        assert request.prompt_id == "provider_connection"
        assert request.thinking_mode == "disabled"
        yield AIStreamChunk(content_delta="OK", provider=self.provider_name, model=self.model)

    async def complete(self, request):
        assert request.prompt_id == "provider_structured_output_probe"
        assert request.max_tokens == 512
        assert request.thinking_mode == "disabled"
        return AICompletionResponse(
            content='{"json_mode":true}',
            structured_data={"json_mode": True},
            provider=self.provider_name,
            model=self.model,
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "stream_complete", streaming)
    monkeypatch.setattr(OpenAICompatibleProvider, "complete", complete)
    tested = await client.post("/api/ai/test-connection", json=payload(model="deepseek-flash"))
    assert tested.status_code == 200, tested.text
    assert tested.json()["connected"] is True
    assert tested.json()["streaming"] is True
    assert tested.json()["structured_output_supported"] is True

    saved = await client.get("/api/ai/settings")
    assert saved.status_code == 200
    assert saved.json()["provider"] == configured.provider
    assert saved.json()["model"] == configured.model
    assert saved.json()["base_url"] == configured.base_url

    async with role_client("QA_ENGINEER") as engineer:
        denied = await engineer.put("/api/ai/settings", json=payload())
        assert denied.status_code == 403


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ai_connection_reports_safe_provider_probe_error(client, monkeypatch):
    async def healthy(self):
        return ProviderHealthStatus(
            provider="openai-compatible",
            status=ProviderHealth.AVAILABLE,
            message="stub connection passed",
            model=self.model,
            base_url=self.base_url,
        )

    async def streaming(self, _request):
        if False:
            yield AIStreamChunk()
        raise AIProviderError("output_limit", "Probe output reached the configured token limit.")

    monkeypatch.setattr(OpenAICompatibleProvider, "check_health", healthy)
    monkeypatch.setattr(OpenAICompatibleProvider, "stream_complete", streaming)

    tested = await client.post("/api/ai/test-connection", json=payload(model="deepseek-flash"))

    assert tested.status_code == 200, tested.text
    assert tested.json()["connected"] is False
    assert "output_limit" in tested.json()["message"]
    assert "configured token limit" in tested.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_budget", [0, 1])
async def test_ai_connection_probe_honors_configured_transient_network_retries(
    test_db_session, monkeypatch, retry_budget
):
    import httpx
    from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory

    configured = AIRuntimeConfig(
        enabled=True,
        provider="openai-compatible",
        api_key="synthetic-key",
        model="probe-model",
        base_url="https://probe.invalid/v1",
        timeout=2,
        max_retries=retry_budget,
    )

    async def effective_config(_self):
        return configured

    async def healthy(self):
        return ProviderHealthStatus(provider=self.provider_name, status=ProviderHealth.AVAILABLE, model=self.model)

    attempts = []

    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("synthetic transient timeout", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text='data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(AISettingsService, "_effective_config", effective_config)
    monkeypatch.setattr(OpenAICompatibleProvider, "check_health", healthy)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs)
    )
    result = await AISettingsService(TaskRepositoryScopeFactory()).test_connection()
    assert len(attempts) == retry_budget + 1
    assert result.connected is bool(retry_budget)
    assert result.streaming is bool(retry_budget)
    if not retry_budget:
        assert "timeout" in result.message
