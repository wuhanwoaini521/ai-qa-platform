import asyncio

import pytest
from app.services.platform_health_service import PlatformHealthService


@pytest.mark.asyncio
async def test_health_is_cached_and_component_failure_does_not_hide_other_results(monkeypatch):
    service = PlatformHealthService()
    calls = []

    async def good():
        calls.append(True)
        return {"status": "ok", "message": "checked"}

    async def broken():
        raise RuntimeError("secret upstream text")

    for name in ("_database", "_ai", "_jev", "_browser", "_worker", "_test_runtime", "_filesystem", "_lsp"):
        monkeypatch.setattr(service, name, broken if name == "_ai" else good)
    health = await service.check()
    assert len(health["components"]) == 8
    assert health["status"] == "degraded"
    assert "secret upstream text" not in str(health)
    assert await service.check() is health
    assert len(calls) == 7
    await service.check(refresh=True)
    assert len(calls) == 14


@pytest.mark.asyncio
async def test_missing_worker_is_a_real_warning(test_db_session):
    result = await PlatformHealthService()._worker()
    assert result["status"] == "warning"


@pytest.mark.asyncio
async def test_ai_health_uses_shared_status(monkeypatch):
    from app.services.ai_settings_service import AISettingsService
    from project_model.models import AIStatusResponse

    async def status(_self):
        return AIStatusResponse(
            provider="fake",
            status="SIMULATION",
            model="fake-qa-model",
            message="offline",
            operational_state="FALLBACK_ONLY",
            real_model_available=False,
        )

    monkeypatch.setattr(AISettingsService, "get_status", status)
    result = await PlatformHealthService()._ai()
    assert result["status"] == "warning"
    assert result["operational_state"] == "FALLBACK_ONLY"


@pytest.mark.asyncio
async def test_health_coroutines_run_independently(monkeypatch):
    service = PlatformHealthService()
    started = set()

    async def probe(name):
        started.add(name)
        await asyncio.sleep(0.01)
        assert len(started) == 8
        return {"status": "ok", "message": name}

    for name in ("_database", "_ai", "_jev", "_browser", "_worker", "_test_runtime", "_filesystem", "_lsp"):
        monkeypatch.setattr(service, name, lambda name=name: probe(name))
    assert (await service.check())["status"] == "healthy"
