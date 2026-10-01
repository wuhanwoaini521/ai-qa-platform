from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.onboarding.contract import venv_interpreter

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
        self._running_jobs: set[str] = set()
        self._http_client: httpx.AsyncClient | None = None
        self._runner = PytestRunner()
        self._heartbeat_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the worker daemon lifecycle."""
        self._running = True
        headers: dict[str, str] = {}
        token = os.getenv("AI_QA_AUTH_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                "AI_QA_AUTH_TOKEN is not set: the API rejects worker requests with 401 unless "
                "AUTH_REQUIRED=false. Create an API key (Security -> API Keys) and export it."
            )
        self._http_client = httpx.AsyncClient(base_url=self.api_url, timeout=30.0, headers=headers)

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
                    json={"status": "OFFLINE", "current_load": 0},
                )
            except Exception:
                pass
            await self._http_client.aclose()

        logger.info("Worker daemon %s stopped.", self.worker_id)

    def _local_ip(self) -> str:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"

    async def _register(self) -> None:
        """Register worker node in the platform worker registry."""
        try:
            assert self._http_client is not None
            resp = await self._http_client.post(
                "/api/workers",
                json={
                    "hostname": self.worker_name,
                    "ip_address": self._local_ip(),
                    # The API matches jobs by browser, so runner capabilities are reported as browsers.
                    "browsers": self.capabilities,
                    "os": platform.system().lower(),
                    "max_concurrency": self.max_concurrency,
                    "tags": [f"worker_id:{self.worker_id}"],
                },
            )
            if resp.status_code in (200, 201):
                self.worker_id = resp.json()["id"]
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
                jobs_running = len(self._running_jobs)
                resp = await self._http_client.post(
                    f"/api/workers/{self.worker_id}/heartbeat",
                    json={
                        "status": "BUSY" if jobs_running else "ONLINE",
                        "current_load": jobs_running,
                    },
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
                    self._running_jobs.add(job["id"])
                    try:
                        await self._process_job(job)
                    finally:
                        self._running_jobs.discard(job["id"])
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
                json={"worker_id": self.worker_id, "browser": "chromium"},
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
        logger.info("Processing job %s (Run: %s)", job_id, job_data["run_id"])

        try:
            assert self._http_client is not None
            run_response = await self._http_client.get(f"/api/runs/{job_data['run_id']}")
            run_response.raise_for_status()
            run = run_response.json()
            workspace_root = Path(os.getenv("WORKSPACE_STORAGE_DIR", "runtime/workspaces")).resolve()
            workspace_dir = (workspace_root / job_data["workspace_id"]).resolve()
            if not workspace_dir.is_relative_to(workspace_root):
                raise ValueError("Invalid workspace ID")
            project_interpreter = venv_interpreter(workspace_dir / ".qa-platform-runtime")
            artifact_root = Path(os.getenv("ARTIFACT_STORAGE_DIR", "runtime/artifacts")).resolve()
            artifact_dir = artifact_root / job_data["run_id"]
            artifact_dir.mkdir(parents=True, exist_ok=True)

            async def send_log(chunk: str) -> None:
                assert self._http_client is not None
                response = await self._http_client.post(
                    f"/api/jobs/{job_id}/log", json={"worker_id": self.worker_id, "log": chunk}
                )
                response.raise_for_status()

            runner_task = asyncio.create_task(
                self._runner.run_suite(
                    workspace_dir=workspace_dir,
                    nodeids=job_data["nodeids"],
                    markers=run["markers"],
                    environment={**run["environment"], "QA_ARTIFACT_DIR": str(artifact_dir)},
                    interpreter=str(project_interpreter) if project_interpreter.exists() else sys.executable,
                    on_log=send_log,
                )
            )
            cancellation_task = asyncio.create_task(self._watch_job_cancellation(job_id))
            try:
                done, _ = await asyncio.wait(
                    {runner_task, cancellation_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancellation_task in done and cancellation_task.result():
                    runner_task.cancel()
                    await asyncio.gather(runner_task, return_exceptions=True)
                    logger.info("Job %s cancelled by the platform", job_id)
                    return
                result = await runner_task
            finally:
                if not cancellation_task.done():
                    cancellation_task.cancel()
                if not runner_task.done():
                    runner_task.cancel()
                await asyncio.gather(cancellation_task, runner_task, return_exceptions=True)

            result.artifact_paths = [str(path) for path in artifact_dir.rglob("*") if path.is_file()]
            response = await self._http_client.post(
                f"/api/jobs/{job_id}/result",
                json={"worker_id": self.worker_id, "result": result.model_dump(mode="json")},
            )
            response.raise_for_status()
            logger.info("Successfully completed job %s", job_id)

        except asyncio.CancelledError:
            logger.info("Worker is shutting down while processing job %s", job_id)
            return
        except Exception as exc:
            logger.exception("Failed to execute job %s: %s", job_id, exc)
            if self._http_client is not None:
                try:
                    await self._http_client.post(f"/api/jobs/{job_id}/fail", json={"error_message": str(exc)})
                except Exception:
                    pass

    async def _watch_job_cancellation(self, job_id: str) -> bool:
        """Poll the durable job state so an API cancellation stops the local pytest process."""
        assert self._http_client is not None
        while True:
            try:
                response = await self._http_client.get(f"/api/jobs/{job_id}")
                if response.status_code == 200 and response.json().get("status") == "CANCELLED":
                    return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Job cancellation poll failed for %s: %s", job_id, exc)
            await asyncio.sleep(2.0)
