"""Assertion ↔ script ↔ TestRun linkage: real records only, never inferred states."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.container import get_requirement_lifecycle_service
from app.main import app
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_run_repo import TestRunRepository
from app.services.requirement_lifecycle_service import RequirementLifecycleService
from project_model.models import RunStatus, TestRunCreate
from qa_core.ai.models import AICompletionResponse

SCRIPT = """from playwright.sync_api import Page, expect


def test_total_is_discounted(page: Page):
    # criterion: AC-001
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")
"""

DRAFTING = {
    "assertions": [
        {
            "criterion_id": "AC-001",
            "statement": "Order total shows 90.00 after a 10% code",
            "check": "read the total and compare to 90.00",
        }
    ]
}


class Orchestrator:
    __test__ = False

    def __init__(self, payload: dict):
        self.payload = payload
        self.ai_provider = SimpleNamespace(provider_name="unit_fixture", model="assertion_fixture")
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return AICompletionResponse(
            content="{}", structured_data=self.payload, provider="unit_fixture", model="assertion_fixture"
        )


async def _seed_adopted(client, criteria: str = "Valid code reduces the total") -> tuple[str, str, str]:
    project = (await client.post("/api/projects", json={"name": "Linkage probe", "bootstrap_workspace": True})).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Checkout discount",
                "description": "A valid code reduces the order total by the code percentage.",
                "acceptance_criteria": criteria,
            },
        )
    ).json()
    orchestrator = Orchestrator(DRAFTING)
    app.dependency_overrides[get_requirement_lifecycle_service] = lambda: RequirementLifecycleService(
        TaskRepositoryScopeFactory(), orchestrator
    )
    drafts = (await client.post(f"/api/requirements/{requirement['id']}/assertions/draft")).json()
    assertion_id = drafts[0]["id"]
    await client.post(
        f"/api/requirements/{requirement['id']}/assertions/{assertion_id}/adoption", json={"adopted": True}
    )
    return project["id"], requirement["id"], assertion_id


def _stop() -> None:
    app.dependency_overrides.pop(get_requirement_lifecycle_service, None)


@pytest.mark.asyncio
async def test_saving_a_script_records_the_binding(client):
    project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        response = await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": [assertion_id]},
        )
        assert response.status_code == 200, response.text
        binding = response.json()
        assert binding["path"] == "tests/test_total.py"
        assert binding["assertion_ids"] == [assertion_id]
        assert binding["criterion_ids"] == ["AC-001"]
        assert binding["nodeids"] == ["tests/test_total.py::test_total_is_discounted"]

        saved = (await client.get(f"/api/requirements/{requirement_id}")).json()["qa_model"]
        assert [item["path"] for item in saved["scripts"]] == ["tests/test_total.py"]
        files = (await client.get(f"/api/workspaces/{project_id}/files")).json()
        names = [node["name"] for node in files]

        def flatten(nodes):
            for node in nodes:
                yield node
                yield from flatten(node.get("children") or [])

        assert any(node["name"] == "test_total.py" for node in flatten(files)) or "tests" in names
    finally:
        _stop()


@pytest.mark.asyncio
async def test_saving_requires_adopted_assertions(client):
    _project_id, requirement_id, _assertion_id = await _seed_adopted(client)
    try:
        response = await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": ["ASR-UNKNOWN-1"]},
        )
        assert response.status_code == 422
        assert "adopted assertions" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_identical_resave_is_idempotent_but_different_content_is_rejected(client):
    _project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        payload = {"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": [assertion_id]}
        first = await client.post(f"/api/requirements/{requirement_id}/assertions/script/save", json=payload)
        assert first.status_code == 200, first.text
        again = await client.post(f"/api/requirements/{requirement_id}/assertions/script/save", json=payload)
        assert again.status_code == 200, again.text
        changed = {**payload, "code": SCRIPT.replace("90.00", "80.00")}
        conflict = await client.post(f"/api/requirements/{requirement_id}/assertions/script/save", json=changed)
        assert conflict.status_code == 409
    finally:
        _stop()


@pytest.mark.asyncio
async def test_binding_cannot_be_forged_beyond_the_code_markers(client):
    _project_id, requirement_id, assertion_id = await _seed_adopted(
        client, criteria="Valid code reduces the total\nExpired code leaves the total unchanged"
    )
    try:
        # The code claims a criterion that no adopted assertion backs, so the binding must be rejected.
        leaky = SCRIPT.replace("# criterion: AC-001", "# criterion: AC-001\n    # criterion: AC-002")
        response = await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_total.py", "code": leaky, "assertion_ids": [assertion_id]},
        )
        assert response.status_code == 422
        assert "without an adopted assertion" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_not_adopted_assertion_reports_not_adopted(client):
    project = (
        await client.post("/api/projects", json={"name": "Not adopted probe", "bootstrap_workspace": True})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Checkout",
                "description": "desc",
                "acceptance_criteria": "Valid code reduces the total",
            },
        )
    ).json()
    app.dependency_overrides[get_requirement_lifecycle_service] = lambda: RequirementLifecycleService(
        TaskRepositoryScopeFactory(), Orchestrator(DRAFTING)
    )
    try:
        await client.post(f"/api/requirements/{requirement['id']}/assertions/draft")
        body = (await client.get(f"/api/requirements/{requirement['id']}/assertions/runs")).json()
        assert body["assertions"][0]["state"] == "NOT_ADOPTED"
    finally:
        _stop()


@pytest.mark.asyncio
async def test_run_without_execution_records_is_not_mistaken_for_passed(client, test_db_session):
    project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={
                "path": "tests/test_total.py",
                "code": SCRIPT,
                "assertion_ids": [assertion_id],
            },
        )
        async with test_db_session() as session:
            repository = TestRunRepository(session)
            run = await repository.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
            await repository.update_run_status(run.id, RunStatus.PASSED, total=1, passed=1, failed=0)
            await session.commit()
        body = (await client.get(f"/api/requirements/{requirement_id}/assertions/runs")).json()
        assert body["assertions"][0]["state"] == "NEVER_RUN"
    finally:
        _stop()


@pytest.mark.asyncio
async def test_assertion_runs_reports_never_run_before_any_execution(client):
    _project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": [assertion_id]},
        )
        response = await client.get(f"/api/requirements/{requirement_id}/assertions/runs")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["assertions"][0]["assertion_id"] == assertion_id
        assert body["assertions"][0]["state"] == "NEVER_RUN"
        assert body["assertions"][0]["run"] is None
    finally:
        _stop()


@pytest.mark.asyncio
async def test_assertion_runs_maps_a_real_execution(client, test_db_session):
    project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_total.py", "code": SCRIPT, "assertion_ids": [assertion_id]},
        )
        nodeid = "tests/test_total.py::test_total_is_discounted"
        async with test_db_session() as session:
            repository = TestRunRepository(session)
            run = await repository.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
            await repository.add_execution(
                run.id, nodeid, RunStatus.PASSED, duration_ms=1234.0, artifact_paths=["shot.png"]
            )
            await repository.update_run_status(run.id, RunStatus.PASSED, total=1, passed=1, failed=0)
            await session.commit()
            run_id = run.id

        response = await client.get(f"/api/requirements/{requirement_id}/assertions/runs")
        assert response.status_code == 200, response.text
        entry = response.json()["assertions"][0]
        assert entry["state"] == "PASSED"
        assert entry["run"]["run_id"] == run_id
        assert entry["run"]["nodeid"] == nodeid
        assert entry["run"]["artifact_count"] == 1
        assert entry["run"]["finished_at"]
    finally:
        _stop()


TWO_TESTS = """from playwright.sync_api import Page, expect


def test_total_is_discounted(page: Page):
    # criterion: AC-001
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")


def test_coupon_is_rejected(page: Page):
    # criterion: AC-002
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#status")).to_have_text("invalid coupon")
"""


@pytest.mark.asyncio
async def test_assertions_are_paired_with_their_own_test_function(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Pairing probe", "bootstrap_workspace": True})).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Checkout",
                "description": "Two checks",
                "acceptance_criteria": "Valid code reduces the total\nExpired code is rejected",
            },
        )
    ).json()
    two = {
        "assertions": [
            {
                "criterion_id": "AC-001",
                "statement": "Total shows 90.00 after a 10% code",
                "check": "read total",
            },
            {
                "criterion_id": "AC-002",
                "statement": "Expired code is rejected with a message",
                "check": "read status",
            },
        ]
    }
    app.dependency_overrides[get_requirement_lifecycle_service] = lambda: RequirementLifecycleService(
        TaskRepositoryScopeFactory(), Orchestrator(two)
    )
    try:
        drafts = (await client.post(f"/api/requirements/{requirement['id']}/assertions/draft")).json()
        for item in drafts:
            await client.post(
                f"/api/requirements/{requirement['id']}/assertions/{item['id']}/adoption", json={"adopted": True}
            )
        saved = await client.post(
            f"/api/requirements/{requirement['id']}/assertions/script/save",
            json={
                "path": "tests/test_checkout.py",
                "code": TWO_TESTS,
                "assertion_ids": [item["id"] for item in drafts],
            },
        )
        assert saved.status_code == 200, saved.text
        binding = saved.json()
        assert {pairing["nodeid"] for pairing in binding["nodeid_criteria"]} == {
            "tests/test_checkout.py::test_total_is_discounted",
            "tests/test_checkout.py::test_coupon_is_rejected",
        }

        project_id = project["id"]
        async with test_db_session() as session:
            repository = TestRunRepository(session)
            run = await repository.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
            await repository.add_execution(
                run.id,
                "tests/test_checkout.py::test_coupon_is_rejected",
                RunStatus.FAILED,
                error_message="coupon accepted",
            )
            await repository.add_execution(run.id, "tests/test_checkout.py::test_total_is_discounted", RunStatus.PASSED)
            await repository.update_run_status(run.id, RunStatus.FAILED, total=2, passed=1, failed=1)
            await session.commit()

        body = (await client.get(f"/api/requirements/{requirement['id']}/assertions/runs")).json()
        states = {entry["criterion_id"]: entry["state"] for entry in body["assertions"]}
        assert states == {"AC-001": "PASSED", "AC-002": "FAILED"}
    finally:
        _stop()


@pytest.mark.asyncio
async def test_test_function_without_criterion_marker_is_rejected(client):
    _project_id, requirement_id, assertion_id = await _seed_adopted(client)
    try:
        unmarked = """from playwright.sync_api import Page


def test_unmarked(page: Page):
    page.goto("http://127.0.0.1:5183/")
    assert True
"""
        response = await client.post(
            f"/api/requirements/{requirement_id}/assertions/script/save",
            json={"path": "tests/test_unmarked.py", "code": unmarked, "assertion_ids": [assertion_id]},
        )
        assert response.status_code == 422
        assert "no '# criterion:' marker" in response.json()["detail"]
    finally:
        _stop()
