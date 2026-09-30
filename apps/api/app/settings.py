from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./runtime/ai_qa_platform.db"
    # Route authorization is on by default: every route except the probes, `/api/metrics` and
    # `/api/auth/login` needs a bearer token. Set AUTH_REQUIRED=false only for throwaway local runs —
    # the API then treats every request as the seeded administrator (see app/api/authz.py).
    auth_required: bool = True
    #: Secret used to sign session tokens. MUST be replaced in any real deployment.
    app_secret_key: str = "change-me-in-production"
    #: Session token lifetime in seconds (default 7 days).
    auth_token_ttl_seconds: int = 86400 * 7
    runtime_dir: Path = Path("./runtime")
    workspace_storage_dir: Path = Path("./runtime/workspaces")
    artifact_storage_dir: Path = Path("./runtime/artifacts")
    qa_ai_provider: str = "fake"
    qa_ai_api_key: str = ""
    qa_ai_base_url: str = "https://api.openai.com/v1"
    qa_ai_model: str = "gpt-4o-mini"
    qa_ai_timeout: float = 30.0
    qa_ai_max_retries: int = 3
    browser_proxy_url: str = ""
    browser_proxy_bypass: str = ""
    jev_enabled: bool = False
    jev_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    jev_base_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_timeout: float = 20.0
    jev_minimum_confidence: float = 0.60
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()

# Ensure directories exist
settings.runtime_dir.mkdir(parents=True, exist_ok=True)
settings.workspace_storage_dir.mkdir(parents=True, exist_ok=True)
settings.artifact_storage_dir.mkdir(parents=True, exist_ok=True)

#: Session token lifetime, read once at import (auth_service imports it as a module constant).
TOKEN_TTL_SECONDS = settings.auth_token_ttl_seconds
