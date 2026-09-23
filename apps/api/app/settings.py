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
    runtime_dir: Path = Path("./runtime")
    workspace_storage_dir: Path = Path("./runtime/workspaces")
    artifact_storage_dir: Path = Path("./runtime/artifacts")
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
