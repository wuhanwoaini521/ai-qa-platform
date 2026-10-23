"""A workflow definition is a versioned, validated, approved artifact — never a guess from a trace.

Drafting and publishing are separate permissions, a published version never changes, and a plan is
only compiled from a version that validates.
"""

from __future__ import annotations

import pytest
from app.repositories.workflow_definition_repo import (
    WorkflowDefinitionRepository,
    WorkflowVersionNotFound,
    graph_checksum,
)
from app.services.workflow_definition_service import WorkflowDefinitionService
from conftest import bearer_client, login_token
from sqlalchemy import select

pytestmark = pytest.mark.integration


PASSWORD = "pw-123456"


def test_graph_checksum_and_execution_order_ignore_node_declaration_order():
    graph = {
        "nodes": [
            {"key": "first", "kind": "tests.generate"},
            {"key": "second", "kind": "tests.generate"},
        ],
        "edges": [],
    }

    reordered = {**graph, "nodes": list(reversed(graph["nodes"]))}

    assert graph_checksum(graph) == graph_checksum(reordered)

    from project_model.workflow_definition import WorkflowGraphSpec, execution_order

    assert execution_order(WorkflowGraphSpec.model_validate(graph)) == execution_order(
        WorkflowGraphSpec.model_validate(reordered)
    )


async def _as(admin, email: str):
    return bearer_client(await login_token(admin, email, PASSWORD))


async def _members(client, session, project_id: str, people: list[tuple[str, str]], team_id: str) -> None:
    """One project team holds every role under test: the team, not the role, grants project access."""
    from app.persistence.models import TeamMemberORM, TeamORM

    user_ids: list[str] = []
    for email, role in people:
        created = await client.post(
            "/api/users",
            json={"email": email, "full_name": email.split("@")[0], "role": role, "password": PASSWORD},
        )
        assert created.status_code == 201, created.text
        user_ids.append(created.json()["id"])
    async with session() as db:
        db.add(TeamORM(id=team_id, name=team_id))
        await db.flush()
        for index, user_id in enumerate(user_ids):
            db.add(TeamMemberORM(id=f"tm_{team_id}_{index}", team_id=team_id, user_id=user_id))
        await db.commit()
    patched = await client.patch(f"/api/projects/{project_id}", json={"team_id": team_id})
    assert patched.status_code == 200, patched.text


def _graph(*, extra: bool = False) -> dict:
    """A realistic authoring flow: read the readings, draft, ask a human, then write."""
    run_input = {"discovery_run_id": {"$input": "discovery_run_id"}}
    nodes = [
        {"key": "collect", "kind": "discovery.collect_gaps", "inputs": dict(run_input)},
        {"key": "analyze", "kind": "discovery.analyze_gaps", "title": "Analyse the gaps", "inputs": dict(run_input)},
        {"key": "generate", "kind": "tests.generate"},
        {"key": "approve", "kind": "task.request_approval"},
        {"key": "write", "kind": "source.write_generated"},
    ]
    edges = [
        {"source": "collect", "target": "analyze"},
        {"source": "analyze", "target": "generate"},
        {"source": "generate", "target": "approve"},
        {"source": "approve", "target": "write"},
    ]
    if extra:
        nodes.append({"key": "verify", "kind": "tests.run_target"})
        edges.append({"source": "write", "target": "verify"})
    return {"nodes": nodes, "edges": edges}


async def _project(client, name: str) -> str:
    response = await client.post("/api/projects", json={"name": name, "bootstrap_workspace": True})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


async def _definition(client, project_id: str, name: str = "Discovery follow-up") -> dict:
    response = await client.post(
        f"/api/projects/{project_id}/workflows", json={"name": name, "description": "Review readings"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_draft_can_be_saved_compared_and_published_once(client):
    project_id = await _project(client, "Workflow project")
    created = await _definition(client, project_id)
    definition_id = created["id"]
    assert created["draft"]["version"] == 1
    assert created["draft"]["graph"] == {"nodes": [], "edges": []}
    assert {kind["kind"] for kind in created["catalogue"]} >= {
        "discovery.collect_gaps",
        "task.request_approval",
        "source.write_generated",
    }

    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert saved.status_code == 200, saved.text
    assert saved.json()["issues"] == []
    assert saved.json()["draft"]["graph"]["nodes"][0]["key"] == "collect"

    published = await client.post(f"/api/workflows/{definition_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["published"]["version"] == 1
    assert published.json()["published"]["state"] == "PUBLISHED"
    # Publishing opens the next draft; the published row itself is never edited in place.
    assert published.json()["draft_version"] == 2

    detail = (await client.get(f"/api/workflows/{definition_id}")).json()
    assert detail["published_version"] == 1
    states = {row["version"]: row["state"] for row in detail["versions"]}
    assert states[1] == "PUBLISHED"
    assert states[2] == "DRAFT"
    assert detail["published"]["graph"]["nodes"][0]["key"] == "collect"

    second = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph(extra=True))
    assert second.status_code == 200, second.text
    assert second.json()["draft"]["version"] == 2

    compared = await client.get(f"/api/workflows/{definition_id}/compare", params={"base": 1, "head": 2})
    assert compared.status_code == 200, compared.text
    diff = compared.json()["diff"]
    assert [node["key"] for node in diff["nodes"]["added"]] == ["verify"]
    assert diff["edges"]["added"] == [{"source": "write", "target": "verify"}]
    assert diff["identical"] is False


async def test_an_invalid_draft_is_flagged_and_cannot_be_published(client):
    project_id = await _project(client, "Workflow validation")
    definition_id = (await _definition(client, project_id))["id"]

    cycle = {
        "nodes": [
            {"key": "a", "kind": "tests.generate"},
            {"key": "b", "kind": "tests.generate"},
        ],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    }
    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=cycle)
    assert saved.status_code == 200
    assert {issue["code"] for issue in saved.json()["issues"]} == {"CYCLE"}

    refused = await client.post(f"/api/workflows/{definition_id}/publish")
    assert refused.status_code == 422
    assert "cycle" in refused.json()["detail"].lower()

    unknown_kind = {
        "nodes": [{"key": "a", "kind": "shell.execute"}],
        "edges": [],
    }
    validated = await client.post(f"/api/workflows/{definition_id}/validate", json=unknown_kind)
    assert {issue["code"] for issue in validated.json()["issues"]} == {"UNKNOWN_KIND"}

    missing = {
        "nodes": [{"key": "a", "kind": "tests.generate"}],
        "edges": [{"source": "a", "target": "ghost"}],
    }
    validated = await client.post(f"/api/workflows/{definition_id}/validate", json=missing)
    assert {issue["code"] for issue in validated.json()["issues"]} == {"UNKNOWN_EDGE_NODE"}


@pytest.mark.parametrize(
    "graph",
    [
        {"nodes": [{"key": 7, "kind": "tests.generate"}], "edges": []},
        {"nodes": [{"key": "a", "kind": "tests.generate", "inputs": None}], "edges": []},
        {"nodes": [{"key": "a", "kind": "tests.generate", "position": {"x": "bad"}}], "edges": []},
        {"nodes": [None], "edges": []},
        {"nodes": [{"key": "a", "kind": "tests.generate"}], "edges": [{"source": None, "target": "a"}]},
        {"nodes": None, "edges": []},
    ],
)
async def test_validate_rejects_structurally_malformed_graph_with_422(client, graph):
    project_id = await _project(client, "Malformed workflow validation")
    definition_id = (await _definition(client, project_id))["id"]

    response = await client.post(f"/api/workflows/{definition_id}/validate", json=graph)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("corrupt_graph", [[], [1], {"nodes": [None], "edges": []}])
async def test_corrupt_published_graph_does_not_break_detail_or_launch(client, test_db_session, corrupt_graph):
    project_id = await _project(client, "Corrupt published graph")
    definition_id = (await _definition(client, project_id))["id"]
    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert saved.status_code == 200
    published = await client.post(f"/api/workflows/{definition_id}/publish")
    assert published.status_code == 200

    from app.persistence.models import WorkflowDefinitionVersionORM

    async with test_db_session() as session:
        version = await session.get(WorkflowDefinitionVersionORM, published.json()["published"]["id"])
        version.graph = corrupt_graph
        await session.commit()

    detail = await client.get(f"/api/workflows/{definition_id}")
    launch = await client.post(
        f"/api/workflows/{definition_id}/execute",
        json={"version": published.json()["published"]["version"], "inputs": {"failure_id": "missing"}},
        headers={"Idempotency-Key": "corrupt-graph-launch"},
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["published"]["execution"]["eligible"] is False
    assert detail.json()["published"]["graph"] == {"nodes": [], "edges": []}
    assert launch.status_code == 422, launch.text


@pytest.mark.parametrize("corrupt_graph", [[1], {"nodes": 7, "edges": None}])
async def test_corrupt_draft_graph_does_not_break_definition_list_or_detail(client, test_db_session, corrupt_graph):
    project_id = await _project(client, "Corrupt draft graph")
    definition_id = (await _definition(client, project_id))["id"]

    from app.persistence.models import WorkflowDefinitionVersionORM

    async with test_db_session() as session:
        draft = await session.scalar(
            select(WorkflowDefinitionVersionORM).where(
                WorkflowDefinitionVersionORM.definition_id == definition_id,
                WorkflowDefinitionVersionORM.state == "DRAFT",
            )
        )
        draft.graph = corrupt_graph
        await session.commit()

    listing = await client.get(f"/api/projects/{project_id}/workflows")
    detail = await client.get(f"/api/workflows/{definition_id}")

    assert listing.status_code == 200, listing.text
    assert listing.json()["definitions"][0]["draft_node_count"] == 0
    assert detail.status_code == 200, detail.text
    assert detail.json()["draft"]["graph"] == {"nodes": [], "edges": []}


async def test_malformed_draft_is_rejected_without_replacing_the_saved_graph(client):
    project_id = await _project(client, "Malformed workflow draft")
    definition_id = (await _definition(client, project_id))["id"]
    original = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert original.status_code == 200
    original_graph = original.json()["draft"]["graph"]

    malformed = await client.put(
        f"/api/workflows/{definition_id}/draft",
        json={"nodes": [{"key": 7, "kind": "tests.generate"}], "edges": []},
    )

    assert malformed.status_code == 422
    after = await client.get(f"/api/workflows/{definition_id}")
    assert after.json()["draft"]["graph"] == original_graph


async def test_a_stale_editor_cannot_overwrite_a_newer_draft(client, test_db_session):
    project_id = await _project(client, "Workflow conflict")
    definition_id = (await _definition(client, project_id))["id"]
    first = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    checksum = first.json()["draft"]["checksum"]
    assert (await client.put(f"/api/workflows/{definition_id}/draft", json=_graph(extra=True))).status_code == 200

    stale = await client.put(f"/api/workflows/{definition_id}/draft", json={**_graph(), "base_checksum": checksum})
    assert stale.status_code == 409
    assert "changed since" in stale.json()["detail"]

    fresh = await client.put(
        f"/api/workflows/{definition_id}/draft",
        json={
            **_graph(),
            "base_checksum": (await client.get(f"/api/workflows/{definition_id}")).json()["draft"]["checksum"],
        },
    )
    assert fresh.status_code == 200, fresh.text


async def test_concurrent_orm_version_conflicts_return_409_and_preserve_published_version(client, test_db_session):
    from sqlalchemy.orm.exc import StaleDataError

    project_id = await _project(client, "Workflow optimistic conflict")
    definition_id = (await _definition(client, project_id))["id"]
    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert saved.status_code == 200

    from app.api.workflow_definitions import get_workflow_definition_service
    from app.container import get_db
    from app.main import app

    async def stale_publish(self, definition, issues, actor_id):
        raise StaleDataError("concurrent update")

    async def stale_save(self, definition, graph, issues, actor_id, base_checksum=None):
        raise StaleDataError("concurrent update")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(WorkflowDefinitionRepository, "publish", stale_publish)
    monkeypatch.setattr(WorkflowDefinitionRepository, "save_draft", stale_save)
    original_dependency = app.dependency_overrides.get(get_workflow_definition_service)
    original_db_dependency = app.dependency_overrides.get(get_db)

    async def dependency():
        async with test_db_session() as session:
            yield WorkflowDefinitionService(WorkflowDefinitionRepository(session))

    async def rollback_db():
        yield None

    async def fresh_dependency():
        async with test_db_session() as session:
            yield WorkflowDefinitionService(WorkflowDefinitionRepository(session))

    app.dependency_overrides[get_db] = rollback_db
    app.dependency_overrides[get_workflow_definition_service] = fresh_dependency
    try:
        response = await client.post(f"/api/workflows/{definition_id}/publish")
    finally:
        if original_dependency is None:
            app.dependency_overrides.pop(get_workflow_definition_service, None)
        else:
            app.dependency_overrides[get_workflow_definition_service] = original_dependency
        if original_db_dependency is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_db_dependency
        monkeypatch.undo()

    assert response.status_code == 409
    assert "CONCURRENT_MODIFICATION" in response.text
    assert "reload" in response.text.lower()
    async with test_db_session() as session:
        definition = await WorkflowDefinitionRepository(session).get(definition_id)
        versions = await WorkflowDefinitionRepository(session).versions(definition_id)
    assert definition.published_version is None
    assert [row.state for row in versions] == ["DRAFT"]


async def test_restoring_a_published_version_creates_a_new_draft(client):
    project_id = await _project(client, "Workflow restore")
    definition_id = (await _definition(client, project_id))["id"]
    await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert (await client.post(f"/api/workflows/{definition_id}/publish")).status_code == 200
    await client.put(f"/api/workflows/{definition_id}/draft", json={"nodes": [], "edges": []})

    restored = await client.post(f"/api/workflows/{definition_id}/versions/1/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["draft"]["version"] == 2
    assert [node["key"] for node in restored.json()["draft"]["graph"]["nodes"]] == [
        "collect",
        "analyze",
        "generate",
        "approve",
        "write",
    ]


async def test_a_published_version_compiles_into_runtime_steps(client, test_db_session):
    project_id = await _project(client, "Workflow compile")
    definition_id = (await _definition(client, project_id))["id"]
    await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert (await client.post(f"/api/workflows/{definition_id}/publish")).status_code == 200

    async with test_db_session() as session:
        service = WorkflowDefinitionService(WorkflowDefinitionRepository(session))
        definition = await service.definitions.get(definition_id)
        assert definition is not None
        steps, version = await service.compile_plan(definition)
        assert version.state == "PUBLISHED"
        assert [step.key for step in steps] == ["collect", "analyze", "generate", "approve", "write"]
        assert steps[1].depends_on == ["collect"]
        assert steps[4].depends_on == ["approve"]
        assert steps[0].tool == "discovery.collect_gaps"
        # `{"$input": ...}` binds from the run inputs, so the step must not pin a literal.
        assert steps[0].inputs == {}
        assert steps[4].inputs == {}

        with pytest.raises(WorkflowVersionNotFound):
            await service.compile_plan(definition, version=2)


async def test_a_lead_publishes_while_an_engineer_may_only_draft(client, test_db_session):
    """Drafting is automation work; publishing is a governance act reserved for a lead."""
    project_id = await _project(client, "Workflow permissions")
    definition_id = (await _definition(client, project_id))["id"]
    await _members(
        client,
        test_db_session,
        project_id,
        [("workflow.engineer@example.com", "QA_ENGINEER"), ("workflow.lead@example.com", "QA_LEAD")],
        "team_workflow_roles",
    )
    engineer = await _as(client, "workflow.engineer@example.com")
    lead = await _as(client, "workflow.lead@example.com")

    async with engineer:
        saved = await engineer.put(f"/api/workflows/{definition_id}/draft", json=_graph())
        assert saved.status_code == 200, saved.text
        assert saved.json()["issues"] == []
        refused = await engineer.post(f"/api/workflows/{definition_id}/publish")
        assert refused.status_code == 403
        assert "publish" not in refused.text.lower() or "lacks permission" in refused.text

    async with lead:
        published = await lead.post(f"/api/workflows/{definition_id}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["published"]["state"] == "PUBLISHED"


async def test_a_viewer_reads_but_never_edits(client, test_db_session):
    project_id = await _project(client, "Workflow viewer")
    definition_id = (await _definition(client, project_id))["id"]
    viewer_email = "workflow.viewer@example.com"
    await _members(client, test_db_session, project_id, [(viewer_email, "VIEWER")], "team_workflow_viewer")
    viewer = await _as(client, viewer_email)

    async with viewer:
        assert (await viewer.get(f"/api/workflows/{definition_id}")).status_code == 200
        assert (await viewer.get(f"/api/projects/{project_id}/workflows")).status_code == 200
        assert (await viewer.put(f"/api/workflows/{definition_id}/draft", json=_graph())).status_code == 403
        assert (await viewer.post(f"/api/workflows/{definition_id}/publish")).status_code == 403


async def test_a_stranger_cannot_see_or_touch_the_definition(client):
    project_id = await _project(client, "Workflow owner")
    definition_id = (await _definition(client, project_id))["id"]
    email = "workflow.stranger@example.com"
    created = await client.post(
        "/api/users",
        json={"email": email, "full_name": "Stranger", "role": "QA_ENGINEER", "password": "pw-123456"},
    )
    assert created.status_code == 201, created.text
    stranger = await _as(client, email)

    async with stranger:
        # Never 403 on an id, so project existence cannot be probed.
        assert (await stranger.get(f"/api/workflows/{definition_id}")).status_code == 404
        assert (await stranger.put(f"/api/workflows/{definition_id}/draft", json=_graph())).status_code == 404
        assert (await stranger.get(f"/api/projects/{project_id}/workflows")).status_code == 404


async def test_a_draft_that_never_validated_still_reports_its_issues(client):
    project_id = await _project(client, "Workflow issues")
    definition_id = (await _definition(client, project_id))["id"]
    # A write without an approval before it is exactly the rule the platform must never relax.
    unsafe = {
        "nodes": [
            {"key": "generate", "kind": "tests.generate"},
            {"key": "write", "kind": "source.write_generated"},
        ],
        "edges": [{"source": "generate", "target": "write"}],
    }
    saved = await client.put(f"/api/workflows/{definition_id}/draft", json=unsafe)
    assert {issue["code"] for issue in saved.json()["issues"]} == {"WRITE_WITHOUT_APPROVAL"}

    listed = (await client.get(f"/api/projects/{project_id}/workflows")).json()
    assert listed["definitions"][0]["draft_issues"][0]["code"] == "WRITE_WITHOUT_APPROVAL"
    assert listed["definitions"][0]["draft_node_count"] == 2
    assert listed["catalogue"] == (await client.get(f"/api/projects/{project_id}/workflows")).json()["catalogue"]


async def test_the_execution_diff_names_what_ran_and_what_the_definition_expected(client, test_db_session):
    """Read-only: the definition is compared with a task's real steps, never used to invent them."""
    from app.persistence.models import TaskORM, TaskStepORM

    project_id = await _project(client, "Workflow execution diff")
    definition_id = (await _definition(client, project_id))["id"]
    await client.put(f"/api/workflows/{definition_id}/draft", json=_graph())
    assert (await client.post(f"/api/workflows/{definition_id}/publish")).status_code == 200

    async with test_db_session() as session:
        user_id = (await client.get("/api/auth/me")).json()["user"]["id"]
        session.add(
            TaskORM(
                id="task_diff",
                type="QA_GOAL",
                goal="Run the readings flow",
                status="COMPLETED",
                owner_id=user_id,
                project_id=project_id,
                inputs={},
                context={},
                verification={},
                created_at=None,
            )
        )
        await session.flush()
        for position, (key, tool) in enumerate(
            [
                ("collect", "discovery.collect_gaps"),
                ("analyze", "discovery.analyze_gaps"),
                ("write", "source.write_generated"),
                ("probe", "browser.inspect"),
            ]
        ):
            session.add(
                TaskStepORM(
                    id=f"step_{key}",
                    task_id="task_diff",
                    position=position,
                    key=key,
                    name=key,
                    tool=tool,
                    status="COMPLETED",
                )
            )
        await session.commit()

    response = await client.get(f"/api/workflows/{definition_id}/execution-diff", params={"task_id": "task_diff"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"] == {
        "definition_nodes": 5,
        "ran_steps": 4,
        "matched": 3,
        "not_executed": 2,
        "undeclared": 1,
    }
    assert [row["key"] for row in payload["matched"]] == ["collect", "analyze", "write"]
    assert {row["key"] for row in payload["not_executed"]} == {"generate", "approve"}
    assert payload["undeclared"][0]["tool"] == "browser.inspect"
    assert payload["undeclared"][0]["reason"] == "the_definition_declares_no_node_of_this_kind"
    # Facts the comparison does not establish stay declared as unknown.
    assert "step_inputs_are_not_compared" in payload["unknown"]

    other_project = await _project(client, "Someone else's project")
    foreign = await client.get(
        f"/api/workflows/{definition_id}/execution-diff", params={"task_id": "task_diff", "version": 1}
    )
    assert foreign.status_code == 200, foreign.text
    assert other_project != project_id

    missing = await client.get(f"/api/workflows/{definition_id}/execution-diff", params={"task_id": "task_missing"})
    assert missing.status_code == 404
