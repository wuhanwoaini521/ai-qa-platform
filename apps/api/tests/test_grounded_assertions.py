"""Grounded assertions → script draft: criteria-grounded, human-adopted, never auto-written."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.container import get_requirement_lifecycle_service
from app.main import app
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.requirement_lifecycle_service import RequirementLifecycleService
from qa_core.ai.models import AICompletionResponse

VALID_SCRIPT = """from playwright.sync_api import Page, expect


def test_discount_checkout(page: Page):
    # criterion: AC-001
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")
"""


class DraftingOrchestrator:
    __test__ = False

    def __init__(self, payload: dict, *, provider: str = "unit_fixture"):
        self.payload = payload
        self.provider = provider
        self.ai_provider = SimpleNamespace(provider_name=provider, model="assertion_fixture")
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return AICompletionResponse(
            content="{}",
            structured_data=self.payload,
            provider=self.provider,
            model="assertion_fixture",
        )


def _assertion(criterion_id: str, statement: str) -> dict:
    return {
        "criterion_id": criterion_id,
        "statement": statement,
        "check": "read the rendered total and compare it to the expected value",
    }


async def _seed(client, *, criteria: str) -> tuple[str, str]:
    project = (await client.post("/api/projects", json={"name": "Assertion probe", "bootstrap_workspace": True})).json()
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
    return project["id"], requirement["id"]


def _use_service(orchestrator) -> None:
    app.dependency_overrides[get_requirement_lifecycle_service] = lambda: RequirementLifecycleService(
        TaskRepositoryScopeFactory(), orchestrator
    )


def _stop() -> None:
    app.dependency_overrides.pop(get_requirement_lifecycle_service, None)


async def _draft(client, requirement_id: str) -> list[dict]:
    response = await client.post(f"/api/requirements/{requirement_id}/assertions/draft")
    assert response.status_code == 200, response.text
    return response.json()


async def _adopt(client, requirement_id: str, assertion_id: str, adopted: bool = True) -> None:
    response = await client.post(
        f"/api/requirements/{requirement_id}/assertions/{assertion_id}/adoption", json={"adopted": adopted}
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_draft_assertions_cites_criteria_and_starts_unadopted(client):
    _project_id, requirement_id = await _seed(
        client, criteria="Valid code reduces the total\nExpired code leaves the total unchanged"
    )
    _use_service(
        DraftingOrchestrator(
            {
                "assertions": [
                    _assertion("AC-001", "Order total shows 90.00 after applying a 10% code"),
                    _assertion("AC-002", "Order total stays 100.00 when the code is expired"),
                ]
            }
        )
    )
    try:
        drafts = await _draft(client, requirement_id)
        assert {item["criterion_id"] for item in drafts} == {"AC-001", "AC-002"}
        assert all(item["adopted"] is False for item in drafts)
        assert all(item["source"] == "unit_fixture/assertion_fixture" for item in drafts)

        saved = (await client.get(f"/api/requirements/{requirement_id}")).json()["qa_model"]
        assert len(saved["assertions"]) == 2
    finally:
        _stop()


@pytest.mark.asyncio
async def test_draft_requires_acceptance_criteria(client):
    _project_id, requirement_id = await _seed(client, criteria="")
    orchestrator = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Some assertion text here")]})
    _use_service(orchestrator)
    try:
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/draft")
        assert response.status_code == 422
        assert "Acceptance criteria" in response.json()["detail"]
        assert orchestrator.calls == 0
    finally:
        _stop()


@pytest.mark.asyncio
async def test_draft_citing_unknown_criterion_is_rejected_and_not_persisted(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    _use_service(DraftingOrchestrator({"assertions": [_assertion("AC-999", "Invented assertion for unknown rule")]}))
    try:
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/draft")
        assert response.status_code == 422
        assert "unknown acceptance criteria" in response.json()["detail"]
        saved = (await client.get(f"/api/requirements/{requirement_id}")).json()["qa_model"] or {}
        assert saved.get("assertions", []) == []
    finally:
        _stop()


@pytest.mark.asyncio
async def test_adoption_is_explicit_and_persisted(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    _use_service(
        DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    )
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        saved = (await client.get(f"/api/requirements/{requirement_id}")).json()["qa_model"]
        assert saved["assertions"][0]["adopted"] is True

        missing = await client.post(
            f"/api/requirements/{requirement_id}/assertions/ASR-AC-001-9/adoption", json={"adopted": True}
        )
        assert missing.status_code == 404
    finally:
        _stop()


@pytest.mark.asyncio
async def test_redrafting_keeps_human_adopted_assertions(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    orchestrator = DraftingOrchestrator(
        {"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]}
    )
    _use_service(orchestrator)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        orchestrator.payload = {
            "assertions": [_assertion("AC-001", "Order total shows 81.00 after a 10% code on a 90.00 cart")]
        }
        redrafted = await _draft(client, requirement_id)
        assert [item["adopted"] for item in redrafted] == [True, False]
        assert redrafted[0]["statement"] == "Order total shows 90.00 after a 10% code"
    finally:
        _stop()


@pytest.mark.asyncio
async def test_fake_provider_cannot_ground_assertions(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    orchestrator = DraftingOrchestrator(
        {"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]}, provider="fake"
    )
    _use_service(orchestrator)
    try:
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/draft")
        assert response.status_code == 422
        assert "Fake AI" in response.json()["detail"]
        assert orchestrator.calls == 0
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_generation_requires_an_adopted_assertion(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        await _draft(client, requirement_id)
        script_orchestrator = DraftingOrchestrator(
            {"file_path": "tests/test_discount.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-001"]}
        )
        _use_service(script_orchestrator)
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "Adopt at least one assertion" in response.json()["detail"]
        assert script_orchestrator.calls == 0
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_generation_is_traceable_and_never_writes(client):
    project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["file_path"] == "tests/test_discount.py"
        assert body["used_criterion_ids"] == ["AC-001"]
        assert body["assertion_ids"] == [drafts[0]["id"]]
        assert "# criterion: AC-001" in body["code"]

        files = (await client.get(f"/api/workspaces/{project_id}/files")).json()

        def flatten(nodes):
            for node in nodes:
                yield node
                yield from flatten(node.get("children") or [])

        assert all(node["name"] != "test_discount.py" for node in flatten(files))
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_citing_unadopted_assertion_is_rejected(client):
    _project_id, requirement_id = await _seed(
        client, criteria="Valid code reduces the total\nExpired code leaves the total unchanged"
    )
    drafting = DraftingOrchestrator(
        {
            "assertions": [
                _assertion("AC-001", "Order total shows 90.00 after a 10% code"),
                _assertion("AC-002", "Order total stays 100.00 when the code is expired"),
            ]
        }
    )
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-002"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "not adopted" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_omitting_an_adopted_assertion_is_rejected(client):
    _project_id, requirement_id = await _seed(
        client, criteria="Valid code reduces the total\nExpired code leaves the total unchanged"
    )
    drafting = DraftingOrchestrator(
        {
            "assertions": [
                _assertion("AC-001", "Order total shows 90.00 after a 10% code"),
                _assertion("AC-002", "Order total stays 100.00 when the code is expired"),
            ]
        }
    )
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        for item in drafts:
            await _adopt(client, requirement_id, item["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "omitted adopted assertions" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_without_criterion_marker_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        markerless = VALID_SCRIPT.replace("    # criterion: AC-001\n", "")
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": markerless, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "traceability markers" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_outside_tests_directory_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "app/discount.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "tests/*.py" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_invalid_python_script_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_broken.py", "code": "def broken(:\n", "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "not valid Python" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_referencing_unknown_criterion_marker_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        leaky = VALID_SCRIPT.replace("# criterion: AC-001", "# criterion: AC-001\n    # criterion: AC-099")
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": leaky, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "not adopted" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_referencing_foreign_assertion_id_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        leaky = VALID_SCRIPT.replace("# criterion: AC-001", "# criterion: AC-001 (ASR-AC-001-9)")
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_discount.py", "code": leaky, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "assertions that were not adopted" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_that_fabricates_the_page_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        fake = """from playwright.sync_api import Page, expect


def test_fake(page: Page):
    # criterion: AC-001
    page.set_content('<div id="total">90.00</div>')
    expect(page.locator("#total")).to_have_text("90.00")
"""
        _use_service(
            DraftingOrchestrator({"file_path": "tests/test_fake.py", "code": fake, "used_criterion_ids": ["AC-001"]})
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "builds its own page" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_without_navigation_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        no_nav = """from playwright.sync_api import Page, expect


def test_no_nav(page: Page):
    # criterion: AC-001
    expect(page.locator("#total")).to_have_text("90.00")
"""
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_no_nav.py", "code": no_nav, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "never navigates" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_guarded_save_refuses_to_overwrite_an_existing_file(client):
    project_id, _requirement_id = await _seed(client, criteria="Valid code reduces the total")
    await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/test_existing.py", "content": "def test_ok():\n    assert 1 == 1\n"},
    )
    conflict = await client.put(
        f"/api/workspaces/{project_id}/file",
        json={
            "path": "tests/test_existing.py",
            "content": "def test_ok():\n    assert 2 == 2\n",
            "expected_exists": False,
        },
    )
    assert conflict.status_code == 409

    created = await client.put(
        f"/api/workspaces/{project_id}/file",
        json={"path": "tests/test_new.py", "content": "def test_new():\n    assert 1 == 1\n", "expected_exists": False},
    )
    assert created.status_code == 200


@pytest.mark.asyncio
async def test_script_using_network_interception_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        intercepted = """from playwright.sync_api import Page, expect


def test_intercepted(page: Page):
    # criterion: AC-001
    page.route("**/api/**", lambda route: route.fulfill(status=200, body="{}"))
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")
"""
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_intercepted.py", "code": intercepted, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "builds its own page" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_script_injecting_init_script_is_rejected(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator({"assertions": [_assertion("AC-001", "Order total shows 90.00 after a 10% code")]})
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        injected = """from playwright.sync_api import Page, expect


def test_injected(page: Page):
    # criterion: AC-001
    page.add_init_script("window.__x = 1")
    page.goto("http://127.0.0.1:5183/")
    expect(page.locator("#total")).to_have_text("90.00")
"""
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_injected.py", "code": injected, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "builds its own page" in response.json()["detail"]
    finally:
        _stop()


@pytest.mark.asyncio
async def test_adopted_assertion_with_redaction_placeholder_cannot_generate(client):
    _project_id, requirement_id = await _seed(client, criteria="Valid code reduces the total")
    drafting = DraftingOrchestrator(
        {"assertions": [_assertion("AC-001", "Order total shows [REDACTED_SSN] after a 10% code")]}
    )
    _use_service(drafting)
    try:
        drafts = await _draft(client, requirement_id)
        await _adopt(client, requirement_id, drafts[0]["id"])
        _use_service(
            DraftingOrchestrator(
                {"file_path": "tests/test_redacted.py", "code": VALID_SCRIPT, "used_criterion_ids": ["AC-001"]}
            )
        )
        response = await client.post(f"/api/requirements/{requirement_id}/assertions/script")
        assert response.status_code == 422
        assert "redaction placeholder" in response.json()["detail"]
    finally:
        _stop()
