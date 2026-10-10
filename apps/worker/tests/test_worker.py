from __future__ import annotations

import asyncio

import pytest
from worker.daemon import WorkerDaemon


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_observes_durable_job_cancellation():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "CANCELLED"}

    class Client:
        @staticmethod
        async def get(_url: str):
            return Response()

    daemon = WorkerDaemon()
    daemon._http_client = Client()  # type: ignore[assignment]

    assert await daemon._watch_job_cancellation("job-cancelled") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_claim_loop_runs_jobs_up_to_configured_capacity(monkeypatch):
    daemon = WorkerDaemon(max_concurrency=2, poll_interval=0.001)
    daemon._running = True
    next_job = 0
    active = 0
    peak_active = 0
    completed = 0
    two_started = asyncio.Event()
    release_jobs = asyncio.Event()

    async def claim_job():
        nonlocal next_job
        if next_job >= 3:
            return None
        next_job += 1
        return {"id": f"job-{next_job}", "browser": "chromium"}

    async def process_job(_job):
        nonlocal active, peak_active, completed
        active += 1
        peak_active = max(peak_active, active)
        if active == 2:
            two_started.set()
        try:
            await release_jobs.wait()
        finally:
            active -= 1
            completed += 1

    monkeypatch.setattr(daemon, "_claim_job", claim_job)
    monkeypatch.setattr(daemon, "_process_job", process_job)
    loop = asyncio.create_task(daemon._job_claim_loop())
    try:
        await asyncio.wait_for(two_started.wait(), timeout=1)
        assert next_job == 2
        assert len(daemon._running_jobs) == 2

        release_jobs.set()
        async with asyncio.timeout(1):
            while completed < 3:
                await asyncio.sleep(0.001)
        assert peak_active == 2
        assert next_job == 3
    finally:
        daemon._running = False
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_claim_requests_only_declared_browser_engines():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "job-firefox", "browser": "firefox"}

    class Client:
        request = None

        async def post(self, path, *, json):
            self.request = (path, json)
            return Response()

    daemon = WorkerDaemon(capabilities=["pytest", "firefox", "chromium", "python3"])
    client = Client()
    daemon._http_client = client  # type: ignore[assignment]

    job = await daemon._claim_job()

    assert job == {"id": "job-firefox", "browser": "firefox"}
    assert client.request == (
        "/api/jobs/claim",
        {"worker_id": daemon.worker_id, "browsers": ["firefox", "chromium"]},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_fails_closed_when_worker_registration_is_rejected(monkeypatch):
    class Response:
        status_code = 401

    class Client:
        closed = False

        async def post(self, *_args, **_kwargs):
            return Response()

        async def aclose(self):
            self.closed = True

    daemon = WorkerDaemon()
    client = Client()
    monkeypatch.setattr("worker.daemon.httpx.AsyncClient", lambda **_kwargs: client)

    with pytest.raises(RuntimeError, match="registration failed with HTTP 401"):
        await daemon.start()

    assert client.closed
    assert daemon._http_client is None
    assert daemon._running is False
    assert daemon._heartbeat_task is None
    assert daemon._poll_task is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stop_joins_all_background_and_job_tasks_before_closing_client():
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

    class Client:
        closed = False
        offline = False

        async def post(self, path, *, json):
            if path.endswith("/heartbeat") and json["status"] == "OFFLINE":
                self.offline = True
            return Response()

        async def aclose(self):
            self.closed = True

    daemon = WorkerDaemon()
    client = Client()
    daemon._http_client = client  # type: ignore[assignment]
    daemon._running = True
    gate = asyncio.Event()
    daemon._heartbeat_task = asyncio.create_task(gate.wait())
    daemon._poll_task = asyncio.create_task(gate.wait())
    daemon._job_tasks["job-active"] = asyncio.create_task(gate.wait())
    daemon._running_jobs.add("job-active")

    await daemon.stop()

    assert daemon._heartbeat_task is None
    assert daemon._poll_task is None
    assert not daemon._job_tasks
    assert not daemon._running_jobs
    assert client.offline and client.closed
    assert daemon._http_client is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancelled_job_reports_interruption_and_cancels_pytest(tmp_path, monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, data=None):
            self.data = data or {}

        def json(self):
            return self.data

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self):
            self.posts = []

        async def get(self, path):
            if path == "/api/runs/run-1":
                return Response({"markers": [], "environment": {}})
            return Response({"status": "RUNNING"})

        async def post(self, path, *, json):
            self.posts.append((path, json))
            return Response()

    daemon = WorkerDaemon()
    worker_config = daemon.config.worker.model_copy(
        update={
            "workspace_storage_dir": tmp_path / "workspaces",
            "artifact_storage_dir": tmp_path / "artifacts",
        }
    )
    daemon.config = daemon.config.model_copy(update={"worker": worker_config})
    (tmp_path / "workspaces" / "project-1").mkdir(parents=True)
    client = Client()
    daemon._http_client = client  # type: ignore[assignment]
    runner_started = asyncio.Event()
    runner_cancelled = asyncio.Event()

    async def wait_for_cancel(**_kwargs):
        runner_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            runner_cancelled.set()

    monkeypatch.setattr(daemon._runner, "run_suite", wait_for_cancel)
    job = {
        "id": "job-1",
        "run_id": "run-1",
        "workspace_id": "project-1",
        "nodeids": ["tests/test_example.py::test_example"],
        "browser": "firefox",
    }
    task = asyncio.create_task(daemon._process_job(job))
    await asyncio.wait_for(runner_started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runner_cancelled.is_set()
    assert (
        "/api/jobs/job-1/fail",
        {"worker_id": daemon.worker_id, "error_message": "Worker shut down before the job completed."},
    ) in client.posts
    assert not any(path.endswith("/result") for path, _ in client.posts)
