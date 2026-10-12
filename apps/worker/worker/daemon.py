from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from platform_config import AppConfig, ConfigManager
from qa_core.execution.failure_snapshot import capture_failure_snapshot_event
from qa_core.execution.live_browser_plugin import write_live_browser_plugin
from qa_core.execution.pytest_runner import PytestRunner
from qa_core.failure.snapshot_crypto import FailureSnapshotCipher
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
        heartbeat_interval: float | None = None,
        poll_interval: float | None = None,
    ) -> None:
        self.config_manager = ConfigManager()
        self.config: AppConfig = self.config_manager.get()
        worker_config = self.config.worker
        self.api_url = (api_url or worker_config.api_url).rstrip("/")
        self.worker_id = worker_id or os.getenv("WORKER_ID", f"worker-{socket.gethostname()}-{uuid.uuid4().hex[:6]}")
        self.worker_name = worker_name or worker_config.name or f"Runner-{platform.node()}"

        self.capabilities = list(worker_config.capabilities if capabilities is None else capabilities)
        configured_projects = os.getenv("WORKER_PROJECT_IDS")
        self.project_ids = (
            list(dict.fromkeys(item.strip() for item in configured_projects.split(",") if item.strip()))
            if configured_projects is not None
            else None
        )
        self.browser_capabilities = [
            capability for capability in self.capabilities if capability in {"chromium", "firefox", "webkit"}
        ]
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else min(worker_config.max_concurrency, self.config.run.max_parallel_runs)
        )
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        self.heartbeat_interval = (
            heartbeat_interval if heartbeat_interval is not None else worker_config.heartbeat_interval_seconds
        )
        self.poll_interval = poll_interval if poll_interval is not None else worker_config.poll_interval_seconds

        self._running = False
        self._running_jobs: set[str] = set()
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._runner = PytestRunner(default_timeout_sec=self.config.pytest.timeout_seconds)
        self._heartbeat_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Register this worker before starting its heartbeat and bounded claim loop."""
        if self._running:
            return
        if self._http_client is not None:
            raise RuntimeError("Worker HTTP client is already open")
        headers: dict[str, str] = {}
        token = self.config.worker.auth_token.get_secret_value().strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                "AI_QA_AUTH_TOKEN is not set: the API rejects worker requests with 401 unless "
                "AUTH_REQUIRED=false. Create an API key (Security -> API Keys) and export it."
            )
        self._http_client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=self.config.worker.http_timeout_seconds,
            headers=headers,
        )

        logger.info(
            "Starting worker %s (Name: %s, Capabilities: %s, Concurrency: %d, API: %s)",
            self.worker_id,
            self.worker_name,
            self.capabilities,
            self.max_concurrency,
            self.api_url,
        )

        try:
            await self._register()
        except Exception:
            client, self._http_client = self._http_client, None
            if client is not None:
                await client.aclose()
            raise

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"worker-heartbeat-{self.worker_id}")
        self._poll_task = asyncio.create_task(self._job_claim_loop(), name=f"worker-poll-{self.worker_id}")

    async def stop(self) -> None:
        """Stop claiming work, cancel active subprocesses, then mark offline and close HTTP."""
        if not self._running and self._http_client is None:
            return
        logger.info("Stopping worker daemon %s...", self.worker_id)
        self._running = False

        loop_tasks = [task for task in (self._heartbeat_task, self._poll_task) if task is not None]
        for task in loop_tasks:
            task.cancel()
        if loop_tasks:
            await asyncio.gather(*loop_tasks, return_exceptions=True)
        self._heartbeat_task = None
        self._poll_task = None

        job_tasks = list(self._job_tasks.values())
        for task in job_tasks:
            task.cancel()
        if job_tasks:
            await asyncio.gather(*job_tasks, return_exceptions=True)
        self._job_tasks.clear()
        self._running_jobs.clear()

        client, self._http_client = self._http_client, None
        if client:
            try:
                await client.post(
                    f"/api/workers/{self.worker_id}/heartbeat",
                    json={"status": "OFFLINE", "current_load": 0},
                )
            except Exception as exc:
                logger.warning("Could not mark worker %s offline: %s", self.worker_id, exc)
            await client.aclose()
        logger.info("Worker daemon %s stopped.", self.worker_id)

    def _local_ip(self) -> str:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"

    async def _register(self) -> None:
        """Register only actual browser engines; fail startup if the API rejects registration."""
        assert self._http_client is not None
        response = await self._http_client.post(
            "/api/workers",
            json={
                "hostname": self.worker_name,
                "ip_address": self._local_ip(),
                "browsers": self.browser_capabilities,
                "os": platform.system().lower(),
                "max_concurrency": self.max_concurrency,
                "tags": [f"worker_id:{self.worker_id}", *[f"capability:{item}" for item in self.capabilities]],
            },
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Worker registration failed with HTTP {response.status_code}")
        data = response.json()
        registered_id = data.get("id")
        if not isinstance(registered_id, str) or not registered_id:
            raise RuntimeError("Worker registration response did not contain an ID")
        self.worker_id = registered_id
        logger.info("Worker registered successfully: %s", self.worker_id)

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
        """Continuously claim work while enforcing the advertised per-process capacity."""
        while self._running:
            try:
                for job_id, task in list(self._job_tasks.items()):
                    if not task.done():
                        continue
                    self._job_tasks.pop(job_id, None)
                    if not task.cancelled() and (error := task.exception()) is not None:
                        logger.error("Worker job task %s exited unexpectedly: %s", job_id, error)

                if len(self._job_tasks) >= self.max_concurrency:
                    await asyncio.wait(
                        self._job_tasks.values(),
                        timeout=self.poll_interval,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue

                job = await self._claim_job()
                if job:
                    job_id = str(job["id"])
                    if job_id in self._job_tasks:
                        logger.error("API returned already-active job %s; refusing duplicate execution", job_id)
                        await asyncio.sleep(self.poll_interval)
                        continue
                    self._running_jobs.add(job_id)
                    task = asyncio.create_task(self._run_claimed_job(job), name=f"worker-job-{job_id}")
                    self._job_tasks[job_id] = task
                else:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in job claim loop")
                await asyncio.sleep(self.poll_interval)

    async def _run_claimed_job(self, job: dict[str, Any]) -> None:
        job_id = str(job["id"])
        try:
            await self._process_job(job)
        finally:
            self._running_jobs.discard(job_id)

    async def _claim_job(self) -> dict[str, Any] | None:
        if not self.browser_capabilities:
            logger.warning("Worker has no supported browser capability; no jobs can be claimed")
            return None
        try:
            assert self._http_client is not None
            response = await self._http_client.post(
                "/api/jobs/claim",
                json={
                    "worker_id": self.worker_id,
                    "browsers": self.browser_capabilities,
                    **({"project_ids": self.project_ids} if self.project_ids is not None else {}),
                },
            )
            if response.status_code == 200:
                data = response.json()
                if data:
                    browser = data.get("browser")
                    if browser not in self.browser_capabilities:
                        logger.error("API assigned job %s outside declared browser capabilities", data.get("id"))
                        try:
                            failed = await self._http_client.post(
                                f"/api/jobs/{data['id']}/fail",
                                json={
                                    "worker_id": self.worker_id,
                                    "error_message": "API assigned a job outside the worker's declared browser capabilities.",
                                },
                            )
                            failed.raise_for_status()
                        except Exception as error:
                            logger.warning("Could not return incompatible job %s: %s", data.get("id"), error)
                        return None
                    logger.info("Claimed job: %s (%s)", data.get("id"), browser)
                    return data
            elif response.status_code not in (204,):
                logger.warning("Job claim returned HTTP %d", response.status_code)
            return None
        except asyncio.CancelledError:
            raise
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
            workspace_root = self.config.worker.workspace_storage_dir.resolve()
            workspace_dir = (workspace_root / job_data["workspace_id"]).resolve()
            if not workspace_dir.is_relative_to(workspace_root):
                raise ValueError("Invalid workspace ID")
            project_interpreter = venv_interpreter(workspace_dir / ".qa-platform-runtime")
            artifact_root = self.config.worker.artifact_storage_dir.resolve()
            artifact_dir = artifact_root / job_data["run_id"]
            artifact_dir.mkdir(parents=True, exist_ok=True)

            async def send_log(chunk: str) -> None:
                assert self._http_client is not None
                response = await self._http_client.post(
                    f"/api/jobs/{job_id}/log", json={"worker_id": self.worker_id, "log": chunk}
                )
                response.raise_for_status()

            snapshot_key = FailureSnapshotCipher.generate_ephemeral_key()
            failure_snapshots = []

            async def on_browser_event(event: dict[str, Any]) -> None:
                capture = capture_failure_snapshot_event(
                    event,
                    ephemeral_key=snapshot_key,
                    master_key=self.config.app.secret_key.get_secret_value(),
                )
                if capture is not None:
                    failure_snapshots.append(capture)

            live_dir_runtime = tempfile.TemporaryDirectory(prefix=".qa-live-", dir=artifact_dir)
            live_dir = Path(live_dir_runtime.name)
            live_browser_log = live_dir / "browser-live"
            live_plugin = write_live_browser_plugin(live_dir) if self.config.features.live_browser else None
            env = {
                **run["environment"],
                "QA_ARTIFACT_DIR": str(artifact_dir),
                "QA_BROWSER": str(job_data.get("browser", "chromium")),
                "QA_FAILURE_SNAPSHOT_ENCRYPTION_KEY": snapshot_key,
                "QA_FAILURE_SNAPSHOT_TTL_SECONDS": str(self.config.failure.storage_state_ttl_seconds),
                "QA_CAPTURE_SCREENSHOT": str(int(self.config.failure.capture_screenshot)),
                "QA_CAPTURE_DOM": str(int(self.config.failure.capture_dom)),
                "QA_CAPTURE_CONSOLE": str(int(self.config.failure.capture_console)),
                "QA_CAPTURE_NETWORK": str(int(self.config.failure.capture_network)),
                "QA_EVIDENCE_MAX_CONSOLE_ENTRIES": str(self.config.evidence.max_console_entries),
                "QA_EVIDENCE_MAX_NETWORK_ENTRIES": str(self.config.evidence.max_network_entries),
                "QA_EVIDENCE_MAX_DOM_CHARS": str(self.config.evidence.max_dom_chars),
                "PYTHONPATH": os.pathsep.join(
                    value
                    for value in (
                        str(live_dir) if live_plugin else "",
                        run["environment"].get("PYTHONPATH", ""),
                        os.environ.get("PYTHONPATH", ""),
                    )
                    if value
                ),
                **({"QA_PLATFORM_LIVE_BROWSER_LOG": str(live_browser_log)} if live_plugin else {}),
            }
            try:
                runner_task = asyncio.create_task(
                    self._runner.run_suite(
                        workspace_dir=workspace_dir,
                        nodeids=job_data["nodeids"],
                        markers=run["markers"],
                        environment=env,
                        interpreter=str(project_interpreter) if project_interpreter.exists() else sys.executable,
                        on_log=send_log,
                        browser_event_path=live_browser_log if live_plugin else None,
                        on_browser_event=on_browser_event if live_plugin else None,
                        extra_pytest_args=[
                            *self.config.pytest.default_args,
                            *(["-p", live_plugin] if live_plugin else []),
                        ],
                        parallel_workers=self.config.pytest.workers,
                        timeout_sec=self.config.pytest.timeout_seconds,
                    )
                )
            except BaseException:
                live_dir_runtime.cleanup()
                raise
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
                live_dir_runtime.cleanup()

            result.failure_snapshots = failure_snapshots
            result.artifact_paths = [str(path) for path in artifact_dir.rglob("*") if path.is_file()]
            response = await self._http_client.post(
                f"/api/jobs/{job_id}/result",
                json={"worker_id": self.worker_id, "result": result.model_dump(mode="json")},
            )
            response.raise_for_status()
            logger.info("Successfully completed job %s", job_id)

        except asyncio.CancelledError:
            logger.info("Worker is shutting down while processing job %s", job_id)
            if self._http_client is not None:
                try:
                    response = await self._http_client.post(
                        f"/api/jobs/{job_id}/fail",
                        json={
                            "worker_id": self.worker_id,
                            "error_message": "Worker shut down before the job completed.",
                        },
                    )
                    response.raise_for_status()
                except Exception as exc:
                    logger.warning("Could not report interrupted job %s: %s", job_id, exc)
            raise
        except Exception as exc:
            logger.exception("Failed to execute job %s: %s", job_id, exc)
            if self._http_client is not None:
                try:
                    response = await self._http_client.post(
                        f"/api/jobs/{job_id}/fail",
                        json={"worker_id": self.worker_id, "error_message": str(exc)},
                    )
                    response.raise_for_status()
                except Exception as report_error:
                    logger.warning("Could not report job failure %s: %s", job_id, report_error)

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
