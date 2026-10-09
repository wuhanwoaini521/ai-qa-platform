from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from platform_config.models import AppConfig

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_SECRET_PATHS = {
    "app.secret_key",
    "ai.api_key",
    "jev.api_key",
    "browser.proxy_url",
    "worker.auth_token",
    "integrations.github.token",
    "integrations.jira.token",
    "integrations.testrail.token",
    "integrations.jenkins.token",
}


class ConfigLoadError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigReloadResult:
    applied: bool
    config_path: str
    changed: tuple[str, ...] = ()
    restart_required: tuple[str, ...] = ()


def find_config_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "config" / "config.yaml"


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix: value} if prefix else {}
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        flattened.update(_flatten(item, path))
    return flattened


def _interpolate(value: Any, *, config_path: Path, source_map: dict[str, str], prefix: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: _interpolate(item, config_path=config_path, source_map=source_map, prefix=f"{prefix}.{key}" if prefix else str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_interpolate(item, config_path=config_path, source_map=source_map, prefix=prefix) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.groups()
        if name in os.environ:
            result = os.environ[name]
        elif default is not None:
            result = default
        else:
            raise ConfigLoadError(f"Missing environment variable {name} referenced by {config_path}:{prefix}")
        source_map[prefix] = f"env:{name}"
        return result

    source_map.setdefault(prefix, f"config:{config_path}")
    return _ENV_PATTERN.sub(replace, value)


def _validate_secret_references(raw: dict[str, Any], config_path: Path) -> None:
    for path, value in _flatten(raw).items():
        if path not in _SECRET_PATHS or value in (None, ""):
            continue
        if not isinstance(value, str) or not re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}", value):
            raise ConfigLoadError(f"Secret field {path} must be empty or an environment reference in {config_path}")
    database_url = _flatten(raw).get("database.url")
    if isinstance(database_url, str) and not _ENV_PATTERN.fullmatch(database_url):
        from urllib.parse import urlsplit

        parsed = urlsplit(database_url)
        if parsed.username or parsed.password:
            raise ConfigLoadError(f"database.url must reference an environment variable for credentials in {config_path}")


def _model_sources(config: AppConfig, raw_sources: dict[str, str]) -> dict[str, str]:
    fields = _flatten(config.model_dump(mode="python"))
    sources = {}
    for path in fields:
        if path in raw_sources:
            sources[path] = raw_sources[path]
        else:
            sources[path] = "schema_default"
    return sources


class ConfigManager:
    """Loads one immutable config per process and swaps validated reloads atomically."""

    RESTART_REQUIRED_FIELDS = frozenset({
        "api.host",
        "api.port",
        "api.cors_origins",
        "app.runtime_dir",
        "app.workspace_storage_dir",
        "app.artifact_storage_dir",
        "app.secret_key",
        "database.url",
        "database.echo",
        "database.pool_size",
        "database.max_overflow",
        "database.sqlite_timeout_seconds",
        "worker.api_url",
        "worker.auth_token",
        "worker.name",
        "worker.capabilities",
        "worker.max_concurrency",
        "worker.heartbeat_interval_seconds",
        "worker.poll_interval_seconds",
        "worker.http_timeout_seconds",
        "worker.workspace_storage_dir",
        "worker.artifact_storage_dir",
        "run.max_parallel_runs",
        "pytest.workers",
        "pytest.timeout_seconds",
        "pytest.default_args",
    })

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = find_config_path(path)
        self._lock = threading.RLock()
        self._config, self._sources = self._read()

    def _read(self) -> tuple[AppConfig, dict[str, str]]:
        if not self.path.is_file():
            raise ConfigLoadError(f"Configuration file not found: {self.path}")
        load_dotenv(self.path.parent.parent / ".env", override=False)
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            raise ConfigLoadError(f"Unable to read configuration file {self.path}: {type(error).__name__}") from error
        if not isinstance(raw, dict):
            raise ConfigLoadError(f"Configuration root must be a mapping: {self.path}")
        _validate_secret_references(raw, self.path)
        source_map: dict[str, str] = {path: f"config:{self.path}" for path in _flatten(raw)}
        expanded = _interpolate(raw, config_path=self.path, source_map=source_map)
        try:
            config = AppConfig.model_validate(expanded)
        except ValidationError as error:
            details = "; ".join(f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in error.errors())
            raise ConfigLoadError(f"Invalid configuration in {self.path}: {details}") from error
        return config, _model_sources(config, source_map)

    def get(self) -> AppConfig:
        with self._lock:
            return self._config

    def source_map(self) -> dict[str, str]:
        with self._lock:
            return dict(self._sources)

    def reload(self) -> ConfigReloadResult:
        candidate, candidate_sources = self._read()
        with self._lock:
            previous = self._config
            before = _flatten(previous.model_dump(mode="python"))
            after = _flatten(candidate.model_dump(mode="python"))
            changed = tuple(sorted(path for path in before if before[path] != after[path]))
            restart_required = tuple(sorted(self.RESTART_REQUIRED_FIELDS.intersection(changed)))
            if restart_required:
                return ConfigReloadResult(
                    applied=False,
                    config_path=str(self.path),
                    changed=changed,
                    restart_required=restart_required,
                )
            self._config, self._sources = candidate, candidate_sources
            return ConfigReloadResult(applied=True, config_path=str(self.path), changed=changed)

    def replace_for_test(self, config: AppConfig) -> None:
        """Replace the immutable snapshot in tests; production changes go through reload()."""
        with self._lock:
            self._config = config
