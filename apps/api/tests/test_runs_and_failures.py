import asyncio
import warnings
from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.api.failures import get_failure_service
from app.persistence.models import (
    BreakpointORM,
    BrowserSessionORM,
    FailureRecordORM,
    RunnerProfileORM,
    TestExecutionORM,
    utc_now,
)
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.failure_service import FailureService, _validated_trace_events
from app.services.test_run_service import TestRunService, event_bus
from app.services.workspace_service import WorkspaceService
from httpx import AsyncClient
from project_model.models import RunStatus, TestRunCreate
from qa_core.ai.models import FailureAnalysisResponse
from qa_core.ai.trace import AITraceEvent, make_trace_event
from qa_core.execution.models import SingleTestResult, SuiteExecutionResult, TestExecutionStatus
from qa_core.execution.runner_backend import RunnerStatusResult
from qa_core.healing.models import LocatorRepairProposal
from sqlalchemy import select

pytestmark = pytest.mark.integration


def test_repair_trace_revalidates_serialized_events_before_response_dump():
    event = make_trace_event("run_1", "repair_suggested", stage="repair", title="Repair suggested")
    validated = _validated_trace_events([event.model_dump(mode="json")])
    proposal = LocatorRepairProposal(
        old_locator="#old",
        proposed_locator='[data-testid="new"]',
        strategy="test_id",
        reason="verified",
        execution_trace=validated,
    )

    assert isinstance(proposal.execution_trace[0], AITraceEvent)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        proposal.model_dump(mode="json")
    assert not caught


@pytest.mark.asyncio
async def test_trigger_run_and_failure_flow(client: AsyncClient):
    # 1. Create project with bootstrap workspace
    proj_res = await client.post(
        "/api/projects",
        json={"name": "Execution Demo Suite", "bootstrap_workspace": True},
    )
    proj_id = proj_res.json()["id"]

    # 2. Add an intentional failing test
    await client.put(
        f"/api/workspaces/{proj_id}/file",
        json={
            "path": "tests/test_failing.py",
            "content": """import pytest

def test_intentional_locator_failure():
    raise TimeoutError("TimeoutError: Locator('button#checkout-submit') not found within 5000ms")
""",
        },
    )

    # 3. Trigger test run
    run_res = await client.post(
        "/api/runs",
        json={
            "project_id": proj_id,
            "workspace_id": proj_id,
            "nodeids": ["tests/test_failing.py::test_intentional_locator_failure"],
        },
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    run_id = run_data["id"]

    # 4. Get run details
    get_run = await client.get(f"/api/runs/{run_id}")
    assert get_run.status_code == 200

    # 5. Check failures
    failures_res = await client.get("/api/failures")
    assert failures_res.status_code == 200

    # 6. Test QA Assistant chat
    assistant_res = await client.post(
        "/api/qa-assistant/chat",
        json={
            "action": "explain",
            "context": {
                "project_id": proj_id,
                "requirement_title": "Checkout Verification",
                "current_file": "tests/test_failing.py",
            },
        },
    )
    assert assistant_res.status_code == 200
    assert "explain" in assistant_res.json()["action_type"]


@pytest.mark.integration
async def test_abandoned_runs_are_recovered_and_never_stay_running(client: AsyncClient, test_db_session):
    """A process crash must not leave a run RUNNING forever, and recovery must not invent a verdict."""
    project = await client.post("/api/projects", json={"name": "Stale Run Recovery"})
    project_id = project.json()["id"]

    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        # A run that started long ago and never finished: no background execution to race with.
        run.status = RunStatus.RUNNING.value
        run.created_at = utc_now() - timedelta(minutes=10)
        run.started_at = utc_now() - timedelta(minutes=10)
        await session.commit()
        run_id = run.id

    recent = await client.post("/api/runs/recover-stale", params={"stale_after_seconds": 3600})
    assert recent.status_code == 200, recent.text
    assert run_id not in recent.json()["recovered_run_ids"]

    recovered = await client.post("/api/runs/recover-stale", params={"stale_after_seconds": 60})
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["recovered_run_ids"] == [run_id]

    fetched = await client.get(f"/api/runs/{run_id}")
    # CANCELLED, not FAILED: the platform does not know the outcome and must not invent one.
    assert fetched.json()["status"] == "CANCELLED"
    assert fetched.json()["finished_at"] is not None


@pytest.mark.asyncio
async def test_startup_recovery_commits_local_runs_and_leaves_worker_jobs_for_the_queue(
    client: AsyncClient, test_db_session
):
    from app.main import _recover_stale_runs

    project = await client.post("/api/projects", json={"name": "Startup Recovery Ownership"})
    project_id = project.json()["id"]
    async with test_db_session() as session:
        repo = TestRunRepository(session)
        local = await repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        worker = await repo.create_run(
            TestRunCreate(project_id=project_id, workspace_id=project_id, runner_type="WORKER")
        )
        local.total = 2
        await repo.add_execution(local.id, "tests/test_recovered.py::test_passed", RunStatus.PASSED)
        for run in (local, worker):
            run.status = RunStatus.RUNNING.value
            run.created_at = utc_now() - timedelta(hours=3)
            run.started_at = utc_now() - timedelta(hours=3)
        await session.commit()
        local_id, worker_id = local.id, worker.id

    recovered = await _recover_stale_runs()
    assert local_id in recovered
    assert worker_id not in recovered
    recovered_run = (await client.get(f"/api/runs/{local_id}")).json()
    assert recovered_run["status"] == "CANCELLED"
    assert recovered_run["passed"] == 1
    assert len(recovered_run["executions"]) == 1
    assert (await client.get(f"/api/runs/{worker_id}")).json()["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_cancel_preserves_aggregate_counts_for_results_already_committed(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Partial Cancellation Counts"})).json()
    async with test_db_session() as session:
        repo = TestRunRepository(session)
        run = await repo.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        run.status = RunStatus.RUNNING.value
        run.total = 4
        await repo.add_execution(run.id, "tests/test_x.py::test_pass", RunStatus.PASSED)
        await repo.add_execution(run.id, "tests/test_x.py::test_fail", RunStatus.FAILED)
        await repo.add_execution(run.id, "tests/test_x.py::test_skip", RunStatus.SKIPPED)
        await session.commit()
        run_id = run.id

    response = await client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert (response.json()["passed"], response.json()["failed"], response.json()["skipped"]) == (1, 1, 1)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_cancel_counts_results_committed_while_it_waits_for_run_lock(
    client: AsyncClient, test_db_session
):
    project = (await client.post("/api/projects", json={"name": "Postgres Cancel Result Race"})).json()
    async with test_db_session() as session:
        repo = TestRunRepository(session)
        run = await repo.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        run.status = RunStatus.RUNNING.value
        await session.commit()
        run_id = run.id

    writer_ready = asyncio.Event()
    allow_writer_commit = asyncio.Event()

    async def persist_result():
        async with test_db_session() as writer_session:
            repo = TestRunRepository(writer_session)
            assert await repo.reserve_active_run_for_result(run_id)
            await repo.add_execution(run_id, "tests/test_lock.py::test_pass", RunStatus.PASSED)
            writer_ready.set()
            await allow_writer_commit.wait()
            await writer_session.commit()

    writer = asyncio.create_task(persist_result())
    await asyncio.wait_for(writer_ready.wait(), timeout=3)

    async with test_db_session() as cancel_session:
        repo = TestRunRepository(cancel_session)
        cancellation = asyncio.create_task(repo.cancel_active_run(run_id, utc_now()))
        await asyncio.sleep(0.05)
        assert not cancellation.done(), "cancellation should wait for the result transaction's run lock"
        allow_writer_commit.set()
        assert await asyncio.wait_for(cancellation, timeout=3)
        await cancel_session.commit()
    await asyncio.wait_for(writer, timeout=3)

    final = (await client.get(f"/api/runs/{run_id}")).json()
    assert final["status"] == "CANCELLED"
    assert final["passed"] == 1
    assert len(final["executions"]) == 1


@pytest.mark.asyncio
async def test_failure_secrets_are_redacted_before_storage_api_and_ai_input(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Failure Secret Redaction"})).json()
    raw_url_secret = "url-query-sentinel"
    raw_bearer_secret = "bearer-sentinel-123"
    raw_password_secret = "password-sentinel"
    raw_error = (
        "AssertionError: https://example.test/reset?token=url-query-sentinel "
        "Authorization: Bearer bearer-sentinel-123 password=password-sentinel"
    )
    raw_stack = f'Traceback (most recent call last):\n  File "test.py", line 3\n    raise Exception("{raw_error}")\n'

    async with test_db_session() as session:
        repo = TestRunRepository(session)
        run = await repo.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        await session.commit()
        run_id = run.id

    suite = SuiteExecutionResult(
        exit_code=1,
        total=1,
        failed=1,
        results=[
            SingleTestResult(
                nodeid="tests/test_secrets.py::test_failure",
                status=TestExecutionStatus.FAILED,
                error_message=raw_error,
                stack_trace=raw_stack,
            )
        ],
    )
    async with test_db_session() as session:
        service = TestRunService(TestRunRepository(session), WorkspaceRepository(session), WorkspaceService())
        await service.persist_suite_result(run_id, suite)

    async with test_db_session() as session:
        execution = (
            await session.execute(select(TestExecutionORM).where(TestExecutionORM.run_id == run_id))
        ).scalar_one()
        failure = (
            await session.execute(select(FailureRecordORM).where(FailureRecordORM.run_id == run_id))
        ).scalar_one()
        failure_id = failure.id
        for value in (execution.error_message, execution.stack_trace, failure.error_message, failure.stack_trace):
            assert raw_url_secret not in (value or "")
            assert raw_bearer_secret not in (value or "")
            assert raw_password_secret not in (value or "")

        service = get_failure_service(session)
        observed = {}

        class CapturingOrchestrator:
            async def diagnose_failure_ai(self, **kwargs):
                observed.update(kwargs)
                return FailureAnalysisResponse(classification="UNKNOWN", root_cause="Observed failure")

            def last_invocation_metadata(self):
                return {"provider": "fake", "model": "fake-qa-model", "fallback_used": True}

        service.orchestrator = CapturingOrchestrator()
        await service.diagnose_failure_ai(failure_id)
        assert raw_url_secret not in observed["error_message"]
        assert raw_bearer_secret not in observed["error_message"]
        assert raw_password_secret not in observed["error_message"]
        assert raw_url_secret not in observed["stack_trace"]
        assert raw_bearer_secret not in observed["stack_trace"]
        assert raw_password_secret not in observed["stack_trace"]

    failure_response = await client.get(f"/api/failures/{failure_id}")
    assert failure_response.status_code == 200
    serialized = failure_response.text
    assert raw_url_secret not in serialized
    assert raw_bearer_secret not in serialized
    assert raw_password_secret not in serialized


@pytest.mark.asyncio
async def test_legacy_run_output_and_execution_secrets_are_redacted_on_api_read(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Legacy Run Secret Redaction"})).json()
    raw_url_secret = "legacy-url-query-sentinel"
    raw_bearer_secret = "legacy-bearer-sentinel-456"
    raw_password_secret = "legacy-password-sentinel"
    raw_error = (
        f"AssertionError: https://example.test/reset?token={raw_url_secret} "
        f"Authorization: Bearer {raw_bearer_secret} password={raw_password_secret}"
    )
    raw_stack = f'Traceback (most recent call last):\n    raise Exception("{raw_error}")\n'

    async with test_db_session() as session:
        repo = TestRunRepository(session)
        run = await repo.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        run.log_output = f"legacy log: {raw_error}"
        run.external_build_url = f"https://build-user:build-password@example.test/job/42?token={raw_url_secret}"
        await repo.add_execution(
            run.id,
            "tests/test_legacy.py::test_failure",
            RunStatus.FAILED,
            error_message=raw_error,
            stack_trace=raw_stack,
        )
        await repo.add_external_artifact(
            run.id,
            "Legacy HTML report",
            "HTML_REPORT",
            f"https://reports.example.test/run/42?token={raw_url_secret}",
        )
        session.add(
            BrowserSessionORM(
                id="legacy-browser-session",
                run_id=run.id,
                browser_session_id="legacy-browser-session",
                page_id="legacy-browser-page",
                nodeid="tests/test_legacy.py::test_failure",
                current_url=f"https://app.example.test/checkout?token={raw_url_secret}",
            )
        )
        await session.commit()
        run_id = run.id

    response = await client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    serialized = response.text
    for secret in (raw_url_secret, raw_bearer_secret, raw_password_secret, "build-password"):
        assert secret not in serialized
    assert payload["log_output"] is not None
    assert payload["executions"][0]["error_message"] is not None
    assert payload["executions"][0]["stack_trace"] is not None
    assert payload["external_build_url"].startswith("https://example.test/")
    assert payload["external_artifacts"][0]["url"] == "https://reports.example.test/run/42"
    assert payload["browser_sessions"][0]["current_url"] == "https://app.example.test/checkout"


@pytest.mark.asyncio
async def test_late_suite_result_cannot_add_executions_to_a_cancelled_run(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Late Result Guard"})).json()
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            TestRunCreate(project_id=project["id"], workspace_id=project["id"])
        )
        run.status = RunStatus.CANCELLED.value
        await session.commit()
        run_id = run.id

    result = SuiteExecutionResult(
        exit_code=0,
        total=1,
        passed=1,
        results=[SingleTestResult(nodeid="tests/test_late.py::test_late", status=TestExecutionStatus.PASSED)],
    )
    async with test_db_session() as session:
        service = TestRunService(TestRunRepository(session), WorkspaceRepository(session), WorkspaceService())
        await service.persist_suite_result(run_id, result)

    fetched = await client.get(f"/api/runs/{run_id}")
    assert fetched.json()["status"] == "CANCELLED"
    assert fetched.json()["executions"] == []


@pytest.mark.asyncio
async def test_jenkins_cancellation_reuses_the_selected_profile(client: AsyncClient, test_db_session, monkeypatch):
    project = (await client.post("/api/projects", json={"name": "Profiled Jenkins Cancel"})).json()
    profile_id = "jenkins-profile-cancel-test"
    async with test_db_session() as session:
        session.add(
            RunnerProfileORM(
                id=profile_id,
                project_id=project["id"],
                name="Selected Jenkins",
                type="JENKINS",
                enabled=True,
                config={
                    "base_url": "https://jenkins.example.test/root",
                    "job_name": "qa-selected-suite",
                    "user": "qa-user",
                    "api_token": "profile-token-sentinel",
                },
            )
        )
        repo = TestRunRepository(session)
        run = await repo.create_run(
            TestRunCreate(
                project_id=project["id"],
                workspace_id=project["id"],
                runner_type="JENKINS",
                runner_profile_id=profile_id,
            )
        )
        run.status = RunStatus.RUNNING.value
        run.external_job_id = "queue:54321"
        await session.commit()
        run_id = run.id

    observed = {}

    class StubJenkinsBackend:
        def __init__(self, config=None):
            self.config = config

        async def stop(self, _run_id, external_job_id=None):
            observed["config"] = self.config
            observed["external_job_id"] = external_job_id
            return True

    monkeypatch.setattr("app.services.test_run_service.JenkinsRunnerBackend", StubJenkinsBackend)
    async with test_db_session() as session:
        service = TestRunService(TestRunRepository(session), WorkspaceRepository(session), WorkspaceService())
        cancelled = await service.cancel_run(run_id)
    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED
    assert observed["config"].base_url == "https://jenkins.example.test/root"
    assert observed["config"].job_name == "qa-selected-suite"
    assert observed["config"].user == "qa-user"
    assert observed["config"].api_token == "profile-token-sentinel"
    assert observed["external_job_id"] == "queue:54321"


@pytest.mark.asyncio
async def test_jenkins_worker_polls_until_remote_build_is_terminal(client: AsyncClient, test_db_session, monkeypatch):
    project = (await client.post("/api/projects", json={"name": "Jenkins Polling"})).json()
    data = TestRunCreate(
        project_id=project["id"],
        workspace_id=project["id"],
        runner_type="JENKINS",
        nodeids=["tests/test_ci.py::test_ci"],
    )
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(data)
        await session.commit()
        run_id = run.id

    first_poll = asyncio.Event()
    continue_build = asyncio.Event()
    config = SimpleNamespace(job_name="qa-suite", poll_interval_seconds=0.01)
    monkeypatch.setattr("app.services.test_run_service._jenkins_config_for_profile", lambda _profile: config)

    class StubJenkinsBackend:
        def __init__(self, config=None):
            self.config = config
            self.status_calls = 0
            self.log_calls = 0

        async def trigger(self, _request):
            return SimpleNamespace(external_job_id="queue:42")

        async def get_status(self, _run_id, external_job_id=None):
            self.status_calls += 1
            if self.status_calls == 1:
                first_poll.set()
                await continue_build.wait()
                return RunnerStatusResult(
                    run_id=run_id,
                    status=RunStatus.RUNNING,
                    external_job_id="42",
                    external_build_url="https://jenkins.example.test/job/qa-suite/42/",
                )
            return RunnerStatusResult(
                run_id=run_id,
                status=RunStatus.PASSED,
                duration_ms=25,
                external_job_id="42",
                external_build_url="https://jenkins.example.test/job/qa-suite/42/",
            )

        async def stream_logs(self, _run_id, external_job_id=None):
            self.log_calls += 1
            if external_job_id == "42":
                yield "new Jenkins log chunk\n"

        async def stop(self, _run_id, external_job_id=None):
            return True

    monkeypatch.setattr("app.services.test_run_service.JenkinsRunnerBackend", StubJenkinsBackend)
    async with test_db_session() as session:
        service = TestRunService(TestRunRepository(session), WorkspaceRepository(session), WorkspaceService())
        worker = asyncio.create_task(service._run_jenkins_worker_task(run_id, data))
        await asyncio.wait_for(first_poll.wait(), timeout=2)
        async with test_db_session() as read_session:
            running = await TestRunRepository(read_session).get_by_id(run_id)
            assert running is not None
            assert running.status == RunStatus.RUNNING.value
            assert running.finished_at is None
        continue_build.set()
        await asyncio.wait_for(worker, timeout=2)

    completed = (await client.get(f"/api/runs/{run_id}")).json()
    assert completed["status"] == "PASSED"
    assert completed["finished_at"] is not None


@pytest.mark.asyncio
async def test_browser_event_urls_are_sanitized_before_database_and_sse(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Browser URL Redaction"})).json()
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            TestRunCreate(project_id=project["id"], workspace_id=project["id"])
        )
        await session.commit()
        run_id = run.id
    queue = event_bus.subscribe(run_id)
    sentinel_url = "https://user:pass@example.test/account?access_token=sentinel#private"
    try:
        async with test_db_session() as session:
            service = TestRunService(TestRunRepository(session), WorkspaceRepository(session), WorkspaceService())
            await service._record_browser_event(
                run_id,
                {
                    "type": "session.started",
                    "session_id": "browser-redaction-session",
                    "page_id": "browser-redaction-page",
                    "nodeid": "tests/test_account.py::test_account",
                    "worker_id": "gw0",
                    "url": sentinel_url,
                    "status": "running",
                },
            )
            session_event = queue.get_nowait()
            assert session_event["session"]["current_url"] == "https://example.test/account"
            await service._record_browser_event(
                run_id,
                {
                    "type": "frame",
                    "session_id": "browser-redaction-session",
                    "page_id": "browser-redaction-page",
                    "nodeid": "tests/test_account.py::test_account",
                    "worker_id": "gw0",
                    "url": sentinel_url,
                    "frame": "encoded-frame",
                },
            )
            frame_event = queue.get_nowait()
            assert frame_event["url"] == "https://example.test/account"
            stored = await session.get(BrowserSessionORM, "browser-redaction-session")
            assert stored is not None
            assert stored.current_url == "https://example.test/account"
    finally:
        event_bus.unsubscribe(run_id, queue)


@pytest.mark.asyncio
async def test_run_stream_replays_browser_sessions_created_before_connection(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Browser Reconnect"})).json()
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        await session.commit()
        service = TestRunService(repository, WorkspaceRepository(session), WorkspaceService())
        # There is no subscriber when this event arrives, as with a page refresh.
        await service._record_browser_event(
            run.id,
            {
                "type": "session.started",
                "session_id": "reconnected-browser",
                "page_id": "reconnected-page",
                "nodeid": "tests/test_browser.py::test_page",
                "url": "https://example.test/start",
            },
        )
        stream = service.event_generator(run.id)
        try:
            connected = await anext(stream)
            assert connected["type"] == "CONNECTED"
            restored = await anext(stream)
            assert restored["type"] == "BROWSER_SESSION"
            assert restored["session"]["browser_session_id"] == "reconnected-browser"
            assert restored["session"]["current_url"] == "https://example.test/start"

            # Simulate a different worker process updating the database without this event bus.
            async with test_db_session() as worker_session:
                browser = await worker_session.get(BrowserSessionORM, "reconnected-browser")
                browser.current_url = "https://example.test/next"
                await worker_session.commit()
            updated = await asyncio.wait_for(anext(stream), timeout=3)
            assert updated["type"] == "BROWSER_SESSION"
            assert updated["session"]["current_url"] == "https://example.test/next"
        finally:
            await stream.aclose()
        assert run.id not in event_bus._subscribers


@pytest.mark.asyncio
async def test_run_stream_unsubscribes_when_closed_after_connected(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Stream Cleanup"})).json()
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        await session.commit()
        service = TestRunService(repository, WorkspaceRepository(session), WorkspaceService())
        stream = service.event_generator(run.id)
        await anext(stream)
        await stream.aclose()
        assert run.id not in event_bus._subscribers


@pytest.mark.asyncio
async def test_run_cancellation_is_idempotent_and_cancels_distributed_job(client: AsyncClient):
    project = (await client.post("/api/projects", json={"name": "Cancel Distributed Run"})).json()
    created = await client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "workspace_id": project["id"],
            "runner_type": "WORKER",
            "nodeids": ["tests/test_slow.py::test_waits"],
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    jobs = await client.get("/api/jobs", params={"run_id": run_id})
    assert jobs.status_code == 200, jobs.text
    assert len(jobs.json()) == 1
    job_id = jobs.json()[0]["id"]

    cancelled = await client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    assert (await client.get(f"/api/jobs/{job_id}")).json()["status"] == "CANCELLED"

    repeated = await client.post(f"/api/runs/{run_id}/cancel")
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["status"] == "CANCELLED"

    # A late worker error must not overwrite the cancellation with FAILED.
    late_error = await client.post(f"/api/jobs/{job_id}/fail", json={"error_message": "late worker response"})
    assert late_error.status_code == 200, late_error.text
    assert late_error.json()["status"] == "CANCELLED"
    assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_does_not_change_a_terminal_run(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Terminal Run Cannot Cancel"})).json()
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            TestRunCreate(project_id=project["id"], workspace_id=project["id"])
        )
        run.status = RunStatus.PASSED.value
        run.finished_at = utc_now()
        await session.commit()
        run_id = run.id

    cancelled = await client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "PASSED"


async def _seed_locator_failure(client: AsyncClient, test_db_session, file_path: str, content: str, locator: str):
    """Create a project with a real workspace file plus a failure record pointing at it."""
    project = (
        await client.post("/api/projects", json={"name": f"Repair {locator}", "bootstrap_workspace": True})
    ).json()
    project_id = project["id"]
    written = await client.put(f"/api/workspaces/{project_id}/file", json={"path": file_path, "content": content})
    assert written.status_code == 200, written.text

    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        execution = await run_repo.add_execution(run_id=run.id, nodeid=f"{file_path}::test_x", status=RunStatus.FAILED)
        failure = await run_repo.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid=f"{file_path}::test_x",
            test_name="test_x",
            classification="LOCATOR_CHANGED",
            exception_type="TimeoutError",
            error_message=f'Timeout waiting for locator("{locator}")',
            stack_trace="",
            failing_locator=locator,
        )
        await session.commit()
        failure_id = failure.id
    return project_id, failure_id


@pytest.mark.integration
async def test_generated_repair_proposal_persists_without_closing_request_session(client: AsyncClient, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Persist Repair Proposal"})).json()
    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        execution = await run_repo.add_execution(
            run_id=run.id,
            nodeid="tests/test_cart.py::test_cart",
            status=RunStatus.FAILED,
        )
        failure = await run_repo.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid="tests/test_cart.py::test_cart",
            test_name="test_cart",
            classification="LOCATOR_CHANGED",
            exception_type="PlaywrightError",
            error_message="The old locator did not resolve.",
            stack_trace="tests/test_cart.py:12",
            failing_locator="#old-cart-button",
        )
        await session.commit()
        failure_id = failure.id
        execution_id = execution.id

        service = get_failure_service(session)

        class StubOrchestrator:
            async def diagnose_failure_ai(self, **_kwargs):
                return FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The old locator no longer matches the page.",
                    provider="fake",
                    fallback_used=True,
                )

            def last_invocation_metadata(self):
                return {"provider": "fake", "model": "fake-qa-model", "fallback_used": True}

            def propose_locator_repair(self, *, failing_locator, error_message, file_path):
                return LocatorRepairProposal(
                    old_locator=failing_locator,
                    proposed_locator='[data-testid="cart-submit"]',
                    strategy="test_id",
                    reason=error_message,
                    file_path=file_path,
                )

        service.orchestrator = StubOrchestrator()
        proposal = await service.generate_repair_proposal(failure_id)
        assert session.is_active
        assert proposal.proposed_locator == '[data-testid="cart-submit"]'
        assert all(
            event.case_execution_id == execution_id
            for event in proposal.execution_trace
            if event.case_execution_id is not None
        )
        await session.commit()

    async with test_db_session() as session:
        stored = await session.get(FailureRecordORM, failure_id)
        assert stored is not None
        assert stored.repair_proposal["proposed_locator"] == '[data-testid="cart-submit"]'
        assert stored.repair_proposal["execution_trace"]


@pytest.mark.integration
async def test_apply_repair_keeps_the_file_parseable_when_the_locator_contains_quotes(
    client: AsyncClient, test_db_session
):
    """Proposed locators such as [data-testid="submit"] must not break the surrounding string."""
    original = 'def test_x():\n    selector = "#checkout-submit"\n    assert selector\n'
    project_id, failure_id = await _seed_locator_failure(
        client, test_db_session, "tests/test_repair.py", original, "#checkout-submit"
    )

    applied = await client.post(
        f"/api/failures/{failure_id}/apply-repair",
        params={"workspace_id": project_id},
        json={
            "file_path": "tests/test_repair.py",
            "old_code": "#checkout-submit",
            "new_code": '[data-testid="submit"]',
        },
    )
    assert applied.status_code == 200, applied.text

    patched = (await client.get(f"/api/workspaces/{project_id}/file?path=tests/test_repair.py")).json()["content"]
    compile(patched, "test_repair.py", "exec")  # the patched file must still be valid Python
    assert '[data-testid=\\"submit\\"]' in patched
    assert "#checkout-submit" not in patched

    validation = await client.post(f"/api/workspaces/{project_id}/validate")
    assert validation.json()["valid"] is True


@pytest.mark.integration
async def test_apply_repair_refuses_a_patch_that_would_break_the_file(client: AsyncClient, test_db_session):
    original = 'def test_x():\n    selector = "#checkout-submit"\n    assert selector\n'
    project_id, failure_id = await _seed_locator_failure(
        client, test_db_session, "tests/test_repair_broken.py", original, "#checkout-submit"
    )

    refused = await client.post(
        f"/api/failures/{failure_id}/apply-repair",
        params={"workspace_id": project_id},
        json={
            "file_path": "tests/test_repair_broken.py",
            "old_code": "#checkout-submit",
            # A raw newline cannot live inside the surrounding quoted string, escaped or not.
            "new_code": "first line\nsecond line",
        },
    )

    assert refused.status_code == 400
    assert "nothing was written" in refused.json()["detail"]
    unchanged = (await client.get(f"/api/workspaces/{project_id}/file?path=tests/test_repair_broken.py")).json()
    assert unchanged["content"] == original


def test_public_locator_proposal_replaces_call_only_in_failed_test():
    service = object.__new__(FailureService)
    source = (
        'def test_other(page):\n    page.locator("#old").click()\n\n'
        'def test_failed(page):\n    label = "中文"; page.locator("#old").click(timeout=500)\n'
    )
    patched = service._patched_content(
        source, "tests/test_cart.py", "#old", 'get_by_role("button", name="Help")', test_name="test_failed"
    )
    assert 'page.get_by_role("button", name="Help").click(timeout=500)' in patched
    assert patched.count('page.locator("#old")') == 1
    compile(patched, "test_cart.py", "exec")


def test_public_locator_proposal_refuses_dynamic_code_and_ambiguous_target():
    service = object.__new__(FailureService)
    source = 'def test_failed(page):\n    page.locator("#old").click()\n    page.locator("#old").click()\n'
    assert (
        service._patched_content(
            source, "test_cart.py", "#old", 'get_by_role("button", name="Help")', test_name="test_failed"
        )
        is None
    )
    assert (
        service._patched_content(
            source, "test_cart.py", "#old", 'get_by_role(__import__("os").getenv("SECRET"))', test_name="test_failed"
        )
        is None
    )


@pytest.mark.integration
async def test_imported_run_persists_its_console_output(client: AsyncClient, tmp_path):
    """A finished run must still show what the runner printed, not an empty console."""
    repo = tmp_path / "console-repo"
    (repo / "tests" / "unit").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "console-probe"\nrequires-python = ">=3.11"\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    (repo / "tests" / "unit" / "test_probe.py").write_text(
        "def test_passes():\n    assert True\n\n\ndef test_fails():\n    assert False\n", encoding="utf-8"
    )

    imported = await client.post("/api/onboarding/import", json={"source_path": str(repo)})
    assert imported.status_code == 201, imported.text
    project_id = imported.json()["project_id"]

    run = await client.post(
        f"/api/onboarding/{project_id}/run",
        json={"nodeids": ["tests/unit/test_probe.py::test_passes", "tests/unit/test_probe.py::test_fails"]},
    )
    assert run.status_code == 200, run.text
    run_id = run.json()["run_id"]

    fetched = await client.get(f"/api/runs/{run_id}")
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["status"] == "FAILED"
    assert body["log_output"], "a finished run must keep the runner's console output"
    assert "test_fails" in body["log_output"]


@pytest.mark.integration
async def test_failed_user_frame_creates_auto_failure_breakpoint(client: AsyncClient, test_db_session):
    from app.services.test_run_service import TestRunService
    from app.services.workspace_service import WorkspaceService

    project = (
        await client.post("/api/projects", json={"name": "Failure Breakpoint", "bootstrap_workspace": True})
    ).json()
    project_id = project["id"]
    await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/test_cart.py", "content": "def test_cart():\n    assert False\n"},
    )
    workspace_dir = WorkspaceService().get_workspace_dir(project_id)
    async with test_db_session() as session:
        run = await TestRunRepository(session).create_run(
            TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=["tests/test_cart.py::test_cart"])
        )
        await session.commit()
        run_id = run.id

    test_file = workspace_dir / "tests" / "test_cart.py"
    suite = SuiteExecutionResult(
        exit_code=1,
        total=1,
        failed=1,
        results=[
            SingleTestResult(
                nodeid="tests/test_cart.py::test_cart",
                status=TestExecutionStatus.FAILED,
                error_message="AssertionError: assert False",
                stack_trace=f'File "{test_file.as_posix()}", line 2, in test_cart\n',
            )
        ],
    )
    service = TestRunService(
        TestRunRepository(test_db_session), WorkspaceRepository(test_db_session), WorkspaceService()
    )
    await service.persist_suite_result(run_id, suite, workspace_id=project_id, workspace_dir=workspace_dir)

    async with test_db_session() as session:
        result = await session.execute(
            select(BreakpointORM).where(
                BreakpointORM.workspace_id == project_id,
                BreakpointORM.file_path == "tests/test_cart.py",
                BreakpointORM.line_number == 2,
                BreakpointORM.source == "auto_failure",
            )
        )
        breakpoint = result.scalar_one_or_none()
    assert breakpoint is not None
    assert breakpoint.run_id == run_id


@pytest.mark.integration
async def test_workspace_breakpoint_crud_and_path_validation(client: AsyncClient):
    project = (await client.post("/api/projects", json={"name": "Manual Breakpoint"})).json()
    project_id = project["id"]
    endpoint = f"/api/workspaces/{project_id}/breakpoints"

    created = await client.put(
        endpoint,
        json={"file_path": "tests/test_cart.py", "line_number": 7, "enabled": True, "source": "manual"},
    )
    assert created.status_code == 200, created.text
    breakpoint_id = created.json()["id"]
    assert created.json()["source"] == "manual"

    listed = await client.get(endpoint)
    assert listed.status_code == 200
    assert [(item["file_path"], item["line_number"]) for item in listed.json()] == [("tests/test_cart.py", 7)]

    unsafe = await client.put(
        endpoint,
        json={"file_path": "../outside.py", "line_number": 1, "source": "manual"},
    )
    assert unsafe.status_code == 400

    deleted = await client.delete(f"{endpoint}/{breakpoint_id}")
    assert deleted.status_code == 204


@pytest.mark.integration
async def test_a_suite_that_never_ran_is_an_error_not_a_pass(client: AsyncClient, test_db_session, tmp_path):
    """A broken conftest (missing dependency) must not be reported as PASSED with 0 tests."""
    project = (await client.post("/api/projects", json={"name": "Broken Suite", "bootstrap_workspace": True})).json()
    project_id = project["id"]
    # Write the broken fixture into the project's real workspace, which is where the run executes.
    await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/conftest.py", "content": "import package_that_does_not_exist\n"},
    )
    await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/test_x.py", "content": "def test_x():\n    assert True\n"},
    )

    async with test_db_session() as session:
        run_repo = TestRunRepository(session)
        run = await run_repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        await session.commit()
        run_id = run.id

    from app.services.test_run_service import TestRunService
    from app.services.workspace_service import WorkspaceService

    service = TestRunService(
        TestRunRepository(test_db_session), WorkspaceRepository(test_db_session), WorkspaceService()
    )
    await service._run_worker_task(run_id, TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=[]))

    async with test_db_session() as session:
        stored = await TestRunRepository(session).get_by_id(run_id)
        assert stored is not None
        # ERROR, not PASSED: nothing executed, and the console carries the reason.
        assert stored.status == RunStatus.ERROR.value, stored.status
        assert stored.passed == 0
        assert stored.log_output and "package_that_does_not_exist" in stored.log_output


@pytest.mark.unit
def test_run_verdict_never_invents_a_pass_from_an_empty_result_set():
    from app.services.test_run_service import TestRunService

    service = TestRunService.__new__(TestRunService)  # no repositories needed for the pure decision
    # exit 4 = usage error (broken conftest / bad args): the suite did not run
    assert service._verdict(4, 0, 0) is RunStatus.ERROR
    assert service._verdict(5, 0, 0) is RunStatus.ERROR
    assert service._verdict(None, 0, 0) is RunStatus.ERROR
    # a genuine pass, and a genuine failure
    assert service._verdict(0, 3, 0) is RunStatus.PASSED
    assert service._verdict(1, 3, 1) is RunStatus.FAILED
    # non-zero exit with results parsed is a failure even if the counter disagrees
    assert service._verdict(1, 2, 0) is RunStatus.FAILED
