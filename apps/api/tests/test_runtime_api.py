import pytest
from app.persistence.models import TaskEventORM, TaskORM, TaskStepORM, utc_now
from app.services.auth_service import AuthService


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "COMPLETED", "FAILED"])
async def test_runtime_api_is_owned_read_only_and_handles_nulls(client, test_db_session, status):
    me = await AuthService().authenticate_token_or_key(client.headers.get("Authorization"))
    owner = str(me[0].id)
    async with test_db_session() as session:
        session.add(TaskORM(id="runtime-task", owner_id=owner, type="EXPLORE_PAGE", goal="Inspect", status=status))
        await session.commit()
        baseline = (await session.get(TaskORM, "runtime-task")).updated_at
    response = await client.get("/api/agent-tasks/runtime-task/runtime")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == status and data["steps"] == [] and data["runs"] == []
    assert data["started_at"] is None and data["events"] == []
    async with test_db_session() as session:
        assert (await session.get(TaskORM, "runtime-task")).updated_at == baseline
        assert not session.new and not session.dirty
    assert (await client.get("/api/runs/absent/runtime")).status_code == 404


async def test_runtime_api_preserves_durable_event_ids_and_legacy_task_endpoint(client, test_db_session):
    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "Inspect the local help page", "inputs": {"url": "http://127.0.0.1:1/"}},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    async with test_db_session() as session:
        session.add(
            TaskEventORM(
                task_id=task_id,
                type="step.failed",
                payload={"step_id": "real-step", "prompt": "hidden", "authorization": "Bearer private"},
                created_at=utc_now(),
            )
        )
        await session.commit()
    response = await client.get(f"/api/tasks/{task_id}/runtime")
    assert response.status_code == 200
    data = response.json()
    assert data["events"][-1]["step_id"] is None  # Unrecorded IDs cannot become selectable nodes.
    assert data["event_cursor"] > 0
    assert "hidden" not in response.text and "private" not in response.text


async def test_other_owner_cannot_read_task_projection(client, test_db_session):
    async with test_db_session() as session:
        session.add(TaskORM(id="foreign", owner_id="other", type="EXPLORE_PAGE", goal="Private"))
        await session.commit()
    assert (await client.get("/api/tasks/foreign/runtime")).status_code == 404


async def test_step_detail_has_owned_access_and_whitelists_nested_outputs(client, test_db_session):
    me = await AuthService().authenticate_token_or_key(client.headers.get("Authorization"))
    async with test_db_session() as session:
        session.add(TaskORM(id="detail-task", owner_id=str(me[0].id), type="EXPLORE_PAGE", goal="Inspect"))
        await session.flush()
        session.add(
            TaskStepORM(
                id="detail-step",
                task_id="detail-task",
                key="inspect",
                name="Inspect",
                tool="browser.inspect",
                outputs={
                    "url": "https://user:pass@example.com/?secret=hidden",
                    "prompt": "private",
                    "reasoning": "hidden thoughts",
                    "candidate": {"locator": "#public", "cookie": "private"},
                    "candidates": [{"score": 0.9}],
                },
            )
        )
        await session.commit()
    response = await client.get("/api/tasks/detail-task/runtime/steps/detail-step")
    assert response.status_code == 200
    assert response.json()["outputs"] == {
        "url": "https://example.com/",
        "candidate": {"locator": "#public"},
        "candidate_count": 1,
    }
    assert "private" not in response.text and "thoughts" not in response.text
    assert (await client.get("/api/tasks/another/runtime/steps/detail-step")).status_code == 404
