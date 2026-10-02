"""Bounded readiness checks, with authenticated detail and cached optional-provider probes."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import inspect, select

from app.persistence import database
from app.persistence.models import WorkerORM, utc_now
from app.services.decision_settings_service import DecisionSettingsService
from app.settings import settings


class PlatformHealthService:
    def __init__(self):
        self._cached = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def check(self, refresh=False):
        if not refresh and self._cached and time.monotonic() < self._expires:
            return self._cached
        async with self._lock:
            if not refresh and self._cached and time.monotonic() < self._expires:
                return self._cached

            async def probe(name, callback):
                started = time.perf_counter()
                try:
                    value = await asyncio.wait_for(callback(), timeout=6)
                except Exception as error:
                    value = {"status": "error", "message": type(error).__name__}
                return {"component": name, **value, "duration_ms": round((time.perf_counter() - started) * 1000, 1)}

            components = await asyncio.gather(
                *[
                    probe("database", self._database),
                    probe("ai", self._ai),
                    probe("jev", self._jev),
                    probe("browser", self._browser),
                    probe("worker", self._worker),
                    probe("test_runtime", self._test_runtime),
                    probe("filesystem", self._filesystem),
                    probe("python_lsp", self._lsp),
                ]
            )
            self._cached = {
                "status": "healthy" if all(item["status"] == "ok" for item in components) else "degraded",
                "checked_at": utc_now().isoformat(),
                "components": components,
            }
            self._expires = time.monotonic() + 30
            return self._cached

    async def _database(self):
        if not await database.check_db_health():
            return {"status": "error", "message": "Database is unreachable."}
        async with database.engine.connect() as connection:
            pending = []
            for table, column, _ in database.ADDITIVE_COLUMNS:
                columns = await connection.run_sync(
                    lambda conn, name=table: {item["name"] for item in inspect(conn).get_columns(name)}
                )
                if column not in columns:
                    pending.append(f"{table}.{column}")
        return {
            "status": "error" if pending else "ok",
            "message": "Database schema update pending." if pending else "Database connected; schema is current.",
            "pending_columns": pending,
        }

    async def _ai(self):
        from app.services.ai_settings_service import AISettingsService

        status = await AISettingsService().get_status()
        real_available = status.real_model_available
        return {
            "status": "ok" if real_available else "warning",
            "message": status.message,
            "operational_state": status.operational_state,
            "provider": status.provider,
            "model": status.model,
            "streaming": status.streaming,
        }

    async def _jev(self):
        config = await DecisionSettingsService().get_runtime_config()
        if not config.enabled or not config.api_key:
            return {
                "status": "warning",
                "message": "Jev is disabled or its key is missing; local strategy remains available.",
                "operational_state": "UNAVAILABLE",
            }
        # A synthetic decision tests the actual endpoint without sending project content.
        from project_model.models import DecisionOption, DecisionRequest

        from app.services.decision_service import DecisionService

        result = await DecisionService().choose(
            DecisionRequest(
                name="readiness_check",
                state={"probe": True},
                options=[DecisionOption(key="ok", description="Confirm service readiness")],
            ),
        )
        available = result.provider == "jev" and not result.fallback_used and result.choice == "ok"
        return {
            "status": "ok" if available else "warning",
            "message": "Jev decision endpoint checked." if available else result.reason or "Decision unavailable.",
            "model": result.model,
            "operational_state": "REAL_AVAILABLE" if available else "UNAVAILABLE",
        }

    async def _browser(self):
        if importlib.util.find_spec("playwright") is None:
            return {"status": "error", "message": "Playwright is not installed."}
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            candidates = [Path(playwright.chromium.executable_path)]
        for command in ("google-chrome", "chromium", "chrome", "msedge"):
            resolved = shutil.which(command)
            if resolved:
                candidates.append(Path(resolved))
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base:
                candidates.extend(
                    [
                        Path(base) / "Google/Chrome/Application/chrome.exe",
                        Path(base) / "Microsoft/Edge/Application/msedge.exe",
                    ]
                )
        available = any(path.is_file() for path in candidates)
        return {
            "status": "ok" if available else "error",
            "message": "Playwright and a browser executable are installed."
            if available
            else "Browser executable missing; install Playwright Chromium or Chrome.",
        }

    async def _worker(self):
        async with database.get_session() as session:
            rows = (
                (
                    await session.execute(
                        select(WorkerORM).where(
                            WorkerORM.last_heartbeat_at >= utc_now() - timedelta(seconds=90),
                            WorkerORM.status.in_(["ONLINE", "BUSY"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            "status": "ok" if rows else "warning",
            "message": f"{len(rows)} worker(s) with recent heartbeat; local task execution is independent.",
        }

    async def _test_runtime(self):
        available = Path(sys.executable).is_file() and importlib.util.find_spec("pytest") is not None
        return {
            "status": "ok" if available else "error",
            "message": "API Python and pytest are available." if available else "Python test runtime is unavailable.",
        }

    async def _filesystem(self):
        for directory in (settings.workspace_storage_dir, settings.artifact_storage_dir):
            with tempfile.TemporaryFile(dir=directory) as handle:
                handle.write(b"ready")
                handle.flush()
        return {"status": "ok", "message": "Workspace and artifact directories are writable."}

    async def _lsp(self):
        available = importlib.util.find_spec("basedpyright") is not None
        return {
            "status": "ok" if available else "warning",
            "message": "basedpyright is installed." if available else "Python language server is missing.",
        }


platform_health_service = PlatformHealthService()
