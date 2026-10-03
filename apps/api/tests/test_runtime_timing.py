from datetime import timedelta

from app.persistence.models import TaskORM, TaskStepORM, TestRunORM
from app.repositories.task_repo import TaskRepository
from app.repositories.test_run_repo import TestRunRepository
from project_model.models import RunStatus


async def test_new_execution_has_nonzero_derived_span(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Timing"})).json()
    async with test_db_session() as session:
        session.add(TestRunORM(id="run", project_id=project["id"], workspace_id=project["id"]))
        await session.flush()
        execution = await TestRunRepository(session).add_execution("run", "test_a", RunStatus.PASSED, duration_ms=1200)
        assert execution.finished_at - execution.started_at == timedelta(milliseconds=1200)
        assert execution.timestamp_source == "derived"


async def test_event_step_identity_is_owned_and_context_is_parallel_safe(test_db_session):
    import asyncio

    from app.services.task_runtime_service import active_runtime_step

    async with test_db_session() as session:
        session.add_all(
            [
                TaskORM(id="a", owner_id="owner", type="EXPLORE_PAGE", goal="A"),
                TaskORM(id="b", owner_id="owner", type="EXPLORE_PAGE", goal="B"),
            ]
        )
        await session.flush()
        session.add(TaskStepORM(id="s", task_id="a", key="inspect", name="Inspect", tool="browser.inspect"))
        await session.flush()
        repo = TaskRepository(session)
        assert (await repo.add_event("a", "step.started", {"step_id": "s"})).step_id == "s"
        assert (await repo.add_event("b", "step.started", {"step_id": "s"})).step_id is None

    async def child(value):
        token = active_runtime_step.set(value)
        try:
            await asyncio.sleep(0)
            return active_runtime_step.get()
        finally:
            active_runtime_step.reset(token)

    assert await asyncio.gather(child("s1"), child("s2")) == ["s1", "s2"]
    assert active_runtime_step.get() is None
