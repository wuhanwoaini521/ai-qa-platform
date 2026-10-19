import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_recorder_save_case_retry_reuses_case_and_binding(client: AsyncClient, test_db_session, monkeypatch):
    from app.api.recorder import recorder_service
    from app.persistence.models import AutomationBindingORM
    from app.repositories.automation_binding_repo import AutomationBindingRepository
    from app.services.recorder_service import RecorderStep

    project = await client.post("/api/projects", json={"name": "Recorder save", "bootstrap_workspace": False})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    recorded_step = RecorderStep(
        action="click",
        locator={"kind": "role", "value": "button", "name": "Save"},
        evidence={
            "schema_version": 1,
            "element": {"tag": "button", "role": "button", "name": "Save"},
            "context": {"url": "https://example.test/save?session=private"},
            "locator_candidates": [
                {
                    "candidate_id": "candidate_1",
                    "kind": "role",
                    "value": "button",
                    "name": "Save",
                    "verification": {"verified": True},
                }
            ],
            "decision": {"selected_candidate_id": "candidate_1", "source": "jev"},
            "decision_history": [{"candidate_id": "candidate_1", "source": "jev"}],
            "status": "available",
        },
    )
    recording_session = SimpleNamespace(
        id="recorder-session", project_id=project_id, steps=[recorded_step.model_dump(mode="json")]
    )
    monkeypatch.setattr(recorder_service, "get", AsyncMock(return_value=recording_session))
    url = "/api/recorder/sessions/test-session/save-case"
    payload = {
        "test_case": {
            "project_id": project_id,
            "title": "Search Selenium",
            "steps": ["Fill search", "Press Enter"],
            "expected_result": "Official documentation opens",
        },
        "file_path": "tests/test_search.py",
        "test_name": "test_search_selenium",
    }
    for invalid in (
        {"file_path": "../outside.py"},
        {"file_path": "C:/outside.py"},
        {"test_name": "search_selenium"},
    ):
        rejected = await client.post(url, json={**payload, **invalid})
        assert rejected.status_code == 422, rejected.text

    first = await client.post(url, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["reused"] is False
    first_case = first.json()["test_case"]
    first_binding = first.json()["binding"]

    # Studio reads the recorded locator and its evidence pointer back from the binding.
    fetched_binding = await client.get(f"/api/test-cases/{first_case['id']}/binding")
    assert fetched_binding.status_code == 200, fetched_binding.text
    recorded_steps = fetched_binding.json()["recorder_steps"]
    assert len(recorded_steps) == 1, recorded_steps
    assert recorded_steps[0]["action"] == "click"
    assert recorded_steps[0]["evidence_id"] == f"recorder:{recorded_step.id}"
    assert recorded_steps[0]["locator"]["kind"] == "role"
    assert recorded_steps[0]["locator"]["value"] == "button"
    assert recorded_steps[0]["url"] == "https://example.test/save"

    recording_session.steps = []
    retry_payload = {**payload, "test_case": {**payload["test_case"], "title": "Search official Selenium docs"}}
    retry = await client.post(url, json=retry_payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["reused"] is True
    assert retry.json()["test_case"]["id"] == first_case["id"]
    assert retry.json()["test_case"]["title"] == "Search official Selenium docs"
    assert retry.json()["binding"]["id"] == first_binding["id"]
    assert retry.json()["nodeid"] == "tests/test_search.py::test_search_selenium"
    async with test_db_session() as session:
        binding = await session.get(AutomationBindingORM, first_binding["id"])
        evidence = binding.recorder_evidence_bundle
        linked_binding = await AutomationBindingRepository(session).get_active_by_nodeid(
            "tests/test_search.py::test_search_selenium", project_id
        )
        from app.api.failures import get_failure_service

        linked_evidence = await get_failure_service(session)._recorder_evidence_bundle(
            SimpleNamespace(test_nodeid="tests/test_search.py::test_search_selenium"), project_id
        )
    from app.services.failure_evidence_service import FailureEvidenceService
    from app.services.failure_service import FailureService

    failure_evidence = await FailureEvidenceService.collect(
        SimpleNamespace(
            test_nodeid="tests/test_search.py::test_search_selenium",
            screenshot_path=None,
            trace_path=None,
            dom_snapshot_path=None,
            console_logs=[],
            error_message="Timeout waiting for locator",
            stack_trace="",
            failing_locator=None,
        ),
        None,
        None,
        page={
            "recent_steps": [
                {
                    "action": "click",
                    "step_id": recorded_step.id,
                    "evidence_id": f"recorder:{recorded_step.id}",
                    "status": "FAILED",
                }
            ]
        },
        recorder_evidence=linked_evidence,
    )
    repair_candidates = FailureService._recorder_evidence_candidates(
        failure_evidence.element_evidence, "https://example.test/save"
    )
    assert linked_binding.id == first_binding["id"]
    assert linked_evidence["version"] == "v1.0"
    assert linked_evidence["binding_id"] == first_binding["id"]
    assert failure_evidence.element_evidence["binding_id"] == first_binding["id"]
    assert failure_evidence.element_evidence["step_count"] == 1
    assert failure_evidence.element_evidence["revisions"][0]["steps"][0]["step_id"] == recorded_step.id
    assert (
        failure_evidence.element_evidence["revisions"][0]["steps"][0]["evidence_id"] == f"recorder:{recorded_step.id}"
    )
    assert failure_evidence.recent_steps[0]["evidence_id"] == f"recorder:{recorded_step.id}"
    assert len(str(failure_evidence.element_evidence).encode("utf-8")) < 64_000
    assert repair_candidates[0]["name"] == "Save"
    assert evidence["version"] == "v1.0"
    assert evidence["revision"] == 2
    assert evidence["steps"] == []
    assert evidence["revisions"][0]["steps"][0]["evidence"]["decision_history"][0]["source"] == "jev"
    assert len(evidence["decision_history"]) == 1
    assert "session=private" not in str(evidence)

    cases = await client.get(f"/api/test-cases?project_id={project_id}")
    assert cases.status_code == 200
    assert [case["id"] for case in cases.json()] == [first_case["id"]]


@pytest.mark.asyncio
async def test_recorder_case_and_binding_roll_back_together_when_binding_fails(client: AsyncClient, monkeypatch):
    from app.api.recorder import recorder_service
    from app.services.automation_binding_service import AutomationBindingService

    project = await client.post("/api/projects", json={"name": "Recorder rollback", "bootstrap_workspace": False})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    monkeypatch.setattr(
        recorder_service,
        "get",
        AsyncMock(return_value=SimpleNamespace(project_id=project_id)),
    )
    monkeypatch.setattr(
        AutomationBindingService,
        "bind_test_case",
        AsyncMock(side_effect=RuntimeError("binding unavailable")),
    )

    with pytest.raises(RuntimeError, match="binding unavailable"):
        await client.post(
            "/api/recorder/sessions/test-session/save-case",
            json={
                "test_case": {"project_id": project_id, "title": "Atomic save"},
                "file_path": "tests/test_atomic_save.py",
                "test_name": "test_atomic_save",
            },
        )

    cases = await client.get(f"/api/test-cases?project_id={project_id}")
    assert cases.status_code == 200
    assert cases.json() == []


@pytest.mark.asyncio
async def test_recorder_run_retry_reuses_queued_run_and_new_intent_creates_a_new_run(client: AsyncClient, monkeypatch):
    from app.repositories.test_run_repo import TestRunRepository
    from app.services.test_run_service import _RUN_WORKER_TASKS, TestRunService
    from sqlalchemy.exc import IntegrityError

    project = await client.post("/api/projects", json={"name": "Recorder Run retry", "bootstrap_workspace": False})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    scheduled: list[str] = []
    release_workers = asyncio.Event()

    async def hold_local_worker(self, run_id, data, *, execution_deadline=None, local_pytest_options=None):
        scheduled.append(run_id)
        await release_workers.wait()

    monkeypatch.setattr(TestRunService, "_run_worker_task", hold_local_worker)
    payload = {
        "idempotency_key": "recorder-retry-1234",
        "project_id": project_id,
        "workspace_id": project_id,
        "nodeids": ["tests/test_search.py::test_search"],
        "runner_type": "LOCAL",
        "requested_by": "Recorder · Search",
    }

    try:
        first = await client.post("/api/runs", json=payload)
        assert first.status_code == 201, first.text
        await asyncio.sleep(0)
        retry = await client.post("/api/runs", json=payload)
        assert retry.status_code == 201, retry.text
        assert retry.json()["id"] == first.json()["id"]
        assert scheduled == [first.json()["id"]]

        interrupted_worker = _RUN_WORKER_TASKS.pop(first.json()["id"])
        interrupted_worker.cancel()
        await asyncio.gather(interrupted_worker, return_exceptions=True)

        get_by_id = TestRunRepository.get_by_id
        hide_existing_once = True

        async def hide_the_first_lookup(repository, run_id):
            nonlocal hide_existing_once
            if run_id == first.json()["id"] and hide_existing_once:
                hide_existing_once = False
                return None
            return await get_by_id(repository, run_id)

        async def simulate_unique_conflict(repository, data, *, task_id=None):
            raise IntegrityError("insert test_runs", {}, RuntimeError("duplicate primary key"))

        with monkeypatch.context() as conflict_patch:
            conflict_patch.setattr(TestRunRepository, "get_by_id", hide_the_first_lookup)
            conflict_patch.setattr(TestRunRepository, "create_run", simulate_unique_conflict)
            recovered = await client.post("/api/runs", json=payload)
        assert recovered.status_code == 201, recovered.text
        assert recovered.json()["id"] == first.json()["id"]
        await asyncio.sleep(0)
        assert scheduled == [first.json()["id"], first.json()["id"]]

        mismatch = await client.post(
            "/api/runs",
            json={**payload, "nodeids": ["tests/test_search.py::test_other"]},
        )
        assert mismatch.status_code == 422
        assert "different Run request" in mismatch.json()["detail"]

        next_run = await client.post("/api/runs", json={**payload, "idempotency_key": "recorder-run-5678"})
        assert next_run.status_code == 201, next_run.text
        assert next_run.json()["id"] != first.json()["id"]
        await asyncio.sleep(0)
        assert scheduled == [first.json()["id"], first.json()["id"], next_run.json()["id"]]
    finally:
        release_workers.set()
        await asyncio.sleep(0)
