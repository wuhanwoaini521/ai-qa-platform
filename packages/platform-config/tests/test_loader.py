from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from platform_config import ConfigLoadError, ConfigManager, sanitize_config_value


@pytest.fixture
def tmp_path():
    path = Path.cwd() / f".tmp-platform-config-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        for child in path.iterdir():
            if child.is_file():
                child.unlink()
        path.rmdir()


def write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_loads_yaml_values_and_secret_environment_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_TEST_CONFIG_KEY", "test-secret")
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """version: 1
ai:
  model: model-from-yaml
  api_key: ${QA_TEST_CONFIG_KEY}
jev:
  minimum_confidence: 0.73
""",
    )

    manager = ConfigManager(path)

    assert manager.get().ai.model == "model-from-yaml"
    assert manager.get().ai.api_key.get_secret_value() == "test-secret"
    assert manager.get().jev.minimum_confidence == 0.73
    assert manager.source_map()["ai.model"] == f"config:{path.resolve()}"
    assert manager.source_map()["ai.api_key"] == "env:QA_TEST_CONFIG_KEY"


def test_missing_environment_reference_and_invalid_values_are_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("QA_TEST_MISSING_CONFIG_KEY", raising=False)
    path = tmp_path / "config.yaml"
    write_config(path, "ai:\n  api_key: ${QA_TEST_MISSING_CONFIG_KEY}\n")
    with pytest.raises(ConfigLoadError, match="Missing environment variable QA_TEST_MISSING_CONFIG_KEY"):
        ConfigManager(path)

    write_config(path, "api:\n  port: 70000\n")
    with pytest.raises(ConfigLoadError, match="api.port"):
        ConfigManager(path)

    write_config(path, "repair:\n  require_candidate_verification: false\n")
    with pytest.raises(ConfigLoadError, match="repair.require_candidate_verification"):
        ConfigManager(path)

    write_config(path, "database:\n  url: postgresql+asyncpg://user:password@db/qa\n")
    with pytest.raises(ConfigLoadError, match="database.url must reference an environment variable"):
        ConfigManager(path)

    write_config(
        path,
        """repair:
  enabled: true
  mode: AUTO
  require_jev: true
jev:
  enabled: false
""",
    )
    with pytest.raises(ConfigLoadError, match="repair.mode=AUTO.*requires jev.enabled=true"):
        ConfigManager(path)


def test_reload_applies_valid_config_and_keeps_previous_snapshot_after_failure(tmp_path):
    path = tmp_path / "config.yaml"
    write_config(path, "ai:\n  model: model-a\n")
    manager = ConfigManager(path)

    write_config(path, "ai:\n  model: model-b\n")
    result = manager.reload()
    assert result.applied
    assert "ai.model" in result.changed
    assert manager.get().ai.model == "model-b"

    write_config(path, "ai:\n  timeout_seconds: -1\n")
    with pytest.raises(ConfigLoadError):
        manager.reload()
    assert manager.get().ai.model == "model-b"


def test_reload_flags_startup_only_changes_without_swapping_snapshot(tmp_path):
    path = tmp_path / "config.yaml"
    write_config(path, "api:\n  port: 8000\n")
    manager = ConfigManager(path)

    write_config(path, "api:\n  port: 8010\n")
    result = manager.reload()

    assert not result.applied
    assert result.restart_required == ("api.port",)
    assert manager.get().api.port == 8000


def test_worker_and_database_construction_settings_require_restart(tmp_path):
    path = tmp_path / "config.yaml"
    write_config(path, "worker:\n  name: original\n")
    manager = ConfigManager(path)

    cases = (
        ("worker.name", "worker:\n  name: replacement\n"),
        ("database.pool_size", "worker:\n  name: original\ndatabase:\n  pool_size: 24\n"),
        ("run.max_parallel_runs", "worker:\n  name: original\nrun:\n  max_parallel_runs: 5\n"),
        ("pytest.workers", "worker:\n  name: original\npytest:\n  workers: 2\n"),
        ("pytest.timeout_seconds", "worker:\n  name: original\npytest:\n  timeout_seconds: 90\n"),
        ("pytest.default_args", "worker:\n  name: original\npytest:\n  default_args: [-q]\n"),
    )
    for field, body in cases:
        write_config(path, body)
        result = manager.reload()
        assert not result.applied
        assert result.restart_required == (field,)


def test_config_dump_redacts_database_url_credentials():
    sanitized = sanitize_config_value(
        {
            "database": {
                "url": "postgresql+asyncpg://qa-user:db-password@db.example/qa?sslpassword=query-secret&sslmode=require"
            }
        }
    )

    assert sanitized["database"]["url"] == (
        "postgresql+asyncpg://***@db.example/qa?sslpassword=%2A%2A%2A&sslmode=require"
    )
