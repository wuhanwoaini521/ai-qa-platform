from app.persistence.models import TaskORM, TestRunORM
from app.services.runtime_projection import RuntimeProjection


async def test_foreign_key_wins_over_legacy_context_and_ancestors_are_explicit(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Relationships"})).json()
    async with test_db_session() as session:
        session.add_all(
            [
                TaskORM(
                    id="task",
                    owner_id="owner",
                    project_id=project["id"],
                    type="RUN_REGRESSION",
                    goal="Run",
                    context={"run_id": "legacy"},
                ),
                TaskORM(id="other", owner_id="owner", project_id=project["id"], type="RUN_REGRESSION", goal="Other"),
            ]
        )
        await session.flush()
        session.add(TestRunORM(id="root", project_id=project["id"], workspace_id=project["id"]))
        await session.flush()
        session.add(
            TestRunORM(
                id="retry", project_id=project["id"], workspace_id=project["id"], task_id="task", parent_run_id="root"
            )
        )
        session.add(TestRunORM(id="legacy", project_id=project["id"], workspace_id=project["id"], task_id="other"))
        await session.commit()
        snapshot = await RuntimeProjection(session).task("task", "owner")
        assert [run.id for run in snapshot.runs] == ["retry"]
        assert snapshot.runs[0].relationship_source == "foreign_key"
        assert [run.id for run in snapshot.run_ancestors] == ["root"]
        assert snapshot.summary.retries == 1
        assert (await RuntimeProjection(session).run("retry", "owner")).task.id == "task"
        assert (await RuntimeProjection(session).run("retry", "someone")).task is None
        assert not session.dirty


async def test_retry_rejects_foreign_parent_and_unrelated_origin_before_execution(client):
    project = (await client.post("/api/projects", json={"name": "Retry validation"})).json()
    response = await client.post(
        "/api/runs", json={"project_id": project["id"], "workspace_id": project["id"], "parent_run_id": "missing"}
    )
    assert response.status_code == 422


async def test_running_child_links_to_actual_step_before_outputs_exist(client, test_db_session):
    from app.persistence.models import TaskEventORM, TaskStepORM, TestExecutionORM, utc_now

    project = (await client.post("/api/projects", json={"name": "Live relationship"})).json()
    async with test_db_session() as session:
        session.add(
            TaskORM(
                id="live-task",
                owner_id="owner",
                project_id=project["id"],
                type="RUN_REGRESSION",
                goal="Run",
                status="RUNNING",
            )
        )
        await session.flush()
        session.add(
            TaskStepORM(
                id="live-step",
                task_id="live-task",
                key="run",
                name="Run tests",
                tool="tests.run_regression",
                status="RUNNING",
            )
        )
        session.add(
            TestRunORM(
                id="live-run",
                task_id="live-task",
                project_id=project["id"],
                workspace_id=project["id"],
                status="RUNNING",
            )
        )
        await session.flush()
        session.add(
            TaskEventORM(
                task_id="live-task",
                step_id="live-step",
                type="step.progress",
                payload={"type": "child_run.started", "run_id": "live-run", "step_id": "live-step"},
            )
        )
        session.add(
            TestExecutionORM(
                id="live-execution",
                run_id="live-run",
                nodeid="test_a.py::test_a",
                status="PASSED",
                finished_at=utc_now(),
            )
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("live-task", "owner")
        assert snapshot.runs[0].step_id == "live-step"
        assert next(event for event in snapshot.events if event.type == "test.completed").step_id == "live-step"
        assert not session.dirty
    response = await client.post(
        "/api/runs", json={"project_id": project["id"], "workspace_id": project["id"], "origin_failure_id": "missing"}
    )
    assert response.status_code == 422
