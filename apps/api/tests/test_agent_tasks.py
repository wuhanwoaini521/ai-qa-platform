from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.api.runs import open_run_service
from app.api.tasks import task_runtime_service
from app.persistence.models import TaskORM
from app.repositories.task_repo import TaskRepository
from app.services.task_workflows import build_plan
from app.settings import settings
from project_model.task_models import TaskStatus, TaskStepStatus, TaskType

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("task_type", list(TaskType))
def test_registered_task_workflows_are_valid_dags(task_type):
    plan = build_plan(task_type)
    keys = [step.key for step in plan]
    assert len(keys) == len(set(keys))
    known = set(keys)
    assert all(set(step.depends_on) <= known for step in plan)
    assert all(step.tool and step.name for step in plan)


@pytest.mark.asyncio
async def test_task_api_persists_task_steps_and_replayable_terminal_events(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Inspect the local help page", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    listed = await client.get("/api/tasks")
    assert listed.status_code == 200
    assert any(item["id"] == task_id for item in listed.json())

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.COMPLETED.value
        rows = await TaskRepository(session).steps_for_task(task_id)
        assert len(rows) == len(build_plan(TaskType.EXPLORE_PAGE))
        await TaskRepository(session).add_event(task_id, "task.completed", {"verification": "test"})
        await session.commit()

    detail = await client.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    assert [step["key"] for step in detail.json()["steps"]] == [step.key for step in build_plan(TaskType.EXPLORE_PAGE)]
    stream = await client.get(f"/api/tasks/{task_id}/events")
    assert stream.status_code == 200
    assert '"type": "task.created"' in stream.text
    assert '"type": "task.completed"' in stream.text


@pytest.mark.asyncio
async def test_task_replan_retries_only_failed_read_only_step(client, test_db_session):
    created = await client.post(
        "/api/tasks", json={"type": "EXPLORE_PAGE", "goal": "Inspect a page", "inputs": {"url": "http://127.0.0.1:1/"}}
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        task.status = TaskStatus.BLOCKED.value
        rows = await TaskRepository(session).steps_for_task(task_id)
        rows[0].status = TaskStepStatus.FAILED.value
        rows[0].error = "Temporary navigation error"
        await session.commit()

    replanned = await client.post(
        f"/api/tasks/{task_id}/replan", params={"instructions": "Retry after checking the page URL"}
    )
    assert replanned.status_code == 200, replanned.text
    assert replanned.json()["status"] == "REPLANNING"
    inspect = next(step for step in replanned.json()["steps"] if step["key"] == "inspect")
    assert inspect["status"] == "PENDING"
    assert inspect["error"] is None


@pytest.mark.asyncio
async def test_restart_recovery_blocks_active_steps_without_replaying_them(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Recover an interrupted browser task",
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        task.status = TaskStatus.RUNNING.value
        steps = await TaskRepository(session).steps_for_task(task_id)
        steps[0].status = TaskStepStatus.RUNNING.value
        await session.commit()

    recovered = await task_runtime_service.recover_interrupted()
    assert task_id in recovered
    detail = await task_runtime_service.get(task_id)
    assert detail is not None and detail.status == TaskStatus.BLOCKED
    assert detail.steps[0].status == TaskStepStatus.FAILED
    assert "API restarted" in (detail.steps[0].error or "")


@pytest.mark.asyncio
async def test_replan_refuses_to_replay_completed_source_writes(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Do not replay source writes", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        owner_id = task.owner_id
        task.status = TaskStatus.BLOCKED.value
        steps = await TaskRepository(session).steps_for_task(task_id)
        steps[0].key = "write"
        steps[0].tool = "source.write_generated"
        steps[0].status = TaskStepStatus.COMPLETED.value
        await session.commit()

    with pytest.raises(ValueError, match="already changed workspace source"):
        await task_runtime_service.replan(task_id, owner_id, "retry")
    detail = await task_runtime_service.get(task_id)
    assert detail is not None and detail.status == TaskStatus.BLOCKED


@pytest.mark.asyncio
async def test_task_approval_resumes_only_an_owned_waiting_task(client, test_db_session):
    project = await client.post("/api/projects", json={"name": "Task Approval Project", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspaces = await client.get(f"/api/workspaces?project_id={project_id}")
    assert workspaces.status_code == 200 and workspaces.json()
    workspace_id = workspaces.json()[0]["id"]
    created = await client.post(
        "/api/tasks",
        json={
            "type": "CREATE_TEST",
            "goal": "Create an approved login test",
            "project_id": project_id,
            "workspace_id": workspace_id,
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        rows = await TaskRepository(session).steps_for_task(task_id)
        approval = next(step for step in rows if step.key == "approval")
        task.status = TaskStatus.WAITING.value
        task.current_step_id = approval.id
        approval.status = TaskStepStatus.WAITING_FOR_APPROVAL.value
        await session.commit()

    response = await client.post(f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    approval = next(step for step in body["steps"] if step["key"] == "approval")
    assert approval["status"] == "COMPLETED"
    assert approval["outputs"]["approved"] is True


@pytest.mark.asyncio
async def test_task_endpoints_require_authentication(anonymous_client):
    response = await anonymous_client.get("/api/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pending_task_can_be_cancelled(client):
    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Cancel before browser navigation",
            "inputs": {"url": "http://127.0.0.1:1/"},
        },
    )
    assert created.status_code == 201, created.text
    cancelled = await client.post(f"/api/tasks/{created.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancelling_active_task_stops_its_child_pytest(client):
    project = await client.post("/api/projects", json={"name": "Cancel Child Run", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_runtime_cancel.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("import time\n\ndef test_wait_for_cancellation():\n    time.sleep(30)\n", encoding="utf-8")

    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "RUN_REGRESSION",
                "goal": "Cancel the active child run",
                "project_id": project_id,
                "workspace_id": project_id,
                "inputs": {"nodeids": ["tests/test_runtime_cancel.py::test_wait_for_cancellation"]},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(100):
            await asyncio.sleep(0.1)
            child_run_id = task_runtime_service._child_runs.get(task_id)
            if child_run_id:
                async with open_run_service() as service:
                    child = await service.get_run(child_run_id)
                if child and child.status.value == "RUNNING":
                    break
        assert child_run_id, "task never registered a child run"

        cancelled = await client.post(f"/api/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        detail = await client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200, detail.text
        assert any(step["status"] == "CANCELLED" for step in detail.json()["steps"])
        async with open_run_service() as service:
            child = await service.get_run(child_run_id)
        assert child is not None and child.status.value == "CANCELLED"
    finally:
        await task_runtime_service.stop()


def test_generated_code_policy_rejects_python_internal_access():
    from app.services.task_runtime_service import TaskBlocked, TaskRuntimeService

    with pytest.raises(TaskBlocked, match="Python internals"):
        TaskRuntimeService._validate_python_test(
            "def test_bad():\n    __builtins__['__import__']('os').system('whoami')\n",
            "tests/test_bad.py",
        )


def test_generated_code_policy_allows_url_parsing_but_blocks_network_imports():
    from app.services.task_runtime_service import TaskBlocked, TaskRuntimeService

    TaskRuntimeService._validate_python_test(
        "from urllib.parse import unquote, urlsplit\n\n"
        "def test_proxy_url():\n    assert urlsplit(unquote('https%3A%2F%2Fexample.test')).scheme == 'https'\n",
        "tests/test_proxy_url.py",
    )

    with pytest.raises(TaskBlocked, match="process/network/system-control"):
        TaskRuntimeService._validate_python_test(
            "from urllib.request import urlopen\n\ndef test_bad():\n    urlopen('https://example.test')\n",
            "tests/test_bad.py",
        )

    with pytest.raises(TaskBlocked, match="approved browser environment settings"):
        TaskRuntimeService._validate_python_test(
            "import os\n\ndef test_bad():\n    os.getenv('AWS_SECRET_ACCESS_KEY')\n",
            "tests/test_bad.py",
        )


@pytest.mark.asyncio
async def test_regression_task_executes_a_real_local_pytest_run(client):
    project = await client.post("/api/projects", json={"name": "Real Task Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_runtime_real.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_real_pytest_assertion():\n    assert 6 * 7 == 42\n", encoding="utf-8")

    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "RUN_REGRESSION",
                "goal": "Run the real local pytest assertion",
                "project_id": project_id,
                "workspace_id": project_id,
                "inputs": {
                    "nodeids": ["tests/test_runtime_real.py::test_real_pytest_assertion"],
                    "region": "local-test",
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        executed = next(step for step in body["steps"] if step["key"] == "run")
        assert executed["outputs"]["status"] == "PASSED"
        assert executed["outputs"]["passed"] == 1
        assert body["verification"]["verified"] is True
        async with open_run_service() as service:
            child_run = await service.get_run(executed["outputs"]["run_id"])
        assert child_run is not None and child_run.environment["QA_REGION"] == "local-test"
    finally:
        await task_runtime_service.stop()


@pytest.mark.asyncio
async def test_explore_task_uses_real_playwright_against_a_local_page(client):
    async def serve_page(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            body = b"<html><head><title>Task Browser Check</title></head><body><h1>Help</h1><a href='/details'>View details</a><button>Delete account</button></body></html>"
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve_page, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Inspect the help link without using destructive controls",
                "inputs": {"url": f"http://127.0.0.1:{port}/"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        assert body["verification"]["kind"] == "browser_exploration"
        inspect = next(step for step in body["steps"] if step["key"] == "inspect")
        assert inspect["outputs"]["title"] == "Task Browser Check"
        assert inspect["outputs"]["candidates"][1]["safe"] is False
        decision = body["decisions"][0]
        assert decision["choice"] == "0"
        assert decision["provider"] != "fake"
        assert body["evidence"]
        screenshot = next(item for item in body["artifacts"] if item["kind"] == "SCREENSHOT")
        downloaded = await client.get(f"/api/artifacts/{screenshot['artifact_id']}/download")
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        await task_runtime_service.stop()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_create_test_runs_browser_decision_approval_and_generated_pytest(client):
    async def serve_page(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            path = request.split(b" ", 2)[1]
            if path == b"/details":
                title, body_html = "Details", "<h1>Details</h1><p>Details: Account billing available</p>"
            else:
                title, body_html = (
                    "Task Browser Check",
                    "<h1>Help</h1><a href='/details'>View details</a><button>Delete account</button>",
                )
            body = f"<html><head><title>{title}</title></head><body>{body_html}</body></html>".encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    project = await client.post("/api/projects", json={"name": "Create Test Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    server = await asyncio.start_server(serve_page, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    steps = [
        {"action": "navigate", "url": url, "description": "Open the observed help page"},
        {
            "action": "click",
            "locator": {"kind": "role", "value": "link", "name": "View details", "exact": True},
            "description": "Open the observed details link",
        },
        {
            "action": "assert_text",
            "locator": {"kind": "text", "value": "Details: Account billing available", "exact": True},
            "value": "Details: Account billing available",
            "description": "Verify details content",
        },
    ]
    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "CREATE_TEST",
                "goal": "Verify the help page details link",
                "project_id": project_id,
                "workspace_id": workspace["id"],
                "inputs": {
                    "url": url,
                    "file_path": "tests/test_generated_help.py",
                    "test_name": "test_help_details",
                    "recorded_steps": steps,
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] == "WAITING":
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        assert any(step["key"] == "decide" and step["status"] == "COMPLETED" for step in waiting["steps"])
        assert waiting["decisions"] and waiting["decisions"][0]["provider"] != "fake"
        assert any(item["kind"] == "GENERATED_TEST" for item in waiting["artifacts"])

        approval = await client.post(
            f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed generated test"}
        )
        assert approval.status_code == 200, approval.text
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        run_step = next(step for step in body["steps"] if step["key"] == "run")
        assert run_step["outputs"]["status"] == "PASSED"
        assert body["verification"]["verified"] is True
        registered = next(step for step in body["steps"] if step["key"] == "register")
        assert registered["status"] == "COMPLETED"
        case_id = registered["outputs"]["test_case_id"]
        case = await client.get(f"/api/test-cases/{case_id}")
        assert case.status_code == 200 and case.json()["automation_status"] == "AUTOMATED"
        binding = await client.get(f"/api/test-cases/{case_id}/binding")
        assert binding.status_code == 200 and binding.json()["nodeid"] == run_step["outputs"]["nodeids"][0]
        assert any(event["type"] == "decision.created" for event in body["events"])
    finally:
        await task_runtime_service.stop()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_real_failure_record_repair_approval_and_targeted_rerun(client):
    project = await client.post("/api/projects", json={"name": "Failure Repair Runtime", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_repair_e2e.py"
    test_path.write_text(
        "def test_failure_is_repaired():\n    message = 'old'\n    assert message == 'new'\n",
        encoding="utf-8",
    )

    initial_run = await client.post(
        "/api/runs",
        json={
            "project_id": project_id,
            "workspace_id": project_id,
            "nodeids": ["tests/test_repair_e2e.py::test_failure_is_repaired"],
            "requested_by": "agent-task-e2e",
        },
    )
    assert initial_run.status_code == 201, initial_run.text
    run_id = initial_run.json()["id"]
    for _ in range(150):
        await asyncio.sleep(0.2)
        run = await client.get(f"/api/runs/{run_id}")
        if run.json()["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
            break
    assert run.json()["status"] == "FAILED", run.json()
    failures = await client.get(f"/api/failures?project_id={project_id}")
    assert failures.status_code == 200, failures.text
    failure = next(item for item in failures.json() if item["run_id"] == run_id)

    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "FIX_FAILURE",
                "goal": "Repair the observed assertion and rerun it",
                "project_id": project_id,
                "workspace_id": workspace["id"],
                "inputs": {"failure_id": failure["id"], "old_locator": "'old'", "proposed_locator": "'new'"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"WAITING", "COMPLETED", "FAILED", "BLOCKED"}:
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        classified = next(step for step in waiting["steps"] if step["key"] == "classify")
        assert classified["outputs"]["classification"] == "ASSERTION_FAILURE"
        diagnosed = next(step for step in waiting["steps"] if step["key"] == "diagnose")
        assert diagnosed["outputs"]["provider"] == "FailureClassifier"
        assert diagnosed["outputs"]["fallback_used"] is True
        assert waiting["evidence"]

        approved = await client.post(
            f"/api/tasks/{task_id}/approval",
            json={"approved": True, "comment": "Reviewed the evidence-backed one-line repair"},
        )
        assert approved.status_code == 200, approved.text
        for _ in range(200):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        assert "message = 'new'" in test_path.read_text(encoding="utf-8")
        target_run = next(step for step in body["steps"] if step["key"] == "target_run")
        assert target_run["outputs"]["status"] == "PASSED"
        assert body["verification"]["verified"] is True
    finally:
        await task_runtime_service.stop()


@pytest.mark.asyncio
async def test_review_task_uses_real_source_and_persists_findings(client):
    project = await client.post("/api/projects", json={"name": "Review Task Runtime", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_review_e2e.py"
    test_path.write_text("def test_review_has_an_assertion():\n    assert True\n", encoding="utf-8")

    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "REVIEW_TEST",
                "goal": "Review the test for meaningful assertions",
                "workspace_id": workspace["id"],
                "inputs": {"file_path": "tests/test_review_e2e.py"},
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(80):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        report = next(step for step in body["steps"] if step["key"] == "report")
        assert report["outputs"]["evidence_backed"] is True
        assert report["outputs"]["finding_count"] >= 1
        assert any(item["type"] == "SourceCode" for item in body["evidence"])
    finally:
        await task_runtime_service.stop()


@pytest.mark.asyncio
async def test_optimize_task_requires_approval_and_runs_the_proposed_refactor(client):
    project = await client.post("/api/projects", json={"name": "Optimize Task Runtime", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    workspace = (await client.get(f"/api/workspaces?project_id={project_id}")).json()[0]
    test_path = Path(settings.workspace_storage_dir) / project_id / "tests" / "test_optimize_e2e.py"
    test_path.write_text("def test_total():\n    assert (1 + 1) == 2\n", encoding="utf-8")
    proposal = "def test_total():\n    total = sum([1, 1])\n    assert total == 2\n"

    await task_runtime_service.start()
    try:
        created = await client.post(
            "/api/tasks",
            json={
                "type": "OPTIMIZE_TEST",
                "goal": "Improve readability without changing the test result",
                "workspace_id": workspace["id"],
                "inputs": {
                    "file_path": "tests/test_optimize_e2e.py",
                    "nodeids": ["tests/test_optimize_e2e.py::test_total"],
                    "proposed_code": proposal,
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        for _ in range(100):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"WAITING", "COMPLETED", "FAILED", "BLOCKED"}:
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        assert any(item["kind"] == "PATCH_PROPOSAL" for item in waiting["artifacts"])
        approved = await client.post(
            f"/api/tasks/{task_id}/approval", json={"approved": True, "comment": "Reviewed the focused refactor"}
        )
        assert approved.status_code == 200, approved.text
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        body = detail.json()
        assert body["status"] == "COMPLETED", body.get("failure_reason")
        assert "total = sum([1, 1])" in test_path.read_text(encoding="utf-8")
        assert body["verification"]["verified"] is True
    finally:
        await task_runtime_service.stop()
