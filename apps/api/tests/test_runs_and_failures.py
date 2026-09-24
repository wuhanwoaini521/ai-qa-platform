from datetime import timedelta

import pytest
from app.persistence.models import utc_now
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from httpx import AsyncClient
from project_model.models import RunStatus, TestRunCreate

pytestmark = pytest.mark.integration


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
