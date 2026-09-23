from datetime import timedelta

import pytest
from app.persistence.models import TestRunORM, utc_now
from httpx import AsyncClient
from project_model.models import RunStatus

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
    run = await client.post("/api/runs", json={"project_id": project_id, "workspace_id": project_id})
    run_id = run.json()["id"]

    # Simulate a run abandoned long ago by moving its creation time into the past.
    async with test_db_session() as session:
        orm = await session.get(TestRunORM, run_id)
        orm.status = RunStatus.RUNNING.value
        orm.created_at = utc_now() - timedelta(minutes=10)
        await session.commit()

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
