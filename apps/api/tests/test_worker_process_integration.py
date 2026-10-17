"""A real local worker process against a real API port.

The worker talks to the API over HTTP only, so the other distributed-execution tests (which call
service methods directly) cannot prove that a queued job actually becomes a pytest run. This module
boots the FastAPI app on a free port, starts ``python -m worker.main`` as a subprocess and reads the
persisted run/job rows afterwards: claim, persist, cancel, timeout kill and crash recovery.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import uvicorn
from app.main import app
from app.persistence.models import utc_now
from app.services.workspace_service import WorkspaceService
from app.settings import settings
from conftest import ROLE_CREDENTIALS, login_token
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.integration

#: Every verdict a run can settle on; QUEUED/RUNNING are the only in-flight states.
TERMINAL = {"PASSED", "FAILED", "SKIPPED", "ERROR", "CANCELLED"}

REPO_ROOT = Path(__file__).resolve().parents[3]

PASSING_TEST = "def test_worker_live_ok():\n    assert True\n"
SLOW_TEST = "import time\n\n\ndef test_worker_live_slow():\n    time.sleep(120)\n"


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_http(url: str, timeout: float = 30.0) -> None:
    async with AsyncClient() as probe:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                await probe.get(url, timeout=1.0)
                return
            except Exception:  # noqa: BLE001 - the server is still binding
                await asyncio.sleep(0.1)
    raise AssertionError(f"API did not become reachable at {url}")


@dataclass
class LiveApi:
    port: int
    workspace_dir: Path
    artifact_dir: Path

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest_asyncio.fixture
async def live_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Serve the real app on a port so the worker subprocess can reach it over HTTP."""
    workspace_dir = tmp_path / "workspaces"
    artifact_dir = tmp_path / "artifacts"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace_storage_dir", workspace_dir)
    monkeypatch.setattr(settings, "artifact_storage_dir", artifact_dir)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="error"))
    serve_task = asyncio.create_task(server.serve())
    await _wait_for_http(f"http://127.0.0.1:{port}/api/health/live")
    try:
        yield LiveApi(port=port, workspace_dir=workspace_dir, artifact_dir=artifact_dir)
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve_task, timeout=15)


class WorkerProcess:
    """`python -m worker.main` running against the live API, killable as a process group."""

    def __init__(self, process: subprocess.Popen[bytes], log_path: Path) -> None:
        self.process = process
        self.log_path = log_path

    @classmethod
    def start(cls, api: LiveApi, log_path: Path, token: str, **extra_env: str) -> "WorkerProcess":
        env = {
            **os.environ,
            "AI_QA_API_URL": api.url,
            "AI_QA_AUTH_TOKEN": token,
            "WORKER_NAME": f"Live-Test-{os.getpid()}",
            "AI_QA_WORKER_WORKSPACE_DIR": str(api.workspace_dir),
            "AI_QA_WORKER_ARTIFACT_DIR": str(api.artifact_dir),
            **extra_env,
        }
        log = log_path.open("wb")
        process = subprocess.Popen(  # noqa: S603 - fixed argv, this repository's own module
            [sys.executable, "-m", "worker.main"],
            cwd=REPO_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        return cls(process, log_path)

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        if os.name == "posix":
            os.killpg(self.process.pid, signal.SIGTERM)
        else:
            self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self.kill()

    def kill(self) -> None:
        """Simulate a crash: no chance to report or clean up."""
        if os.name == "posix":
            os.killpg(self.process.pid, signal.SIGKILL)
        else:
            self.process.kill()
        self.process.wait(timeout=15)

    def log(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace")


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    email, password = ROLE_CREDENTIALS["ADMIN"]
    return await login_token(client, email, password)


@pytest_asyncio.fixture
async def worker_factory(live_api: LiveApi, tmp_path: Path, admin_token: str):
    started: list[WorkerProcess] = []

    def start(**extra_env: str) -> WorkerProcess:
        worker = WorkerProcess.start(live_api, tmp_path / "worker.log", admin_token, **extra_env)
        started.append(worker)
        return worker

    try:
        yield start
    finally:
        for worker in started:
            worker.stop()


async def _create_project_with_files(client: AsyncClient, files: dict[str, str]) -> str:
    project = (await client.post("/api/projects", json={"name": f"Worker live {time.time_ns()}"})).json()
    workspace = WorkspaceService()
    for relative_path, content in files.items():
        await workspace.write_file(project["id"], relative_path, content)
    return project["id"]


async def _create_worker_run(client: AsyncClient, project_id: str, nodeid: str) -> dict[str, Any]:
    response = await client.post(
        "/api/runs",
        json={
            "project_id": project_id,
            "workspace_id": project_id,
            "nodeids": [nodeid],
            "runner_type": "WORKER",
            "browser": "chromium",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _wait_for_run(client: AsyncClient, run_id: str, statuses: set[str], timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in statuses:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"run {run_id} stayed in {last.get('status')}; log:\n{last.get('log_output')}")


async def _wait_for_job_status(
    client: AsyncClient, run_id: str, statuses: set[str], timeout: float = 90.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        jobs = (await client.get("/api/jobs", params={"run_id": run_id})).json()
        assert jobs, f"run {run_id} has no queued job"
        last = jobs[0]
        if last["status"] in statuses:
            return last
        await asyncio.sleep(0.25)
    raise AssertionError(f"job for run {run_id} stayed in {last.get('status')}")


@pytest.mark.asyncio
async def test_worker_process_executes_a_queued_run_and_persists_the_result(
    client: AsyncClient, live_api: LiveApi, worker_factory
) -> None:
    project_id = await _create_project_with_files(client, {"tests/test_worker_live_ok.py": PASSING_TEST})
    run = await _create_worker_run(client, project_id, "tests/test_worker_live_ok.py::test_worker_live_ok")
    # QUEUED with no worker: the run must not execute locally just because the API can.
    assert run["runner_type"] == "WORKER"

    worker = worker_factory()
    finished = await _wait_for_run(client, run["id"], TERMINAL)
    assert finished["status"] == "PASSED", (finished.get("log_output"), worker.log())
    assert (finished["total"], finished["passed"], finished["failed"]) == (1, 1, 0)
    assert [execution["status"] for execution in finished["executions"]] == ["PASSED"]
    assert finished["executions"][0]["nodeid"] == "tests/test_worker_live_ok.py::test_worker_live_ok"
    assert "1 passed" in (finished["log_output"] or ""), worker.log()

    job = await _wait_for_job_status(client, run["id"], {"COMPLETED"})
    assert job["status"] == "COMPLETED"
    assert job["duration_ms"] > 0

    # The same job submitted twice must not execute (or persist) the suite a second time.
    duplicate = await client.post(
        f"/api/jobs/{job['id']}/result",
        json={"worker_id": job["assigned_worker_id"], "result": {"exit_code": 0, "total": 1, "passed": 1}},
    )
    assert duplicate.status_code in {200, 409}, duplicate.text
    replay = await _wait_for_run(client, run["id"], {"PASSED"})
    assert (replay["total"], replay["passed"]) == (1, 1)
    assert len(replay["executions"]) == 1

    worker.stop()
    assert worker.process.returncode is not None
    # The per-job temporary live-browser directory is removed when the job finishes.
    leftover = list((live_api.artifact_dir / run["id"]).glob(".qa-live-*"))
    assert leftover == [], leftover


@pytest.mark.asyncio
async def test_cancelling_the_job_stops_the_running_worker_and_frees_the_slot(
    client: AsyncClient, live_api: LiveApi, worker_factory
) -> None:
    project_id = await _create_project_with_files(
        client,
        {"tests/test_worker_live_slow.py": SLOW_TEST, "tests/test_worker_live_ok.py": PASSING_TEST},
    )
    slow = await _create_worker_run(client, project_id, "tests/test_worker_live_slow.py::test_worker_live_slow")
    worker = worker_factory()
    running = await _wait_for_job_status(client, slow["id"], {"ASSIGNED", "RUNNING"})
    await _wait_for_run(client, slow["id"], {"RUNNING"})

    cancelled = await client.post(f"/api/jobs/{running['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    stopped = await _wait_for_run(client, slow["id"], {"CANCELLED"}, timeout=30.0)
    assert stopped["status"] == "CANCELLED"

    # The worker is still alive and its concurrency slot is free: a second run executes normally.
    follow_up = await _create_worker_run(client, project_id, "tests/test_worker_live_ok.py::test_worker_live_ok")
    done = await _wait_for_run(client, follow_up["id"], TERMINAL)
    assert done["status"] == "PASSED", (done.get("log_output"), worker.log())
    assert worker.process.poll() is None


@pytest.mark.asyncio
async def test_pytest_timeout_kills_the_run_instead_of_hanging(
    client: AsyncClient, live_api: LiveApi, worker_factory
) -> None:
    project_id = await _create_project_with_files(client, {"tests/test_worker_live_slow.py": SLOW_TEST})
    run = await _create_worker_run(client, project_id, "tests/test_worker_live_slow.py::test_worker_live_slow")
    worker = worker_factory(AI_QA_PYTEST_TIMEOUT_SECONDS="5")

    finished = await _wait_for_run(client, run["id"], TERMINAL, timeout=90.0)
    assert finished["status"] in {"FAILED", "ERROR", "CANCELLED"}, finished
    assert finished["finished_at"] is not None
    combined = f"{finished.get('log_output') or ''}\n{worker.log()}"
    assert "timed out" in combined.lower(), combined[-2000:]
    # The worker survived the kill and released its slot.
    assert worker.process.poll() is None


@pytest.mark.asyncio
async def test_crashed_worker_run_is_recovered_instead_of_staying_running(
    client: AsyncClient, live_api: LiveApi, worker_factory, test_db_session
) -> None:
    project_id = await _create_project_with_files(client, {"tests/test_worker_live_slow.py": SLOW_TEST})
    run = await _create_worker_run(client, project_id, "tests/test_worker_live_slow.py::test_worker_live_slow")
    worker = worker_factory()
    await _wait_for_job_status(client, run["id"], {"ASSIGNED", "RUNNING"})
    await _wait_for_run(client, run["id"], {"RUNNING"})

    worker.kill()
    # Without recovery the run would stay RUNNING forever, blocking the UI and the project.
    abandoned = await _wait_for_run(client, run["id"], {"RUNNING"})
    assert abandoned["status"] == "RUNNING"

    # Age the dead worker's last heartbeat instead of waiting out the 10 minute offline window; the
    # recovery query must not touch jobs of a worker that is still heartbeating.
    async with test_db_session() as session:
        aged = utc_now() - timedelta(hours=1)  # a real datetime: PostgreSQL rejects a string here
        await session.execute(text("UPDATE workers SET last_heartbeat_at = :past"), {"past": aged})
        await session.execute(
            text("UPDATE execution_jobs SET updated_at = :past WHERE run_id = :run_id"),
            {"past": aged, "run_id": run["id"]},
        )
        await session.execute(
            text("UPDATE test_runs SET started_at = :past WHERE id = :run_id"),
            {"past": aged, "run_id": run["id"]},
        )
        await session.commit()
    recovered = await client.post("/api/runs/recover-stale", params={"stale_after_seconds": 60})
    assert recovered.status_code == 200, recovered.text
    assert run["id"] in recovered.json()["recovered_run_ids"]
    closed = await _wait_for_run(client, run["id"], {"CANCELLED", "FAILED", "ERROR"})
    assert closed["status"] == "CANCELLED"
    job = await _wait_for_job_status(client, run["id"], {"CANCELLED", "FAILED"})
    assert job["status"] == "CANCELLED"
