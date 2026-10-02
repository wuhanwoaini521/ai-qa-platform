from __future__ import annotations

import pytest
from app.persistence.models import AIProviderConfigORM
from app.services.ai_settings_service import AISettingsService
from qa_core.ai.models import AIStreamChunk, ProviderHealth, ProviderHealthStatus
from qa_core.ai.provider import FallbackAIProvider, OpenAICompatibleProvider
from qa_core.ai.registry import AIProviderRegistry
from sqlalchemy import select


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


@pytest.mark.asyncio
async def test_ai_provider_settings_are_encrypted_and_activated(client, test_db_session):
    AIProviderRegistry.reset()
    try:
        initial = await client.get("/api/ai/settings")
        assert initial.status_code == 200
        assert initial.json()["provider"] == "fake"

        saved = await client.put("/api/ai/settings", json=payload())
        assert saved.status_code == 200, saved.text
        assert saved.json()["api_key_configured"] is True
        assert "normal-ai-secret" not in saved.text

        provider = AIProviderRegistry.get_provider()
        assert isinstance(provider.inner, FallbackAIProvider)
        assert provider.primary.api_key == "normal-ai-secret"
        assert provider.primary.model == "test-model"

        async with test_db_session() as session:
            row = (await session.execute(select(AIProviderConfigORM))).scalar_one()
            assert row.encrypted_api_key and row.encrypted_api_key.startswith("enc_")
            assert "normal-ai-secret" not in row.encrypted_api_key

        AIProviderRegistry.reset()
        await AISettingsService().load_runtime_config()
        restored = AIProviderRegistry.get_provider()
        assert isinstance(restored.inner, FallbackAIProvider)
        assert restored.primary.api_key == "normal-ai-secret"
    finally:
        AIProviderRegistry.reset()


@pytest.mark.asyncio
async def test_ai_connection_test_uses_unsaved_settings_and_requires_admin(client, role_client, monkeypatch):
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
        yield AIStreamChunk(content_delta="OK", provider=self.provider_name, model=self.model)

    monkeypatch.setattr(OpenAICompatibleProvider, "stream_complete", streaming)
    tested = await client.post("/api/ai/test-connection", json=payload())
    assert tested.status_code == 200, tested.text
    assert tested.json()["connected"] is True
    assert tested.json()["streaming"] is True

    saved = await client.get("/api/ai/settings")
    assert saved.status_code == 200
    assert saved.json()["provider"] == "fake"

    async with role_client("QA_ENGINEER") as engineer:
        denied = await engineer.put("/api/ai/settings", json=payload())
        assert denied.status_code == 403
