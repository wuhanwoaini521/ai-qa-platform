from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient
from integrations.jenkins_runner import (
    FakeJenkinsServer,
    JenkinsConfig,
    JenkinsRunnerBackend,
)
from project_model.models import RunnerType, RunStatus
from qa_core.execution.runner_backend import LocalRunnerBackend, RunnerTriggerRequest


@pytest.mark.asyncio
@pytest.mark.unit
async def test_local_runner_backend():
    backend = LocalRunnerBackend()
    health = await backend.check_health()
    assert health.status == "AVAILABLE"
    assert health.type == RunnerType.LOCAL

    trig = await backend.trigger(
        RunnerTriggerRequest(
            run_id="run_local_123",
            project_id="proj_1",
            nodeids=["tests/test_login.py::test_valid_login"],
        )
    )
    assert trig.status == RunStatus.RUNNING


@pytest.mark.asyncio
@pytest.mark.unit
async def test_jenkins_runner_backend_with_fake_server(monkeypatch):
    fake_server = FakeJenkinsServer(base_url="http://jenkins.mock.ci:8080", job_name="qa-e2e-suite")
    transport = httpx.MockTransport(fake_server.handle_request)

    orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: orig_client(transport=transport))

    cfg = JenkinsConfig(
        base_url="http://jenkins.mock.ci:8080",
        job_name="qa-e2e-suite",
        user="qa-agent",
        api_token="token_secret_123",
        parameter_mapping={"markers": "CASES_SPECIFIED", "nodeids": "TARGET_TESTS"},
    )
    backend = JenkinsRunnerBackend(config=cfg)

    # 1. Health check
    health = await backend.check_health()
    assert health.status == "AVAILABLE"

    # 2. Trigger
    trig_res = await backend.trigger(
        RunnerTriggerRequest(
            run_id="run_jenkins_456",
            project_id="proj_1",
            markers=["smoke", "regression"],
            nodeids=["tests/test_checkout.py::test_payment"],
        )
    )
    assert trig_res.external_job_id is not None
    assert "queue:" in trig_res.external_job_id

    # 3. Resolve build number
    qid = trig_res.external_job_id.replace("queue:", "")
    build_num, build_url = await backend.resolve_build_number(qid, max_wait=5.0)
    assert build_num is not None
    assert "qa-e2e-suite" in build_url

    # 4. Stream progressive logs
    logs = []
    async for chunk in backend.stream_logs("run_jenkins_456", external_job_id=str(build_num)):
        logs.append(chunk)
    assert len(logs) > 0
    assert "Running automated test suite on Jenkins" in "".join(logs)
    later_logs = [chunk async for chunk in backend.stream_logs("run_jenkins_456", external_job_id=str(build_num))]
    assert later_logs == []

    # 5. Status check & Artifacts
    status_res = await backend.get_status("run_jenkins_456", external_job_id=str(build_num))
    assert status_res.status == RunStatus.PASSED
    assert len(status_res.artifacts) >= 2
    assert any(a["type"] == "ALLURE" for a in status_res.artifacts)

    # 6. Stop/Cancel
    stopped = await backend.stop("run_jenkins_456", external_job_id=str(build_num))
    assert stopped is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_runner_profile_api_endpoints(client: AsyncClient):
    # 1. List initial runners
    runners_res = await client.get("/api/runners")
    assert runners_res.status_code == 200

    # 2. Create Jenkins runner profile
    create_res = await client.post(
        "/api/runners",
        json={
            "name": "Production Jenkins EU",
            "type": "JENKINS",
            "enabled": True,
            "config": {
                "base_url": "https://jenkins.eu.corp:8080",
                "job_name": "qa-nightly-pipeline",
                "default_parameters": {"REGION": "EU", "NUM_PROCESSES": "4"},
            },
        },
    )
    assert create_res.status_code == 200
    runner_data = create_res.json()
    runner_id = runner_data["id"]
    assert runner_data["name"] == "Production Jenkins EU"
    assert runner_data["type"] == "JENKINS"

    # 3. Get runner by ID
    get_res = await client.get(f"/api/runners/{runner_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == runner_id

    # 4. Check Health endpoint
    health_res = await client.get(f"/api/runners/{runner_id}/health")
    assert health_res.status_code == 200
    assert "status" in health_res.json()

    # 5. Update runner profile
    patch_res = await client.patch(
        f"/api/runners/{runner_id}",
        json={"name": "Production Jenkins EU Primary"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Production Jenkins EU Primary"

    # 6. Delete runner profile
    del_res = await client.delete(f"/api/runners/{runner_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_jenkins_parameter_mapping_matches_the_configured_job_contract(monkeypatch):
    """A real Jenkinsfile reads named parameters, so the mapping must be exact and observable."""
    fake_server = FakeJenkinsServer(base_url="http://jenkins.mock.ci:8080", job_name="qa-e2e-suite")
    transport = httpx.MockTransport(fake_server.handle_request)
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: orig_client(transport=transport))

    config = JenkinsConfig(
        base_url="http://jenkins.mock.ci:8080",
        job_name="qa-e2e-suite",
        user="qa-agent",
        api_token="token_secret_123",
        # Job defaults, plus the mapping from platform fields to Jenkins parameter names.
        default_parameters={"REGION": "EU", "NUM_PROCESSES": "4"},
        parameter_mapping={"markers": "CASES_SPECIFIED", "nodeids": "TARGET_TESTS"},
    )
    backend = JenkinsRunnerBackend(config=config)

    request = RunnerTriggerRequest(
        run_id="run_jenkins_789",
        project_id="proj_1",
        markers=["smoke", "regression"],
        nodeids=["tests/test_checkout.py::test_payment", "tests/test_cart.py::test_add_item"],
        parameters={"NUM_PROCESSES": "8", "BROWSER": "chromium"},
    )

    # The mapping is applied before the request is sent, and platform values win over job defaults.
    assert backend._apply_parameter_mapping(request) == {
        "REGION": "EU",
        "NUM_PROCESSES": "8",
        "BROWSER": "chromium",
        "CASES_SPECIFIED": "smoke and regression",
        "TARGET_TESTS": "tests/test_checkout.py::test_payment tests/test_cart.py::test_add_item",
    }

    triggered = await backend.trigger(request)
    assert triggered.status == RunStatus.RUNNING
    assert triggered.external_job_id.startswith("queue:")

    # A request with no selection must not invent empty parameters for the job.
    empty_mapping = backend._apply_parameter_mapping(RunnerTriggerRequest(run_id="run_empty", project_id="proj_1"))
    assert "CASES_SPECIFIED" not in empty_mapping
    assert "TARGET_TESTS" not in empty_mapping


@pytest.mark.asyncio
@pytest.mark.unit
async def test_jenkins_stop_cancels_queued_items_and_stops_started_builds(monkeypatch):
    server = FakeJenkinsServer(base_url="http://jenkins.mock.ci:8080", job_name="qa-e2e-suite")
    transport = httpx.MockTransport(server.handle_request)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: original_client(transport=transport))
    backend = JenkinsRunnerBackend(config=JenkinsConfig(base_url=server.base_url, job_name=server.job_name))

    server.queue["100"] = {}
    assert await backend.stop("run-queued", external_job_id="queue:100")
    assert server.cancelled_queue_ids == {"100"}

    server.queue["101"] = {"executable": {"number": 42}}
    assert await backend.stop("run-started", external_job_id="queue:101")
    assert server.stopped_build_ids == {"42"}
