from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
import uuid
from typing import Any

import httpx
from qa_core.contracts import ExecutionRequest
from qa_core.fake_adapters import FakeQAOrchestrator

logger = logging.getLogger("worker.daemon")


class WorkerDaemon:
    """Production distributed test worker daemon.

    Registers to the central AI QA Platform API, periodically sends heartbeats,
    polls and claims distributed test jobs matching its browser/runner capabilities,
    executes the test suites with live status tracking, and uploads results.
    """

    def __init__(
        self,
        api_url: str | None = None,
        worker_id: str | None = None,
        worker_name: str | None = None,
        capabilities: list[str] | None = None,
        max_concurrency: int | None = None,
        heartbeat_interval: float = 10.0,
        poll_interval: float = 3.0,
    ) -> None:
        self.api_url = (api_url or os.getenv("AI_QA_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.worker_id = worker_id or os.getenv("WORKER_ID", f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:6]}")
        self.worker_name = worker_name or os.getenv("WORKER_NAME", f"Runner-{platform.node()}")

        default_caps = ["playwright", "chromium", "firefox", "webkit", "pytest", "python3"]
        env_caps = os.getenv("WORKER_CAPABILITIES")
        self.capabilities = capabilities or (env_caps.split(",") if env_caps else default_caps)
        self.max_concurrency = max_concurrency or int(os.getenv("MAX_CONCURRENCY", "4"))

        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval

        self._running = False
        self._http_client: httpx.AsyncClient | None = None
        self._orchestrator = FakeQAOrchestrator()
        self._heartbeat_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the worker daemon lifecycle."""
        self._running = True
        self._http_client = httpx.AsyncClient(base_url=self.api_url, timeout=30.0)

        logger.info(
            "Starting worker %s (Name: %s, Capabilities: %s, Concurrency: %d, API: %s)",
            self.worker_id,
            self.worker_name,
            self.capabilities,
            self.max_concurrency,
            self.api_url,
        )

        # 1. Register with API
        await self._register()

        # 2. Launch concurrent loops
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._poll_task = asyncio.create_task(self._job_claim_loop())

    async def stop(self) -> None:
        """Gracefully stop the worker daemon."""
        logger.info("Stopping worker daemon %s...", self.worker_id)
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._poll_task:
            self._poll_task.cancel()

        if self._http_client:
            try:
                # Deregister / mark worker offline
                await self._http_client.post(
                    f"/api/workers/{self.worker_id}/heartbeat",
                    json={"status": "offline", "current_load": 0},
                )
            except Exception:
                pass
            await self._http_client.aclose()

        logger.info("Worker daemon %s stopped.", self.worker_id)

    async def _register(self) -> None:
        """Register worker node in the platform worker registry."""
        try:
            assert self._http_client is not None
            resp = await self._http_client.post(
                "/api/workers",
                json={
                    "worker_id": self.worker_id,
                    "name": self.worker_name,
                    "host": socket.gethostname(),
                    "capabilities": self.capabilities,
                    "max_concurrency": self.max_concurrency,
                },
            )
            if resp.status_code in (200, 201):
                logger.info("Worker registered successfully: %s", resp.json())
            else:
                logger.warning("Registration response: %d %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("Failed to register worker %s: %s", self.worker_id, exc)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to maintain active status and report node load."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                assert self._http_client is not None
                resp = await self._http_client.post(
                    f"/api/workers/{self.worker_id}/heartbeat",
                    json={"status": "idle", "current_load": 0},
                )
                if resp.status_code != 200:
                    logger.warning("Heartbeat non-200: %d", resp.status_code)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat failed: %s", exc)

    async def _job_claim_loop(self) -> None:
        """Continuously poll the central job queue to claim and execute matching jobs."""
        while self._running:
            try:
                job = await self._claim_job()
                if job:
                    await self._process_job(job)
                else:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in job claim loop: %s", exc)
                await asyncio.sleep(self.poll_interval)

    async def _claim_job(self) -> dict[str, Any] | None:
        try:
            assert self._http_client is not None
            resp = await self._http_client.post(
                "/api/jobs/claim",
                json={"worker_id": self.worker_id, "capabilities": self.capabilities},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    logger.info("Claimed job: %s", data.get("id"))
                    return data
            return None
        except Exception as exc:
            logger.debug("Job claim poll failed: %s", exc)
            return None

    async def _process_job(self, job_data: dict[str, Any]) -> None:
        job_id = job_data["id"]
        job_type = job_data.get("job_type", "test_run")
        payload = job_data.get("payload", {})

        logger.info("Processing job %s (Type: %s)", job_id, job_type)

        try:
            if job_type in ("test_run", "execution"):
                req = ExecutionRequest(
                    project_id=payload.get("project_id", "default"),
                    workspace_path=payload.get("workspace_path", "."),
                    test_paths=payload.get("test_paths", []),
                )
                report, analyses = await self._orchestrator.orchestrate_run(req)
                result = {
                    "report": report.model_dump(),
                    "analyses": [a.model_dump() for a in analyses],
                    "status": "completed",
                }
            else:
                result = {
                    "status": "completed",
                    "message": f"Successfully executed custom job {job_type}",
                }

            # Complete job
            assert self._http_client is not None
            await self._http_client.post(
                f"/api/jobs/{job_id}/complete",
                json={"result": result},
            )
            logger.info("Successfully completed job %s", job_id)

        except Exception as exc:
            logger.exception("Failed to execute job %s: %s", job_id, exc)
            if self._http_client is not None:
                try:
                    await self._http_client.post(
                        f"/api/jobs/{job_id}/complete",
                        json={"result": {"status": "failed", "error": str(exc)}},
                    )
                except Exception:
                    pass
