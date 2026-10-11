from __future__ import annotations

import hashlib

import pytest
from app.api.failures import get_failure_service
from app.main import app
from app.persistence.models import FailureAnalysisORM, FailureRecordORM
from app.repositories.test_run_repo import TestRunRepository
from app.services.failure_service import FailureService, _repair_source_candidates
from project_model.models import RunStatus, TestRunCreate
from qa_core.ai.provider import FakeAIProvider
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


async def seed_failure(client, test_db_session, *, category, error, locator=None, proposal=None):
    project = (
        await client.post("/api/projects", json={"name": "Repair Eligibility", "bootstrap_workspace": False})
    ).json()
    project_id = project["id"]
    content = "def test_x():\n    assert 1 == 2\n"
    response = await client.put(
        f"/api/workspaces/{project_id}/file", json={"path": "tests/test_x.py", "content": content}
    )
    assert response.status_code == 200
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id))
        execution = await repository.add_execution(run.id, "tests/test_x.py::test_x", status=RunStatus.FAILED)
        failure = await repository.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid="tests/test_x.py::test_x",
            test_name="test_x",
            classification=category,
            exception_type="TestError",
            error_message=error,
            stack_trace="",
            failing_locator=locator,
            repair_proposal=proposal,
        )
        await session.commit()
        return project_id, failure.id, content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "error", "locator"),
    [
        ("ASSERTION_FAILURE", "E assert 1 == 2", None),
        ("LOCATOR_CHANGED", "E assert 1 == 2", "element"),  # Legacy or incorrect stored classification.
        ("TIMING_ISSUE", "TimeoutError: Navigation timed out", None),
        ("ENVIRONMENT_ERROR", "Connection refused", None),
        ("UNKNOWN", "Unexpected test failure", None),
        ("LOCATOR_CHANGED", "Timeout waiting for locator", None),
    ],
)
async def test_inapplicable_repairs_are_rejected_before_ai_or_workspace_changes(
    client,
    test_db_session,
    monkeypatch,
    category,
    error,
    locator,
):
    project_id, failure_id, original = await seed_failure(
        client,
        test_db_session,
        category=category,
        error=error,
        locator=locator,
    )
    calls = []

    async def unexpected_diagnosis(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Inapplicable repair must not call the model")

    monkeypatch.setattr(FailureService, "diagnose_failure_ai", unexpected_diagnosis)
    path = f"/api/failures/{failure_id}"
    proposal = await client.post(path + "/repair-proposal")
    assert proposal.status_code == 422, proposal.text
    review = await client.post(path + "/semantic-review", params={"candidate_locator": "#new"})
    assert review.status_code == 422, review.text
    applied = await client.post(
        path + "/apply-repair",
        params={"workspace_id": project_id},
        json={
            "file_path": "tests/test_x.py",
            "old_code": "assert 1 == 2",
            "new_code": "assert 1 == 1",
        },
    )
    assert applied.status_code == 400, applied.text
    assert "No repair analysis exists" in applied.json()["detail"]
    assert not calls
    file = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_x.py"})
    assert file.json()["content"] == original
    async with test_db_session() as session:
        stored = await session.get(FailureRecordORM, failure_id)
        assert not stored.repair_proposal


@pytest.mark.asyncio
async def test_legacy_assertion_proposals_are_not_exposed_as_repairs(client, test_db_session):
    project_id, failure_id, content = await seed_failure(
        client,
        test_db_session,
        category="LOCATOR_CHANGED",
        error="AssertionError: assert 1 == 2",
        locator="element",
        proposal={"old_locator": "element", "proposed_locator": "element", "strategy": "fallback", "confidence": 0},
    )
    response = await client.get(f"/api/failures/{failure_id}")
    assert response.status_code == 200
    assert response.json()["classification"] == "ASSERTION_FAILURE"
    assert response.json()["failing_locator"] is None
    assert response.json()["repair_proposal"] is None


@pytest.mark.asyncio
async def test_real_locator_failure_without_candidate_does_not_create_noop_proposal(client, test_db_session):
    _, failure_id, _ = await seed_failure(
        client,
        test_db_session,
        category="LOCATOR_CHANGED",
        error='Timeout waiting for locator("#old")',
        locator="#old",
    )
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        app.dependency_overrides[get_failure_service] = lambda: service
        try:
            response = await client.post(f"/api/failures/{failure_id}/repair-proposal")
            assert response.status_code == 422, response.text
            stored = await session.get(FailureRecordORM, failure_id)
            assert not stored.repair_proposal
        finally:
            app.dependency_overrides.pop(get_failure_service, None)


def test_repair_sources_include_only_allowed_traceback_frames(tmp_path):
    paths = _repair_source_candidates(
        "tests/test_known_locator.py::test_known_locator_change",
        "tests/test_known_locator.py:12: in test_known_locator_change\n"
        "pages/shop.py:35: in add_with_legacy_locator\n"
        "apps/store.py:10: in add",
        tmp_path,
    )
    assert paths == ["tests/test_known_locator.py", "pages/shop.py"]


def test_page_object_locator_calls_are_patchable_without_test_function_scope():
    source = "class ShopPage:\n    def add(self):\n        self.page.locator('#legacy-add').click()\n"
    assert FailureService._locator_call_count(source, "#legacy-add") == 1
    assert FailureService._locator_call_count(source, "#legacy-add", function_name="test_known_locator_change") == 0


@pytest.mark.asyncio
async def test_verified_repair_can_patch_allowlisted_page_object_source(client, test_db_session):
    project_id, failure_id, _ = await seed_failure(
        client,
        test_db_session,
        category="LOCATOR_CHANGED",
        error='Timeout waiting for locator("#legacy-add")',
        locator="#legacy-add",
    )
    page_path = "pages/shop.py"
    page_source = "class ShopPage:\n    def add(self):\n        self.page.locator('#legacy-add').click()\n"
    response = await client.put(f"/api/workspaces/{project_id}/file", json={"path": page_path, "content": page_source})
    assert response.status_code == 200, response.text
    analysis_id = "repair-analysis-page-object"
    proposal = {
        "file_path": page_path,
        "old_locator": "#legacy-add",
        "proposed_locator": 'get_by_role("button", name="Add to cart")',
        "provider": "jev",
        "model": "jev-1.13.0",
        "ai_provider": "openai-compatible",
        "ai_fallback_used": False,
        "resolved_classification": "LOCATOR_CHANGED",
        "candidate_id": "candidate-1",
        "verified": True,
        "confidence": 0.99,
        "code_diff": "- self.page.locator('#legacy-add')\n+ self.page.get_by_role('button', name='Add to cart')",
        "source_sha256": hashlib.sha256(page_source.encode()).hexdigest(),
        "decision_summary": {
            "provider": "jev",
            "fallback_used": False,
            "verification_source": "playwright",
            "confidence": 0.99,
        },
    }
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = proposal
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": "PATCH_READY", "repair_proposal": proposal},
            )
        )
        await session.commit()

    applied = await client.post(
        f"/api/failures/{failure_id}/analyses/{analysis_id}/apply",
        json={
            "file_path": page_path,
            "old_code": "#legacy-add",
            "new_code": proposal["proposed_locator"],
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert applied.json()["repair"]["state"] == "PATCH_APPLIED"
    updated = await client.get(f"/api/workspaces/{project_id}/file", params={"path": page_path})
    assert 'self.page.get_by_role("button", name="Add to cart")' in updated.json()["content"]


@pytest.mark.asyncio
async def test_noop_patch_is_rejected_even_for_locator_failure(client, test_db_session):
    project_id, failure_id, content = await seed_failure(
        client,
        test_db_session,
        category="LOCATOR_CHANGED",
        error='Timeout waiting for locator("element")',
        locator="element",
    )
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = {
            "file_path": "tests/test_x.py",
            "old_locator": "element",
            "proposed_locator": "element",
            "provider": "jev",
            "ai_provider": "openai-compatible",
            "ai_fallback_used": False,
            "candidate_id": "candidate-1",
            "verified": True,
            "code_diff": "- element\n+ element",
            "resolved_classification": "LOCATOR_CHANGED",
            "source_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "decision_summary": {
                "fallback_used": False,
                "verification_source": "playwright",
                "confidence": 0.95,
            },
        }
        session.add(
            FailureAnalysisORM(
                id="repair-analysis-noop",
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": dict(failure.repair_proposal),
                },
            )
        )
        await session.commit()
    response = await client.post(
        f"/api/failures/{failure_id}/apply-repair",
        params={"workspace_id": project_id},
        json={
            "file_path": "tests/test_x.py",
            "old_code": "element",
            "new_code": "element",
        },
    )
    assert response.status_code == 400, response.text
    assert "相同" in response.json()["detail"]


def test_failure_locator_can_come_from_the_observed_failed_browser_action():
    failure = type(
        "Failure",
        (),
        {"error_message": "AssertionError: checkout did not complete", "stack_trace": "", "failing_locator": None},
    )()
    evidence = {
        "recent_steps": [
            {"action": "click", "locator": "#view-order", "status": "PASSED"},
            {"action": "click", "locator": "css=#purchase-now", "status": "FAILED"},
        ]
    }
    assert FailureService._observed_failed_locator(evidence) == "#purchase-now"
    assert (
        FailureService._require_locator_failure(
            failure,
            resolved_classification="LOCATOR_CHANGED",
            observed_locator=FailureService._observed_failed_locator(evidence),
        )
        == "#purchase-now"
    )
