from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.ai_settings_service import AISettingsService
from app.services.decision_settings_service import DecisionSettingsService
from platform_config import ConfigManager


@pytest.fixture
def tmp_path():
    path = Path.cwd() / f".tmp-api-config-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        resolved = path.resolve()
        if path.name.startswith(".tmp-api-config-") and Path.cwd().resolve() in resolved.parents:
            shutil.rmtree(resolved)


@pytest.mark.asyncio
async def test_ai_and_jev_runtime_services_read_reloaded_shared_config(tmp_path, monkeypatch):
    import app.settings as settings_module

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """ai:
  enabled: true
  provider: fake
  model: ai-model-a
jev:
  enabled: true
  model: jev-model-a
  timeout_seconds: 7
  retries: 2
  minimum_confidence: 0.71
""",
        encoding="utf-8",
    )
    manager = ConfigManager(config_path)
    monkeypatch.setattr(settings_module, "config_manager", manager)

    ai = AISettingsService()
    jev = DecisionSettingsService()
    assert (await ai._effective_config()).model == "ai-model-a"
    effective_jev = await jev.get_runtime_config()
    assert (effective_jev.model, effective_jev.timeout, effective_jev.retries, effective_jev.minimum_confidence) == (
        "jev-model-a",
        7,
        2,
        0.71,
    )

    config_path.write_text(
        """ai:
  enabled: true
  provider: fake
  model: ai-model-b
jev:
  enabled: true
  model: jev-model-b
  timeout_seconds: 9
  retries: 0
  minimum_confidence: 0.82
""",
        encoding="utf-8",
    )
    assert manager.reload().applied
    assert (await ai._effective_config()).model == "ai-model-b"
    effective_jev = await jev.get_runtime_config()
    assert (effective_jev.model, effective_jev.timeout, effective_jev.retries, effective_jev.minimum_confidence) == (
        "jev-model-b",
        9,
        0,
        0.82,
    )


@pytest.mark.asyncio
async def test_effective_config_api_redacts_secrets_and_reload_is_atomic(client, tmp_path, monkeypatch):
    import app.api.settings as api_settings_module
    import app.services.effective_config_service as effective_config_module
    import app.settings as settings_module

    monkeypatch.setenv("QA_CONFIG_API_TEST_SECRET", "must-not-be-returned")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://database-user:database-password@db.example/qa?password=query-password",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """version: 1
database:
  url: ${DATABASE_URL}
ai:
  enabled: true
  provider: fake
  model: api-model-a
  api_key: ${QA_CONFIG_API_TEST_SECRET}
""",
        encoding="utf-8",
    )
    manager = ConfigManager(config_path)
    monkeypatch.setattr(settings_module, "config_manager", manager)
    monkeypatch.setattr(api_settings_module, "config_manager", manager)
    monkeypatch.setattr(effective_config_module, "config_manager", manager)

    effective_response = await client.get("/api/settings/effective")
    assert effective_response.status_code == 200, effective_response.text
    assert effective_response.json()["config"]["ai"]["api_key"] == "***"
    assert "must-not-be-returned" not in effective_response.text
    assert "database-password" not in effective_response.text
    assert "database-user" not in effective_response.text
    assert "query-password" not in effective_response.text
    assert effective_response.json()["config"]["database"]["url"] == (
        "postgresql+asyncpg://***@db.example/qa?password=%2A%2A%2A"
    )

    sources_response = await client.get("/api/settings/sources")
    assert sources_response.status_code == 200, sources_response.text
    assert sources_response.json()["sources"]["ai.api_key"] == "env:QA_CONFIG_API_TEST_SECRET"

    config_path.write_text(
        "version: 1\ndatabase:\n  url: ${DATABASE_URL}\nai:\n  model: api-model-b\n",
        encoding="utf-8",
    )
    reload_response = await client.post("/api/settings/reload")
    assert reload_response.status_code == 200, reload_response.text
    assert reload_response.json()["applied"] is True
    assert (await client.get("/api/settings/effective")).json()["config"]["ai"]["model"] == "api-model-b"

    config_path.write_text(
        "database:\n  url: ${DATABASE_URL}\nai:\n  timeout_seconds: -1\n",
        encoding="utf-8",
    )
    invalid_reload = await client.post("/api/settings/reload")
    assert invalid_reload.status_code == 422
    assert (await client.get("/api/settings/effective")).json()["config"]["ai"]["model"] == "api-model-b"


def test_repair_rerun_scope_uses_configured_nodeid_policy(tmp_path, monkeypatch):
    import app.settings as settings_module
    from app.services.failure_workflow_service import _repair_verification_nodeids

    config_path = tmp_path / "config.yaml"
    config_path.write_text("repair:\n  rerun_exact_nodeid: true\n", encoding="utf-8")
    manager = ConfigManager(config_path)
    monkeypatch.setattr(settings_module, "config_manager", manager)
    test_nodeid = "tests/test_checkout.py::test_purchase[card]"

    assert _repair_verification_nodeids(test_nodeid) == [test_nodeid]

    config_path.write_text("repair:\n  rerun_exact_nodeid: false\n", encoding="utf-8")
    assert manager.reload().applied
    assert _repair_verification_nodeids(test_nodeid) == ["tests/test_checkout.py"]


def test_ai_orchestrator_uses_centralized_per_run_budget(tmp_path, monkeypatch):
    import app.settings as settings_module
    from app.services.ai_runtime import build_ai_orchestrator

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """ai:
  budget:
    enabled: true
    max_requests_per_run: 7
    max_input_tokens_per_run: 11
    max_output_tokens_per_run: 13
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "config_manager", ConfigManager(config_path))

    budget = build_ai_orchestrator().budget_guard
    assert (budget.max_requests, budget.max_input_tokens, budget.max_output_tokens) == (7, 11, 13)


@pytest.mark.asyncio
async def test_zero_traceback_limit_does_not_preserve_full_traceback(tmp_path, monkeypatch):
    import app.settings as settings_module
    from app.services.failure_evidence_service import FailureEvidenceService

    config_path = tmp_path / "config.yaml"
    config_path.write_text("failure:\n  traceback_chars: 0\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "config_manager", ConfigManager(config_path))
    record = SimpleNamespace(
        test_nodeid="tests/test_example.py::test_example",
        screenshot_path=None,
        trace_path=None,
        dom_snapshot_path=None,
        console_logs=[],
        error_message="example error",
        stack_trace="example traceback",
        failing_locator=None,
    )

    evidence = await FailureEvidenceService.collect(record, None, None)

    assert evidence.error == ""
    assert evidence.traceback == ""
