from __future__ import annotations

import asyncio

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import (
    ProjectORM,
    TaskORM,
    TaskStepORM,
    TeamMemberORM,
    TeamORM,
    UserORM,
    WorkflowDefinitionORM,
    WorkflowDefinitionVersionORM,
)
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_run_repo import TestRunRepository
from app.services.task_runtime_service import TaskRuntimeService
from conftest import bearer_client, login_token
from project_model.models import RunStatus
from project_model.models import TestRunCreate as RunCreate
from project_model.task_models import TaskStatus, TaskStepSpec, TaskType
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _graph(*, classify: bool = True) -> dict:
    nodes = [{"key": "collect_custom", "kind": "failure.collect", "inputs": {"failure_id": {"$input": "failure_id"}}}]
    edges = []
    if classify:
        nodes.append(
            {
                "key": "classify_custom",
                "kind": "failure.classify",
                "inputs": {"failure_id": {"$output": "collect_custom.id"}},
            }
        )
        edges.append({"source": "collect_custom", "target": "classify_custom"})
    return {"nodes": nodes, "edges": edges}


async def _published_workflow(
    client, project_id: str, graph: dict | None = None, *, name: str = "Safe failure workflow"
) -> tuple[str, dict]:
    created = await client.post(f"/api/projects/{project_id}/workflows", json={"name": name, "description": ""})
    assert created.status_code == 201, created.text
    definition_id = created.json()["id"]
    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=graph or _graph())
    assert saved.status_code == 200 and saved.json()["issues"] == []
    published = await client.post(f"/api/workflows/{definition_id}/publish")
    assert published.status_code == 200, published.text
    return definition_id, published.json()["published"]


async def _failure(session_factory, project_id: str, *, failure_id_suffix: str = "") -> str:
    async with session_factory() as session:
        runs = TestRunRepository(session)
        run = await runs.create_run(RunCreate(project_id=project_id, workspace_id=project_id))
        execution = await runs.add_execution(
            run_id=run.id,
            nodeid="tests/test_checkout.py::test_checkout",
            status=RunStatus.FAILED,
            error_message="assert 1 == 2",
            stack_trace="AssertionError: assert 1 == 2",
        )
        failure = await runs.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid="tests/test_checkout.py::test_checkout",
            test_name="test_checkout",
            classification="ASSERTION_FAILURE",
            exception_type="AssertionError",
            error_message="assert 1 == 2",
            stack_trace="AssertionError: assert 1 == 2",
        )
        await session.commit()
        return failure.id


async def _project(client, name: str) -> str:
    response = await client.post("/api/projects", json={"name": name, "bootstrap_workspace": False})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def test_published_workflow_launch_runs_its_exact_plan_and_replays_idempotently(client, test_db_session):
    project_id = await _project(client, "Workflow launch")
    definition_id, published = await _published_workflow(client, project_id)
    failure_id = await _failure(test_db_session, project_id)
    key = "workflow-launch-replay-01"

    launched = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": failure_id}},
        headers={"Idempotency-Key": key},
    )
    assert launched.status_code == 202, launched.text
    launch = launched.json()
    assert launch["version_id"] == published["id"]
    assert launch["version"] == published["version"]
    assert launch["checksum"] == published["checksum"]

    replay = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": failure_id}},
        headers={"Idempotency-Key": key},
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["task_id"] == launch["task_id"]
    assert replay.json()["execution_id"] == launch["execution_id"]

    async with test_db_session() as session:
        task = await session.get(TaskORM, launch["task_id"])
        steps = list(
            (
                await session.execute(
                    select(TaskStepORM).where(TaskStepORM.task_id == launch["task_id"]).order_by(TaskStepORM.position)
                )
            ).scalars()
        )
    assert task.type == TaskType.WORKFLOW_EXECUTION.value
    assert task.max_retries == task.max_replans == task.max_ai_calls == 0
    from app.settings import get_config

    assert task.max_duration_seconds == int(get_config().agent.max_runtime_seconds)
    assert task.workflow_definition_id == definition_id
    assert task.workflow_version_id == published["id"]
    assert task.workflow_checksum == published["checksum"]
    assert [(step.key, step.tool, step.inputs) for step in steps] == [
        ("collect_custom", "failure.collect", {"failure_id": failure_id}),
        ("classify_custom", "failure.classify", {"failure_id": {"$output": "collect_custom.id"}}),
    ]

    runtime = get_task_runtime_service()
    assert await runtime.scheduler._claim(launch["task_id"])
    await runtime.scheduler._execute_task(launch["task_id"])
    detail = await runtime.commands.get(launch["task_id"], str((await client.get("/api/auth/me")).json()["user"]["id"]))
    assert detail is not None and detail.status == TaskStatus.COMPLETED
    assert [step.status.value for step in detail.steps] == ["COMPLETED", "COMPLETED"]
    assert detail.steps[0].outputs["id"] == failure_id
    assert detail.steps[1].outputs["classification"]

    trace = await client.get(f"/api/tasks/{launch['task_id']}/execution-trace")
    assert trace.status_code == 200, trace.text
    assert trace.json()["workflow_execution_id"] == launch["execution_id"]
    assert trace.json()["workflow_version_id"] == published["id"]
    assert trace.json()["workflow_checksum"] == published["checksum"]


async def test_workflow_launch_requires_run_permission_and_project_scoped_failure(client, test_db_session):
    project_id = await _project(client, "Workflow launch ACL")
    definition_id, published = await _published_workflow(client, project_id, _graph(classify=False))
    failure_id = await _failure(test_db_session, project_id)
    project_team = TeamORM(id="team_workflow_launch", name="Workflow Launch")
    async with test_db_session() as session:
        user_id = (await client.get("/api/auth/me")).json()["user"]["id"]
        viewer = await client.post(
            "/api/users",
            json={
                "email": "workflow.launch.viewer@example.com",
                "full_name": "Viewer",
                "role": "VIEWER",
                "password": "pw-123456",
            },
        )
        assert viewer.status_code == 201, viewer.text
        session.add(project_team)
        await session.flush()
        session.add_all(
            [
                TeamMemberORM(id="tm_workflow_launch_admin", team_id=project_team.id, user_id=user_id),
                TeamMemberORM(id="tm_workflow_launch_viewer", team_id=project_team.id, user_id=viewer.json()["id"]),
            ]
        )
        await session.commit()
    assert (await client.patch(f"/api/projects/{project_id}", json={"team_id": project_team.id})).status_code == 200
    email, password = "workflow.launch.viewer@example.com", "pw-123456"
    token = await login_token(client, email, password)
    from_client = bearer_client(token)
    async with from_client:
        response = await from_client.post(
            f"/api/workflows/{definition_id}/execute",
            json={"version": published["version"], "inputs": {"failure_id": failure_id}},
            headers={"Idempotency-Key": "workflow-launch-no-permission"},
        )
        assert response.status_code == 403

    other_project = await _project(client, "Other Workflow launch ACL")
    foreign_failure = await _failure(test_db_session, other_project)
    response = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": foreign_failure}},
        headers={"Idempotency-Key": "workflow-launch-foreign-failure"},
    )
    assert response.status_code == 422


async def test_workflow_idempotent_replay_survives_deleted_failure(client, test_db_session):
    from app.persistence.models import FailureRecordORM, TestRunORM
    from app.services import task_command_service
    from app.settings import get_config

    project_id = await _project(client, "Workflow replay after failure deletion")
    definition_id, published = await _published_workflow(client, project_id, _graph(classify=False))
    failure_id = await _failure(test_db_session, project_id)
    other_failure_id = await _failure(test_db_session, project_id)
    headers = {"Idempotency-Key": "workflow-deleted-failure-replay"}
    body = {"version": published["version"], "inputs": {"failure_id": failure_id}}

    first = await client.post(f"/api/workflows/{definition_id}/execute", json=body, headers=headers)
    assert first.status_code == 202, first.text
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        run = await session.get(TestRunORM, failure.run_id)
        await session.delete(failure)
        await session.delete(run)
        await session.commit()

    replay = await client.post(f"/api/workflows/{definition_id}/execute", json=body, headers=headers)
    assert replay.status_code == 202, replay.text
    assert replay.json()["task_id"] == first.json()["task_id"]
    assert replay.json()["execution_id"] == first.json()["execution_id"]

    current = get_config()
    limited = current.model_copy(update={"agent": current.agent.model_copy(update={"max_steps": 1})})
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(task_command_service, "get_config", lambda: limited)
    try:
        budget_replay = await client.post(f"/api/workflows/{definition_id}/execute", json=body, headers=headers)
    finally:
        monkeypatch.undo()
    assert budget_replay.status_code == 202, budget_replay.text
    assert budget_replay.json()["task_id"] == first.json()["task_id"]

    conflicting = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": other_failure_id}},
        headers=headers,
    )
    assert conflicting.status_code == 409, conflicting.text
    async with test_db_session() as session:
        task_ids = list(
            (await session.execute(select(TaskORM.id).where(TaskORM.workflow_definition_id == definition_id))).scalars()
        )
    assert task_ids == [first.json()["task_id"]]


async def test_workflow_idempotency_covers_version_changes_and_conflicting_inputs(client, test_db_session):
    project_id = await _project(client, "Workflow idempotency conflict")
    definition_id, published = await _published_workflow(client, project_id, _graph(classify=False))
    failure_one = await _failure(test_db_session, project_id)
    failure_two = await _failure(test_db_session, project_id)
    headers = {"Idempotency-Key": "workflow-conflict-key-01"}
    body = {"inputs": {"failure_id": failure_one}}
    first = await client.post(f"/api/workflows/{definition_id}/execute", json=body, headers=headers)
    assert first.status_code == 202, first.text
    conflicting_inputs = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": failure_two}},
        headers=headers,
    )
    assert conflicting_inputs.status_code == 409, conflicting_inputs.text
    invalid_changed_inputs = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {}},
        headers=headers,
    )
    assert invalid_changed_inputs.status_code == 409, invalid_changed_inputs.text

    saved = await client.put(
        f"/api/workflows/{definition_id}/draft",
        json={"nodes": _graph(classify=False)["nodes"], "edges": [], "base_checksum": published["checksum"]},
    )
    assert saved.status_code == 200, saved.text
    next_published = await client.post(f"/api/workflows/{definition_id}/publish")
    assert next_published.status_code == 200, next_published.text

    changed_version = await client.post(f"/api/workflows/{definition_id}/execute", json=body, headers=headers)
    assert changed_version.status_code == 202, changed_version.text
    assert changed_version.json()["task_id"] == first.json()["task_id"]
    async with test_db_session() as session:
        task_ids = (
            (await session.execute(select(TaskORM.id).where(TaskORM.workflow_definition_id == definition_id)))
            .scalars()
            .all()
        )
    assert task_ids == [first.json()["task_id"]]


async def test_workflow_launch_concurrent_replays_share_the_database_winner(test_db_session):
    plan = [TaskStepSpec(key="collect", name="Collect", tool="failure.collect")]
    project_id = "project-concurrent"
    owner_id = "owner-concurrent"
    definition_id = "definition-concurrent"
    version_id = "version-concurrent"
    async with test_db_session() as session:
        session.add_all(
            [
                UserORM(id=owner_id, email="workflow-concurrent@example.com", full_name="Concurrent Owner"),
                ProjectORM(id=project_id, name="Concurrent Workflow Project"),
            ]
        )
        await session.flush()
        session.add(
            WorkflowDefinitionORM(
                id=definition_id,
                project_id=project_id,
                name="Concurrent Workflow",
                created_by=owner_id,
            )
        )
        await session.flush()
        session.add(
            WorkflowDefinitionVersionORM(
                id=version_id,
                definition_id=definition_id,
                project_id=project_id,
                version=1,
                state="PUBLISHED",
                graph=_graph(classify=False),
                checksum="b" * 64,
                created_by=owner_id,
                published_by=owner_id,
            )
        )
        await session.commit()

    arguments = {
        "project_id": project_id,
        "owner_id": owner_id,
        "goal": "Concurrent workflow",
        "inputs": {"failure_id": "failure-concurrent"},
        "plan": plan,
        "node_kinds": {"failure.collect": "collect"},
        "definition_id": definition_id,
        "version_id": version_id,
        "version": 1,
        "checksum": "b" * 64,
        "idempotency_key": "concurrent-workflow-key",
    }
    services = [
        TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory(test_db_session)),
        TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory(test_db_session)),
    ]
    first, second = await asyncio.gather(*(service.commands.create_workflow(**arguments) for service in services))
    assert first.id == second.id

    # When publication changes after both requests miss the API replay lookup, the database winner
    # still represents the same unversioned request and must be replayed.
    publish_race_arguments = {
        **arguments,
        "idempotency_key": "concurrent-workflow-publish-race",
        "requested_version": None,
    }
    newer_version_arguments = {
        **publish_race_arguments,
        "version_id": "workflow-version-2",
        "version": 2,
        "checksum": "c" * 64,
    }
    race_first, race_second = await asyncio.gather(
        services[0].commands.create_workflow(**publish_race_arguments),
        services[1].commands.create_workflow(**newer_version_arguments),
    )
    assert race_first.id == race_second.id

    conflicting_arguments = {
        **arguments,
        "idempotency_key": "concurrent-workflow-conflict-key",
    }
    changed_arguments = {
        **conflicting_arguments,
        "inputs": {"failure_id": "different-failure"},
    }
    results = await asyncio.gather(
        services[0].commands.create_workflow(**conflicting_arguments),
        services[1].commands.create_workflow(**changed_arguments),
        return_exceptions=True,
    )
    successes = [result for result in results if not isinstance(result, BaseException)]
    errors = [result for result in results if isinstance(result, BaseException)]
    assert len(successes) == len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert "different Workflow inputs" in str(errors[0])
    async with test_db_session() as session:
        conflict_rows = (
            (
                await session.execute(
                    select(TaskORM).where(TaskORM.workflow_idempotency_key == conflicting_arguments["idempotency_key"])
                )
            )
            .scalars()
            .all()
        )
    assert len(conflict_rows) == 1


async def test_published_workflow_eligibility_respects_current_step_budget(client, monkeypatch):
    from app.services import workflow_definition_service
    from app.settings import get_config

    current = get_config()
    limited = current.model_copy(update={"agent": current.agent.model_copy(update={"max_steps": 1})})
    monkeypatch.setattr(workflow_definition_service, "get_config", lambda: limited)
    project_id = await _project(client, "Workflow detail step budget")
    definition_id, _ = await _published_workflow(client, project_id, _graph())

    response = await client.get(f"/api/workflows/{definition_id}")

    assert response.status_code == 200, response.text
    execution = response.json()["published"]["execution"]
    assert execution["eligible"] is False
    assert any("max_steps" in issue["message"] for issue in execution["issues"])


async def test_workflow_launch_rejects_plan_over_configured_step_budget(client, test_db_session, monkeypatch):
    from app.services import task_command_service
    from app.settings import get_config

    current = get_config()
    limited = current.model_copy(update={"agent": current.agent.model_copy(update={"max_steps": 1})})
    monkeypatch.setattr(task_command_service, "get_config", lambda: limited)
    project_id = await _project(client, "Workflow step budget")
    definition_id, published = await _published_workflow(client, project_id, _graph())
    failure_id = await _failure(test_db_session, project_id)

    response = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": failure_id}},
        headers={"Idempotency-Key": "workflow-step-budget-01"},
    )

    assert response.status_code == 422
    assert "max_steps" in response.text
    async with test_db_session() as session:
        task_ids = list(
            (await session.execute(select(TaskORM.id).where(TaskORM.workflow_definition_id == definition_id))).scalars()
        )
    assert task_ids == [], "over-budget Workflow was persisted for runtime execution"


async def test_workflow_launch_respects_runtime_disabled_and_duration_cap(client, test_db_session, monkeypatch):
    from app.services import task_command_service
    from app.settings import get_config

    current = get_config()
    empty_plan = [TaskStepSpec(key="collect", name="Collect", tool="failure.collect")]
    disabled = current.model_copy(update={"agent": current.agent.model_copy(update={"enabled": False})})
    monkeypatch.setattr(task_command_service, "get_config", lambda: disabled)
    with pytest.raises(ValueError, match="execution is disabled"):
        await get_task_runtime_service().commands.create_workflow(
            project_id="project",
            owner_id="owner",
            goal="Disabled workflow",
            inputs={},
            plan=empty_plan,
            node_kinds={},
            definition_id="definition",
            version_id="version",
            version=1,
            checksum="a" * 64,
            idempotency_key="disabled-workflow-key",
        )

    limited = current.model_copy(update={"agent": current.agent.model_copy(update={"max_runtime_seconds": 120})})
    monkeypatch.setattr(task_command_service, "get_config", lambda: limited)
    project_id = await _project(client, "Workflow duration cap")
    definition_id, published = await _published_workflow(client, project_id, _graph(classify=False))
    failure_id = await _failure(test_db_session, project_id)
    response = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {"failure_id": failure_id}},
        headers={"Idempotency-Key": "workflow-duration-cap-01"},
    )
    assert response.status_code == 202, response.text
    async with test_db_session() as session:
        task = await session.get(TaskORM, response.json()["task_id"])
    assert task.max_duration_seconds == 120


async def test_workflow_launch_rejects_missing_or_unsafe_bindings(client, test_db_session):
    project_id = await _project(client, "Workflow launch bindings")
    definition_id, published = await _published_workflow(client, project_id, _graph(classify=False))
    headers = {"Idempotency-Key": "workflow-missing-input-01"}
    missing = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published["version"], "inputs": {}},
        headers=headers,
    )
    assert missing.status_code == 422

    failure_id = await _failure(test_db_session, project_id)
    unsafe_definition, unsafe_published = await _published_workflow(
        client,
        project_id,
        {"nodes": [{"key": "run", "kind": "tests.run_target"}], "edges": []},
        name="Unsafe workflow",
    )
    refused = await client.post(
        f"/api/workflows/{unsafe_definition}/execute",
        json={"version": unsafe_published["version"], "inputs": {"failure_id": failure_id}},
        headers={"Idempotency-Key": "workflow-unsafe-node-01"},
    )
    assert refused.status_code == 422
    assert "FORBIDDEN" in refused.text and "tests.run_target" in refused.text
