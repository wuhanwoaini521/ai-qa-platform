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
        for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()


def write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_loads_yaml_values_and_secret_environment_interpolation(tmp_path, monkeypatch):
    for name in (
        "QA_AI_ENABLED",
        "QA_AI_PROVIDER",
        "QA_AI_API_KEY",
        "QA_AI_BASE_URL",
        "QA_AI_MODEL",
        "QA_AI_TIMEOUT_SECONDS",
        "QA_AI_MAX_RETRIES",
        "JEV_ENABLED",
        "JEV_API_KEY",
        "JEV_BASE_URL",
        "JEV_MODEL",
        "JEV_TIMEOUT_SECONDS",
        "JEV_RETRIES",
        "JEV_MINIMUM_CONFIDENCE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QA_TEST_CONFIG_KEY", "test-secret")
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    path = isolated / "config.yaml"
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


def test_process_environment_overrides_yaml_for_provider_runtime_fields(tmp_path, monkeypatch):
    overrides = {
        "QA_AI_ENABLED": "false",
        "QA_AI_PROVIDER": "fake",
        "QA_AI_API_KEY": "synthetic-ai-key",
        "QA_AI_BASE_URL": "https://ai-env.example/v1",
        "QA_AI_MODEL": "ai-env-model",
        "QA_AI_TIMEOUT_SECONDS": "17",
        "QA_AI_MAX_RETRIES": "0",
        "JEV_ENABLED": "false",
        "JEV_API_KEY": "synthetic-jev-key",
        "JEV_BASE_URL": "https://jev-env.example/v1/systemone",
        "JEV_MODEL": "jev-env-model",
        "JEV_TIMEOUT_SECONDS": "19",
        "JEV_RETRIES": "0",
        "JEV_MINIMUM_CONFIDENCE": "0.81",
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    path = tmp_path / "config.yaml"
    write_config(
        path,
        """ai:
  enabled: true
  provider: openai-compatible
  api_key: ${QA_AI_API_KEY:-}
  base_url: https://ai-yaml.example/v1
  model: ai-yaml-model
  timeout_seconds: 30
  retries: 3
jev:
  enabled: true
  api_key: ${JEV_API_KEY:-}
  base_url: https://jev-yaml.example/v1/systemone
  model: jev-yaml-model
  timeout_seconds: 30
  retries: 1
  minimum_confidence: 0.60
""",
    )

    manager = ConfigManager(path)
    config = manager.get()
    assert (config.ai.enabled, config.ai.provider, config.ai.base_url, config.ai.model) == (
        False,
        "fake",
        "https://ai-env.example/v1",
        "ai-env-model",
    )
    assert (config.ai.timeout_seconds, config.ai.retries) == (17, 0)
    assert config.ai.api_key.get_secret_value() == "synthetic-ai-key"
    assert (config.jev.enabled, config.jev.base_url, config.jev.model) == (
        False,
        "https://jev-env.example/v1/systemone",
        "jev-env-model",
    )
    assert (config.jev.timeout_seconds, config.jev.retries, config.jev.minimum_confidence) == (19, 0, 0.81)
    assert config.jev.api_key.get_secret_value() == "synthetic-jev-key"
    assert manager.source_map()["ai.base_url"] == "env:QA_AI_BASE_URL"
    assert manager.source_map()["ai.api_key"] == "env:QA_AI_API_KEY"
    assert manager.source_map()["jev.model"] == "env:JEV_MODEL"


def test_yaml_values_win_when_no_provider_environment_override_is_present(tmp_path, monkeypatch):
    names = (
        "QA_AI_ENABLED",
        "QA_AI_PROVIDER",
        "QA_AI_API_KEY",
        "QA_AI_BASE_URL",
        "QA_AI_MODEL",
        "QA_AI_TIMEOUT_SECONDS",
        "QA_AI_MAX_RETRIES",
        "JEV_ENABLED",
        "JEV_API_KEY",
        "JEV_BASE_URL",
        "JEV_MODEL",
        "JEV_TIMEOUT_SECONDS",
        "JEV_RETRIES",
        "JEV_MINIMUM_CONFIDENCE",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    path = isolated / "config.yaml"
    write_config(
        path, "ai:\n  model: yaml-model\n  timeout_seconds: 23\n  retries: 2\njev:\n  model: yaml-jev\n  retries: 3\n"
    )
    config = ConfigManager(path).get()
    assert (config.ai.model, config.ai.timeout_seconds, config.ai.retries) == ("yaml-model", 23, 2)
    assert (config.jev.model, config.jev.retries) == ("yaml-jev", 3)


def test_compose_passes_documented_provider_overrides_to_api():
    import yaml

    compose = yaml.safe_load((Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["api"]["environment"]
    expected = {
        "QA_AI_ENABLED",
        "QA_AI_PROVIDER",
        "QA_AI_API_KEY",
        "QA_AI_BASE_URL",
        "QA_AI_MODEL",
        "QA_AI_TIMEOUT_SECONDS",
        "QA_AI_MAX_RETRIES",
        "JEV_ENABLED",
        "JEV_API_KEY",
        "JEV_BASE_URL",
        "JEV_MODEL",
        "JEV_TIMEOUT_SECONDS",
        "JEV_RETRIES",
        "JEV_MINIMUM_CONFIDENCE",
    }
    assert expected <= environment.keys()


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
