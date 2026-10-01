from __future__ import annotations

import pytest
from app.api.failures import get_failure_service
from app.main import app
from app.persistence.models import FailureRecordORM
from app.repositories.test_run_repo import TestRunRepository
from app.services.failure_service import FailureService
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
    assert applied.status_code == 422, applied.text
    assert not calls
    file = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_x.py"})
    assert file.json()["content"] == original
    async with test_db_session() as session:
        stored = await session.get(FailureRecordORM, failure_id)
        assert not stored.repair_proposal


@pytest.mark.asyncio
async def test_legacy_assertion_proposals_are_not_exposed_as_repairs(client, test_db_session):
    _, failure_id, _ = await seed_failure(
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


@pytest.mark.asyncio
async def test_noop_patch_is_rejected_even_for_locator_failure(client, test_db_session):
    _, failure_id, _ = await seed_failure(
        client,
        test_db_session,
        category="LOCATOR_CHANGED",
        error='Timeout waiting for locator("element")',
        locator="element",
    )
    response = await client.post(
        f"/api/failures/{failure_id}/apply-repair",
        params={"workspace_id": "unused"},
        json={
            "file_path": "tests/test_x.py",
            "old_code": "element",
            "new_code": "element",
        },
    )
    assert response.status_code == 400, response.text
    assert "相同" in response.json()["detail"]
