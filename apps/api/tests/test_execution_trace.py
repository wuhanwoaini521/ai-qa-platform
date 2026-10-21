"""The execution tree only shows rows that exist, and it never guesses a missing fact.

Every node must be traceable to a stored row, every edge must land on a real node, and a fact the
server cannot establish must be reported as unknown instead of being filled in.
"""

from __future__ import annotations

import pytest
from app.persistence.models import (
    AIInvocationORM,
    ArtifactORM,
    TaskArtifactORM,
    TaskEvidenceORM,
    TaskORM,
    TaskStepORM,
    TestRunORM,
)
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def _user_id(client) -> str:
    response = await client.get("/api/auth/me")
    assert response.status_code == 200, response.text
    return response.json()["user"]["id"]


async def _seed_task(session, *, owner_id: str, project_id: str, task_id: str = "task_trace") -> None:
    session.add(
        TaskORM(
            id=task_id,
            type="ANALYZE_DISCOVERY",
            goal="Read the unsettled scenarios and propose what a human should write",
            status="COMPLETED",
            owner_id=owner_id,
            project_id=project_id,
            inputs={"discovery_run_id": "qd_trace", "api_token": "should-not-leak"},
            context={},
            verification={"all_steps_terminal": True},
            created_at=None,
        )
    )
    await session.flush()


async def _trace(client, task_id: str) -> dict:
    response = await client.get(f"/api/tasks/{task_id}/execution-trace")
    assert response.status_code == 200, response.text
    return response.json()


def _nodes(trace: dict, kind: str) -> list[dict]:
    return [node for node in trace["nodes"] if node["type"] == kind]


def _edge_types(trace: dict, source: str) -> set[str]:
    return {edge["type"] for edge in trace["edges"] if edge["source"] == source}


async def test_the_trace_maps_every_real_row_to_one_node_with_valid_edges(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace project", "bootstrap_workspace": True})
    project_id = response.json()["id"]

    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id)
        # The stored artifact must exist before the row that points at it.
        session.add(
            ArtifactORM(
                id="store_1",
                filename="reading.json",
                storage_path="runtime/artifacts/reading.json",
                project_id=project_id,
            )
        )
        await session.flush()
        session.add_all(
            [
                TaskStepORM(
                    id="step_collect",
                    task_id="task_trace",
                    position=0,
                    key="collect",
                    name="Collect scenarios",
                    tool="discovery.collect_gaps",
                    status="COMPLETED",
                    duration_ms=24.0,
                ),
                TaskStepORM(
                    id="step_analyze",
                    task_id="task_trace",
                    position=1,
                    key="analyze",
                    name="Analyze scenarios",
                    tool="discovery.analyze_gaps",
                    status="COMPLETED",
                    dependencies=["collect"],
                    duration_ms=34512.0,
                ),
            ]
        )
        # Steps must exist before the rows that point at them.
        await session.flush()
        session.add_all(
            [
                TaskEvidenceORM(
                    id="ev_1",
                    task_id="task_trace",
                    step_id="step_analyze",
                    type="Analysis",
                    source="discovery",
                    summary="One reading was produced",
                ),
                TaskArtifactORM(
                    id="art_1",
                    task_id="task_trace",
                    step_id="step_analyze",
                    artifact_id="store_1",
                    name="reading.json",
                    kind="json",
                ),
                AIInvocationORM(
                    id="inv_1",
                    task_id="task_trace",
                    step_id="step_analyze",
                    task="discovery_suggestion",
                    provider="openai-compatible",
                    model="mimo-v2.6-flash",
                    status="SUCCESS",
                    duration_ms=34448.0,
                    input_tokens=1587,
                    output_tokens=668,
                    token_source="provider",
                ),
                AIInvocationORM(
                    id="inv_2",
                    task_id="task_trace",
                    task="discovery_evidence_sugg_1",
                    provider="jev",
                    model="jev-1.13.0",
                    status="SUCCESS",
                    duration_ms=457.0,
                    token_source="unknown",
                ),
                TestRunORM(
                    id="run_trace",
                    project_id=project_id,
                    workspace_id=project_id,
                    task_id="task_trace",
                    status="PASSED",
                    nodeids=["tests/test_one.py::test_one"],
                    total=1,
                    passed=1,
                ),
            ]
        )
        await session.commit()

    trace = await _trace(client, "task_trace")

    assert trace["root_task_id"] == "task_trace"
    assert trace["counts"] == {
        "task": 1,
        "step": 2,
        "invocation": 2,
        "evidence": 1,
        "artifact": 1,
        "run": 1,
        "suggestion": 0,
    }
    node_ids = {node["id"] for node in trace["nodes"]}
    # An edge that points at a node the trace does not hold would be a broken tree.
    assert {edge["target"] for edge in trace["edges"]} <= node_ids

    # A step belongs to its task and keeps its own tool, ordering and duration.
    collect = next(node for node in _nodes(trace, "step") if node["id"] == "step:step_collect")
    assert collect["parent_id"] == "task:task_trace"
    assert collect["tool"] == "discovery.collect_gaps"
    assert collect["position"] == 0
    assert collect["duration_ms"] == 24.0
    assert _edge_types(trace, "step:step_collect") == {"CHILD_OF"}

    # A step that declared a dependency keeps a DEPENDS_ON edge to the step that really exists.
    assert _edge_types(trace, "step:step_analyze") == {"CHILD_OF", "DEPENDS_ON"}
    assert {edge["target"] for edge in trace["edges"] if edge["type"] == "DEPENDS_ON"} == {"step:step_collect"}

    # A recorded invocation hangs off the step it ran in, with the numbers the provider reported.
    invocation = next(node for node in _nodes(trace, "invocation") if node["id"] == "invocation:inv_1")
    assert invocation["parent_id"] == "step:step_analyze"
    assert invocation["provider"] == "openai-compatible"
    assert invocation["token_usage"] == {"input_tokens": 1587, "output_tokens": 668, "source": "provider"}
    assert invocation["cost"] is None and invocation["pricing"] == "unpriced"
    assert invocation["fallback_used"] is False
    assert "step_id" not in invocation["unknown"]
    assert _edge_types(trace, "invocation:inv_1") == {"INVOKES"}

    # Evidence and artifacts are produced by the step that stored them.
    assert _edge_types(trace, "evidence:ev_1") == {"PRODUCES"}
    assert _edge_types(trace, "artifact:art_1") == {"PRODUCES"}
    # A run the task asked for is produced by the task.
    assert _edge_types(trace, "run:run_trace") == {"PRODUCES"}


async def test_a_missing_step_and_unreported_tokens_are_named_unknown_not_filled_in(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace gaps", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_gaps")
        session.add_all(
            [
                TaskStepORM(
                    id="step_one",
                    task_id="task_gaps",
                    position=0,
                    key="analyze",
                    name="Analyze",
                    tool="discovery.analyze_gaps",
                    status="COMPLETED",
                ),
                # Historical rows carry no step reference: that is an unknown, not a guess.
                AIInvocationORM(
                    id="inv_legacy",
                    task_id="task_gaps",
                    task="discovery_suggestion",
                    provider="openai-compatible",
                    model="mimo-v2.6-flash",
                    status="SUCCESS",
                    duration_ms=1000.0,
                    token_source="unknown",
                ),
            ]
        )
        await session.commit()

    trace = await _trace(client, "task_gaps")

    invocation = _nodes(trace, "invocation")[0]
    assert invocation["parent_id"] == "task:task_gaps"
    assert "step_id" in invocation["unknown"]
    assert "token_usage" in invocation["unknown"]
    assert invocation["token_usage"] is None
    assert invocation["cost"] is None
    assert "parent_task_id" in trace["unknown"]


async def test_sensitive_keys_never_reach_the_trace(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace secrets", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_secret")
        session.add(
            TaskStepORM(
                id="step_secret",
                task_id="task_secret",
                position=0,
                key="analyze",
                name="Analyze",
                tool="discovery.analyze_gaps",
                status="RUNNING",
                inputs={"prompt": "x" * 500, "authorization": "Bearer secret-token", "nested": {"a": 1, "b": 2}},
                outputs={"api_key": "sk-live", "answer": "short answer"},
            )
        )
        await session.commit()

    trace = await _trace(client, "task_secret")

    step = _nodes(trace, "step")[0]
    assert "authorization" not in step["inputs"]
    assert step["inputs"]["nested"] == "{2 fields}"
    assert len(step["inputs"]["prompt"]) <= 160
    assert "api_key" not in step["outputs"]
    assert step["outputs"]["answer"] == "short answer"
    # The task's own inputs pass the same filter.
    assert "api_token" not in _nodes(trace, "task")[0]["inputs"]


async def test_a_project_trace_keeps_each_task_as_its_own_root(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace roots", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_a")
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_b")
        await session.commit()

    response = await client.get(f"/api/projects/{project_id}/execution-trace?limit=5")
    assert response.status_code == 200, response.text
    trace = response.json()

    assert trace["root_task_id"] is None
    assert trace["root_count"] == 2
    assert trace["counts"]["task"] == 2
    roots = [node for node in trace["nodes"] if node["type"] == "task"]
    assert {node["task_id"] for node in roots} == {"task_a", "task_b"}
    # No task claims another task as its parent: the platform has no such relation.
    assert all(node["parent_id"] is None for node in roots)


async def test_two_tasks_that_propose_the_same_scenario_keep_distinct_nodes(client, test_db_session):
    """A scenario keeps its id across runs, so the row id — not the scenario id — is the node identity."""
    from app.persistence.models import DiscoverySuggestionORM, QualityDiscoveryRunORM

    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace suggestions", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_a")
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_b")
        for row_id, task_id, run_id in (
            ("sug_row_1", "task_a", "qd_one"),
            ("sug_row_2", "task_b", "qd_two"),
        ):
            session.add(
                QualityDiscoveryRunORM(
                    id=run_id,
                    project_id=project_id,
                    requested_by=owner_id,
                    mode="EXPLORE",
                    start_url="http://127.0.0.1:8000/api/demo-shop/index.html",
                    status="COMPLETED",
                )
            )
            await session.flush()
            session.add(
                DiscoverySuggestionORM(
                    id=row_id,
                    project_id=project_id,
                    run_id=run_id,
                    suggestion_id="scen_shared",
                    scenario_id="scen_shared",
                    source="rules",
                    analysis_status="COMPLETED",
                    review_status="PENDING",
                    input_hash=f"hash_{row_id}",
                    task_id=task_id,
                    evidence_ids=["act_1"],
                    related_case_ids=[],
                    payload={"title": "click View warranty terms"},
                    jev={},
                    review={},
                )
            )
        await session.commit()

    trace = (await client.get(f"/api/projects/{project_id}/execution-trace?limit=5")).json()
    suggestion_nodes = [node for node in trace["nodes"] if node["type"] == "suggestion"]
    ids = [node["id"] for node in trace["nodes"]]

    assert trace["counts"]["suggestion"] == 2
    assert len(suggestion_nodes) == 2
    assert len(ids) == len(set(ids)), "the same scenario proposed by two tasks must not collide"
    assert {node["task_id"] for node in suggestion_nodes} == {"task_a", "task_b"}


async def test_every_node_links_to_the_screen_that_already_shows_the_row(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace links", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_linked")
        session.add(
            TestRunORM(
                id="run_linked",
                project_id=project_id,
                task_id="task_linked",
                workspace_id=f"ws_{project_id}",
                status="PASSED",
                nodeids=["tests/test_shop.py::test_cart"],
                total=1,
                passed=1,
                failed=0,
            )
        )
        await session.commit()

    trace = await _trace(client, "task_linked")
    task_node = _nodes(trace, "task")[0]
    run_node = _nodes(trace, "run")[0]

    assert task_node["links"] == {"task": "/runs/tasks?taskId=task_linked"}
    assert run_node["links"] == {"run": "/runs/run_linked"}


async def test_an_empty_project_reports_no_task_rather_than_a_placeholder(client):
    response = await client.post("/api/projects", json={"name": "Trace empty", "bootstrap_workspace": True})
    project_id = response.json()["id"]

    trace = (await client.get(f"/api/projects/{project_id}/execution-trace")).json()

    assert trace["nodes"] == [] and trace["edges"] == [] and trace["root_count"] == 0
    assert "task" in trace["unknown"]


async def test_the_trace_is_scoped_to_its_owner_and_writes_nothing(client, test_db_session):
    owner_id = await _user_id(client)
    response = await client.post("/api/projects", json={"name": "Trace acl", "bootstrap_workspace": True})
    project_id = response.json()["id"]
    async with test_db_session() as session:
        await _seed_task(session, owner_id=owner_id, project_id=project_id, task_id="task_acl")
        session.add(
            TaskORM(
                id="task_foreign",
                type="ANALYZE_DISCOVERY",
                goal="Someone else's task",
                status="COMPLETED",
                owner_id="another-user",
                project_id=project_id,
                inputs={},
                context={},
                verification={},
            )
        )
        await session.commit()

    assert (await client.get("/api/tasks/task_foreign/execution-trace")).status_code == 404
    assert (await client.get("/api/tasks/does-not-exist/execution-trace")).status_code == 404

    async def counts() -> dict[str, int]:
        async with test_db_session() as session:
            return {
                table: (await session.execute(select(func.count()).select_from(model))).scalar_one()
                for table, model in {
                    "tasks": TaskORM,
                    "steps": TaskStepORM,
                    "invocations": AIInvocationORM,
                    "runs": TestRunORM,
                }.items()
            }

    before = await counts()
    await _trace(client, "task_acl")
    await _trace(client, "task_acl")
    assert await counts() == before
