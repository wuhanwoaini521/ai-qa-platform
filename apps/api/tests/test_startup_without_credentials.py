"""Gate 13.5.11 — the API must start, serve, and degrade gracefully with no optional configuration.

No AI provider key, no Jira/TestRail/GitHub/Jenkins credentials, no S3 endpoint. Startup must not
depend on any of them, and the integration surfaces must fall back to their fakes/dry-run modes
instead of crashing at import or at request time. Authentication is *not* optional configuration:
the health probes stay public, everything else requires the seeded administrator's token.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

OPTIONAL_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "QA_AI_PROVIDER",
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "TESTRAIL_BASE_URL",
    "TESTRAIL_EMAIL",
    "TESTRAIL_API_KEY",
    "GITHUB_TOKEN",
    "JENKINS_BASE_URL",
    "JENKINS_USER",
    "JENKINS_API_TOKEN",
    "S3_ENDPOINT_URL",
    "S3_BUCKET_NAME",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
)

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]


def test_import_and_serve_without_any_optional_configuration(tmp_path: Path):
    """Importing the app and answering requests must not require any optional credential."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PYTHONPATH": os.pathsep.join(
            [
                str(API_ROOT),
                str(REPO_ROOT / "packages" / "qa-core"),
                str(REPO_ROOT / "packages" / "project-model"),
                str(REPO_ROOT / "packages" / "integrations"),
            ]
        ),
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}",
        "RUNTIME_DIR": str(tmp_path / "runtime"),
    }

    script = """
import asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.persistence.database import init_db


async def main():
    # ASGITransport does not run the lifespan, so create the schema exactly as startup does.
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Probes stay public so container orchestration works before any user exists.
        live = await client.get("/api/health/live")
        assert live.status_code == 200, live.text
        ready = await client.get("/api/health/ready")
        assert ready.status_code == 200, ready.text

        # Everything else is guarded, even with no optional configuration present.
        denied = await client.get("/api/ai/status")
        assert denied.status_code == 401, denied.text

        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@ai-qa.local", "password": "adminpassword"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        ai_status = await client.get("/api/ai/status")
        assert ai_status.status_code == 200, ai_status.text
        body = ai_status.json()
        assert body["status"] in {"DISABLED", "MOCK", "AVAILABLE"}, body
        assert "api_key" not in str(body).lower(), body

        jira = await client.get("/api/jira/issues", params={"query": "anything"})
        assert jira.status_code == 200, jira.text

        testrail = await client.get("/api/testrail/cases", params={"suite_id": 1})
        assert testrail.status_code == 200, testrail.text


asyncio.run(main())
print("STARTUP_OK")
"""
    # A working directory without a .env file, so nothing is silently injected.
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "STARTUP_OK" in result.stdout
    for name in OPTIONAL_ENV_VARS:
        assert name not in env
