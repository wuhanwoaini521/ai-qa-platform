import asyncio

import pytest
from app.adapters.persistence.sqlalchemy_health_probe import SqlAlchemyDatabaseHealthProbe
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.platform_health_service import PlatformHealthService


def _health_service() -> PlatformHealthService:
    return PlatformHealthService(
        repository_scope=TaskRepositoryScopeFactory(),
        database_health_probe=SqlAlchemyDatabaseHealthProbe(),
    )


@pytest.mark.asyncio
async def test_database_health_compares_applied_migration_revision(test_db_session):
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from app.persistence import database
    from app.persistence.migrations import migration_config

    script_directory = ScriptDirectory.from_config(migration_config())
    head_revision = script_directory.get_current_head()
    async with database.engine.begin() as connection:
        await connection.run_sync(lambda conn: MigrationContext.configure(conn).stamp(script_directory, head_revision))

    result = await _health_service()._database()

    assert result["status"] == "ok"
    assert result["current_revision"] == result["head_revision"]


@pytest.mark.asyncio
async def test_health_is_cached_and_component_failure_does_not_hide_other_results(monkeypatch):
    service = _health_service()
    calls = []

    async def good(**_kwargs):
        calls.append(True)
        return {"status": "ok", "message": "checked"}

    async def broken(**_kwargs):
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
async def test_missing_remote_worker_uses_local_execution_health(test_db_session):
    result = await _health_service()._worker()
    assert result["status"] == "ok"
    assert result["operational_state"] == "LOCAL_EXECUTION_AVAILABLE"


@pytest.mark.asyncio
async def test_ai_health_uses_shared_status(monkeypatch):
    from app.services.ai_settings_service import AISettingsService
    from project_model.models import AIStatusResponse

    async def status(_self, refresh=False):
        return AIStatusResponse(
            provider="fake",
            status="SIMULATION",
            model="fake-qa-model",
            message="offline",
            operational_state="DEGRADED",
            real_model_available=False,
        )

    monkeypatch.setattr(AISettingsService, "get_status", status)
    result = await _health_service()._ai()
    assert result["status"] == "warning"
    assert result["operational_state"] == "DEGRADED"


@pytest.mark.asyncio
async def test_health_coroutines_run_independently(monkeypatch):
    service = _health_service()
    started = set()

    async def probe(name):
        started.add(name)
        await asyncio.sleep(0.01)
        assert len(started) == 8
        return {"status": "ok", "message": name}

    for name in ("_database", "_ai", "_jev", "_browser", "_worker", "_test_runtime", "_filesystem", "_lsp"):
        monkeypatch.setattr(service, name, lambda name=name, **_kwargs: probe(name))
    assert (await service.check())["status"] == "healthy"
