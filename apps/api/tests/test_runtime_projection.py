from datetime import timedelta

import pytest
from app.persistence.models import TaskORM, TaskStepORM, TestRunORM, utc_now
from app.services.runtime_projection import RuntimeProjection


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "COMPLETED", "FAILED"])
async def test_task_projection_is_read_only_and_handles_empty_historical_data(test_db_session, status):
    async with test_db_session() as session:
        task = TaskORM(id="task", owner_id="owner", type="EXPLORE_PAGE", goal="Inspect", status=status)
        session.add(task)
        await session.commit()
        before = task.updated_at
        snapshot = await RuntimeProjection(session).task("task", "owner")
        assert snapshot.status == status
        assert snapshot.steps == [] and snapshot.runs == []
        assert snapshot.started_at is None and snapshot.duration_ms is None
        assert not session.new and not session.dirty and not session.deleted
        assert task.updated_at == before
        assert await RuntimeProjection(session).task("task", "another-owner") is None
        assert await RuntimeProjection(session).run("missing", "owner") is None


async def test_task_step_projection_has_real_dependencies_and_no_large_or_secret_payloads(test_db_session):
    now = utc_now()
    async with test_db_session() as session:
        session.add(TaskORM(id="task", owner_id="owner", type="EXPLORE_PAGE", goal="Inspect", status="RUNNING"))
        await session.flush()
        session.add_all(
            [
                TaskStepORM(
                    id="inspect",
                    task_id="task",
                    key="inspect",
                    name="Inspect",
                    tool="browser.inspect",
                    status="COMPLETED",
                    started_at=now,
                    finished_at=now + timedelta(seconds=2),
                    duration_ms=2000,
                    inputs={"cookie": "private", "prompt": "hidden"},
                    outputs={"content": "x" * 100000},
                ),
                TaskStepORM(
                    id="decide",
                    position=1,
                    task_id="task",
                    key="decide",
                    name="Decide",
                    tool="decision.select",
                    status="PENDING",
                    dependencies=["inspect"],
                ),
            ]
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("task", "owner")
        assert snapshot.summary.completed_steps == 1
        assert snapshot.summary.next_step_ids == ["decide"]
        assert snapshot.steps[1].dependencies == ["inspect"]
        assert snapshot.steps[0].duration_ms == 2000
        assert "private" not in snapshot.model_dump_json()
        assert "hidden" not in snapshot.model_dump_json()
        assert len(snapshot.model_dump_json()) < 5000


async def test_legacy_context_is_explicit_and_ambiguous_or_foreign_project_links_are_not_guessed(
    client, test_db_session
):
    project = (await client.post("/api/projects", json={"name": "runtime projection"})).json()
    async with test_db_session() as session:
        session.add(TestRunORM(id="run", project_id=project["id"], workspace_id=project["id"], status="PASSED"))
        session.add(
            TaskORM(
                id="task",
                owner_id="owner",
                project_id=project["id"],
                type="RUN_REGRESSION",
                goal="Run",
                status="COMPLETED",
                context={"run_id": "run"},
            )
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("task", "owner")
        assert snapshot.runs[0].relationship_source == "legacy_context"
        assert (await RuntimeProjection(session).run("run", "owner")).task.id == "task"
        session.add(
            TaskORM(
                id="second",
                owner_id="owner",
                project_id=project["id"],
                type="RUN_REGRESSION",
                goal="Run",
                context={"run_id": "run"},
            )
        )
        await session.commit()
        assert (await RuntimeProjection(session).run("run", "owner")).task is None
        assert not session.dirty


async def test_ai_lane_uses_recorded_task_identity_and_duration_without_claiming_test_run(test_db_session):
    from app.persistence.models import AIInvocationORM

    now = utc_now()
    async with test_db_session() as session:
        session.add(TaskORM(id="task", owner_id="owner", type="EXPLORE_PAGE", goal="Inspect"))
        session.add(
            AIInvocationORM(
                id="ai",
                task_id="task",
                run_id="trace-only",
                task="review",
                provider="local-policy",
                model="ast",
                started_at=now,
                duration_ms=1500,
            )
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("task", "owner")
        assert snapshot.summary.ai_calls == 1
        span = snapshot.ai_invocations[0]
        assert span.test_run_id is None and span.step_id is None
        assert span.finished_at - span.started_at == timedelta(milliseconds=1500)
        assert span.timestamp_source == "derived" and not session.dirty


async def test_legacy_matching_tolerates_malformed_json_and_rejects_cross_owner_ambiguity(client, test_db_session):
    from sqlalchemy import text

    project = (await client.post("/api/projects", json={"name": "Legacy safety"})).json()
    async with test_db_session() as session:
        session.add(TestRunORM(id="legacy-run", project_id=project["id"], workspace_id=project["id"]))
        session.add_all(
            [
                TaskORM(
                    id="valid",
                    owner_id="owner",
                    project_id=project["id"],
                    type="RUN_REGRESSION",
                    goal="Run",
                    context={"run_id": "legacy-run"},
                ),
                TaskORM(
                    id="bad-json",
                    owner_id="owner",
                    project_id=project["id"],
                    type="RUN_REGRESSION",
                    goal="Corrupt legacy",
                ),
            ]
        )
        await session.commit()
        await session.execute(
            text("UPDATE agent_tasks SET context=:value WHERE id='bad-json'"),
            {"value": "broken JSON mentions legacy-run"},
        )
        await session.commit()
        assert (await RuntimeProjection(session).run("legacy-run", "owner")).task.id == "valid"
        session.add(
            TaskORM(
                id="other-owner",
                owner_id="other",
                project_id=project["id"],
                type="RUN_REGRESSION",
                goal="Conflict",
                context={"run_id": "legacy-run"},
            )
        )
        await session.commit()
        assert (await RuntimeProjection(session).run("legacy-run", "owner")).task is None
        assert (await RuntimeProjection(session).task("valid", "owner")).runs == []
        assert not session.dirty


async def test_failure_analysis_stage_identity_is_not_a_taskstep(client, test_db_session):
    from app.persistence.models import FailureAnalysisORM, FailureRecordORM, TestExecutionORM

    project = (await client.post("/api/projects", json={"name": "Analysis identity"})).json()
    async with test_db_session() as session:
        session.add(
            TaskORM(id="analysis-task", owner_id="owner", project_id=project["id"], type="RUN_REGRESSION", goal="Run")
        )
        await session.flush()
        session.add(
            TestRunORM(id="analysis-run", task_id="analysis-task", project_id=project["id"], workspace_id=project["id"])
        )
        await session.flush()
        session.add(
            TestExecutionORM(id="execution", run_id="analysis-run", nodeid="test_a.py::test_a", status="FAILED")
        )
        await session.flush()
        session.add(
            FailureRecordORM(
                id="failure",
                run_id="analysis-run",
                execution_id="execution",
                test_nodeid="test_a.py::test_a",
                test_name="test_a",
            )
        )
        await session.flush()
        session.add(
            FailureAnalysisORM(
                id="analysis",
                failure_id="failure",
                events=[
                    {
                        "event_id": "e",
                        "run_id": "analysis-trace",
                        "type": "workflow.step",
                        "step_id": "analysis:diagnosis",
                        "stage": "diagnosis",
                        "title": "Actual analysis",
                        "status": "COMPLETED",
                    }
                ],
            )
        )
        await session.commit()
        snapshot = await RuntimeProjection(session).task("analysis-task", "owner")
        analysis_event = next(event for event in snapshot.events if event.source == "ai")
        assert analysis_event.step_id is None
        assert analysis_event.trace_run_id == "analysis-trace"
        assert snapshot.steps == [] and not session.dirty
