"""Bounded readiness checks, with authenticated detail and cached optional-provider probes."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from app.persistence.models import utc_now
from app.ports.browser_runtime import BrowserRuntime
from app.ports.database_health import DatabaseHealthProbe
from app.ports.repository_scope import RepositoryScopeFactory
from app.services.decision_settings_service import DecisionSettingsService
from app.settings import get_config


class PlatformHealthService:
    _probe_timeouts = {
        "ai": 15,
        "jev": 20,
        "browser": 15,
    }

    def __init__(
        self,
        browser_runtime: BrowserRuntime | None = None,
        repository_scope: RepositoryScopeFactory | None = None,
        database_health_probe: DatabaseHealthProbe | None = None,
    ):
        if browser_runtime is None:
            from app.container import get_browser_runtime

            browser_runtime = get_browser_runtime()
        self.browser_runtime = browser_runtime
        self.repository_scope = repository_scope
        self.database_health_probe = database_health_probe
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
                timeout = self._probe_timeouts.get(name, 6)
                try:
                    value = await asyncio.wait_for(callback(), timeout=timeout)
                except TimeoutError:
                    value = {
                        "status": "warning",
                        "message": f"Health probe did not finish within {timeout}s; availability was not confirmed.",
                        "operational_state": "PROBE_TIMEOUT",
                    }
                except Exception as error:
                    value = {"status": "error", "message": type(error).__name__}
                return {"component": name, **value, "duration_ms": round((time.perf_counter() - started) * 1000, 1)}

            components = await asyncio.gather(
                *[
                    probe("database", self._database),
                    probe("ai", lambda: self._ai(refresh=refresh)),
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
        if self.database_health_probe is None:
            raise RuntimeError("Platform health requires a database health probe")
        return await self.database_health_probe.check()

    async def _ai(self, refresh=False):
        from app.services.ai_settings_service import AISettingsService

        status = await AISettingsService(self.repository_scope).get_status(refresh=refresh)
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
        config = await DecisionSettingsService(self.repository_scope).get_runtime_config()
        if not config.enabled or not config.api_key:
            return {
                "status": "warning",
                "message": "Jev is disabled or its key is missing; local strategy remains available.",
                "operational_state": "UNAVAILABLE",
            }
        # Probe transport and response validity directly. Decision confidence/fallback
        # policy belongs to user decisions and must not turn a reachable Jev endpoint red.
        from project_model.models import DecisionOption, DecisionRequest

        from app.services.jev_provider import DecisionProviderError, JevDecisionProvider

        provider = JevDecisionProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        request = DecisionRequest(
            name="readiness_check",
            state={"probe": True},
            options=[
                DecisionOption(key="ok", description="Confirm service readiness"),
                DecisionOption(key="unavailable", description="Report an unavailable service"),
            ],
        )
        try:
            result = await provider.choose(request)
        except DecisionProviderError as error:
            return {
                "status": "warning",
                "message": f"Jev endpoint probe failed ({error.code}).",
                "operational_state": error.code.upper(),
            }
        return {
            "status": "ok",
            "message": f"Jev returned a valid decision response ({result.choice}).",
            "model": result.model,
            "operational_state": "REAL_AVAILABLE",
        }

    async def _browser(self):
        session = await self.browser_runtime.create_session(launch_options={"timeout": 12_000})
        try:
            version = session.browser_version
        finally:
            await self.browser_runtime.close_session(session.id)
        return {
            "status": "ok",
            "message": f"Playwright launched a browser successfully (version {version}).",
        }

    async def _worker(self):
        if self.repository_scope is None:
            raise RuntimeError("Platform health requires a repository scope")
        async with self.repository_scope() as repositories:
            rows = await repositories.workers.list_recent_active(utc_now() - timedelta(seconds=90))
        return {
            "status": "ok",
            "message": (
                f"{len(rows)} remote worker(s) with recent heartbeat."
                if rows
                else "No remote workers are registered; API-local task execution remains available."
            ),
            "operational_state": "REMOTE_WORKERS_AVAILABLE" if rows else "LOCAL_EXECUTION_AVAILABLE",
            "remote_workers": len(rows),
        }

    async def _test_runtime(self):
        available = Path(sys.executable).is_file() and importlib.util.find_spec("pytest") is not None
        return {
            "status": "ok" if available else "error",
            "message": "API Python and pytest are available." if available else "Python test runtime is unavailable.",
        }

    async def _filesystem(self):
        app_config = get_config().app
        for directory in (app_config.workspace_storage_dir, app_config.artifact_storage_dir):
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
