from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest
from app.api.failures import get_failure_service
from app.main import app
from app.persistence.models import BrowserSessionORM, FailureAnalysisORM
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory, TaskRepositoryUnitOfWork
from app.repositories.test_run_repo import TestRunRepository
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.locator_decision_service import LocatorDecisionService
from app.services.locator_history_service import LocatorHistoryService
from app.services.test_run_service import TestRunService as RunApplicationService
from project_model.models import ApplyRepairRequest, DecisionResult, FailureRepairState, RunStatus, TestRunCreate
from qa_core.ai.models import FailureAnalysisResponse
from qa_core.ai.provider import FakeAIProvider
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


def make_run_service(failure_service, session):
    repositories = TaskRepositoryUnitOfWork(session)
    return RunApplicationService(
        failure_service.run_repo,
        failure_service.workspace_repo,
        failure_service.workspace_service,
        repository_scope=TaskRepositoryScopeFactory(),
        repositories=repositories,
        runner_repo=repositories.runner_profiles,
    )


@pytest.mark.asyncio
async def test_verified_locator_heal_is_counted_once_and_unverified_is_not(client, test_db_session):
    from app.persistence.models import FailureAnalysisORM, LocatorHistoryORM
    from sqlalchemy import select

    _project, failure_id, _source = await seed(client, test_db_session, error="AssertionError: mismatch")
    async with test_db_session() as session:
        session.add(FailureAnalysisORM(id="analysis-heal", failure_id=failure_id, result={"verified": False}))
        await session.commit()
    service = LocatorHistoryService(TaskRepositoryScopeFactory())
    await service.record(
        "https://example.test/cart",
        'get_by_role("button", name="Help")',
        True,
        verification=True,
        healed=True,
        healed_analysis_id="analysis-heal",
    )
    async with test_db_session() as session:
        assert (await session.execute(select(LocatorHistoryORM))).scalars().all() == []
        analysis = await session.get(FailureAnalysisORM, "analysis-heal")
        analysis.result = {"verified": True}
        await session.commit()
    for _ in range(3):
        await service.record(
            "https://example.test/cart",
            'get_by_role("button", name="Help")',
            True,
            verification=True,
            healed=True,
            healed_analysis_id="analysis-heal",
        )
    async with test_db_session() as session:
        history = (await session.execute(select(LocatorHistoryORM))).scalar_one()
        assert history.heal_count == history.verification_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_type", ["LOCAL", "WORKER", "JENKINS"])
async def test_repair_verification_command_creates_and_links_exact_idempotent_run(client, test_db_session, runner_type):
    from app.persistence.models import FailureRecordORM, TestRunORM
    from sqlalchemy import select

    project_id, failure_id, _ = await seed(
        client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI"
    )
    analysis_id = "repair-analysis-command"
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        original_run = await session.get(TestRunORM, failure.run_id)
        original_run.runner_type = runner_type
        applied_proposal = {
            "applied": True,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "candidate_id": "candidate-verification",
            "file_path": "tests/test_workflow.py",
            "proposed_locator": "#checkout-new",
        }
        failure.repair_proposal = applied_proposal
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_APPLIED",
                    "repair_proposal": applied_proposal,
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        failure_service = get_failure_service(session)
        runs = make_run_service(failure_service, session)
        runs._schedule_run_if_queued = lambda *_args, **_kwargs: None
        workflow = FailureWorkflowService(failure_service, run_service=runs)
        run = await workflow.start_verification(failure_id, analysis_id, monitor=False)
        repeated = await workflow.start_verification(failure_id, analysis_id, monitor=False)
        assert run.id == repeated.id
        assert run.project_id == project_id
        assert run.workspace_id == project_id
        assert run.nodeids == ["tests/test_workflow.py::test_workflow"]
        assert run.origin_failure_id == failure_id
        assert run.runner_type == runner_type

        history = await workflow.list_history(failure_id)
        assert history[0]["result"]["verification_run_id"] == run.id
        persisted = (
            (await session.execute(select(TestRunORM).where(TestRunORM.origin_failure_id == failure_id)))
            .scalars()
            .all()
        )
        assert len(persisted) == 1


@pytest.mark.asyncio
async def test_concurrent_failure_analysis_requests_share_one_active_analysis(client, test_db_session):
    from sqlalchemy import select

    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as first_session, test_db_session() as second_session:
        scope = TaskRepositoryScopeFactory()
        first = FailureWorkflowService(get_failure_service(first_session), repository_scope=scope)
        second = FailureWorkflowService(get_failure_service(second_session), repository_scope=scope)
        claims = await asyncio.gather(first.start_analysis(failure_id), second.start_analysis(failure_id))

    assert claims[0][0] == claims[1][0]
    assert sum(created for _, created in claims) == 1
    async with test_db_session() as session:
        active = (
            (
                await session.execute(
                    select(FailureAnalysisORM).where(
                        FailureAnalysisORM.failure_id == failure_id,
                        FailureAnalysisORM.status == "RUNNING",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(active) == 1


@pytest.mark.asyncio
async def test_repair_verification_api_exposes_resource_command(client, test_db_session, monkeypatch):
    from app.persistence.models import FailureRecordORM

    project_id, failure_id, _ = await seed(
        client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI"
    )
    analysis_id = "repair-analysis-api"
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        applied_proposal = {
            "applied": True,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "candidate_id": "candidate-api",
            "file_path": "tests/test_workflow.py",
            "proposed_locator": "#checkout-new",
        }
        failure.repair_proposal = applied_proposal
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": applied_proposal,
                },
            )
        )
        await session.commit()
        service = get_failure_service(session)
        monkeypatch.setattr(RunApplicationService, "_schedule_local_run", lambda *_args, **_kwargs: None)
        app.dependency_overrides[get_failure_service] = lambda: service
        try:
            response = await client.post(f"/api/failures/{failure_id}/analyses/{analysis_id}/verification/run")
        finally:
            app.dependency_overrides.pop(get_failure_service, None)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["project_id"] == project_id
        assert body["workspace_id"] == project_id
        assert body["nodeids"] == ["tests/test_workflow.py::test_workflow"]
        assert body["origin_failure_id"] == failure_id


@pytest.mark.asyncio
async def test_repair_verification_command_requires_applied_repair(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    analysis_id = "repair-analysis-not-applied"
    async with test_db_session() as session:
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": "PATCH_READY"},
            )
        )
        await session.commit()

    async with test_db_session() as session:
        failure_service = get_failure_service(session)
        runs = make_run_service(failure_service, session)
        workflow = FailureWorkflowService(failure_service, run_service=runs)
        with pytest.raises(ValueError, match="Apply the verified repair"):
            await workflow.start_verification(failure_id, analysis_id)


@pytest.mark.asyncio
async def test_failed_analysis_does_not_remain_in_analyzing_repair_state(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    analysis_id = "failed-analysis-not-analyzing"
    async with test_db_session() as session:
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="FAILED",
                result={"repair_state": "ANALYZING"},
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id, analysis_id)

    assert state.state == "BLOCKED"
    assert state.allowed_actions == ["START_ANALYSIS"]

    async with test_db_session() as session:
        workflow = FailureWorkflowService(get_failure_service(session))
        first_id, first_started = await workflow.start_analysis(failure_id)
        second_id, second_started = await workflow.start_analysis(failure_id)

    assert first_started is True
    assert second_started is False
    assert second_id == first_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repair_state", "expected_actions"),
    [
        ("FAILED", ["START_ANALYSIS"]),
        ("BLOCKED", ["START_ANALYSIS"]),
    ],
)
async def test_retryable_terminal_failure_states_allow_fresh_analysis(
    client, test_db_session, repair_state, expected_actions
):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        session.add(
            FailureAnalysisORM(
                id=f"analysis-{repair_state.lower()}",
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": repair_state},
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id)

    assert state.state == repair_state
    assert state.allowed_actions == expected_actions


@pytest.mark.asyncio
@pytest.mark.parametrize("verification_source", ["playwright", "playwright_snapshot"])
@pytest.mark.parametrize("stored_state", ["PATCH_READY", "BLOCKED"])
async def test_patch_ready_workflow_keeps_apply_reject_and_fresh_analysis(
    client, test_db_session, verification_source, stored_state
):
    from app.persistence.models import FailureRecordORM

    _, failure_id, _ = await seed(client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI")
    proposal = {
        "proposed_locator": 'get_by_test_id("checkout-new")',
        "verified": True,
        "provider": "jev",
        "decision_summary": {
            "fallback_used": False,
            "verification_source": verification_source,
            "confidence": 0.92,
        },
        "ai_provider": "openai-compatible",
        "ai_fallback_used": False,
        "candidate_id": "candidate_1",
        "code_diff": "- locator(#checkout)\n+ get_by_test_id(checkout-new)",
        "source_sha256": "source-hash",
    }
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = proposal
        session.add(
            FailureAnalysisORM(
                id="analysis-patch-ready",
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": stored_state, "repair_proposal": proposal},
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id)

    assert state.state == "PATCH_READY"
    assert state.allowed_actions == ["APPLY", "REJECT", "START_ANALYSIS"]


@pytest.mark.asyncio
async def test_terminal_manual_verification_records_completion_even_if_state_was_not_reconciled(
    client, test_db_session
):
    from app.persistence.models import FailureRecordORM
    from qa_core.ai.trace import make_trace_event

    project_id, failure_id, _ = await seed(
        client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI"
    )
    analysis_id = "analysis-manual-verify"
    proposal = {
        "proposed_locator": 'get_by_test_id("checkout-new")',
        "verified": True,
        "provider": "jev",
        "decision_summary": {
            "fallback_used": False,
            "verification_source": "playwright",
            "confidence": 0.92,
        },
        "ai_provider": "openai-compatible",
        "ai_fallback_used": False,
        "candidate_id": "candidate_1",
        "code_diff": "- old locator\\n+ new locator",
        "source_sha256": "source-hash",
        "applied": True,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "file_path": "tests/test_workflow.py",
    }
    async with test_db_session() as session:
        repo = TestRunRepository(session)
        failure = await session.get(FailureRecordORM, failure_id)
        verification_run = await repo.create_run(
            TestRunCreate(
                project_id=project_id,
                workspace_id=project_id,
                parent_run_id=failure.run_id,
                origin_failure_id=failure_id,
                nodeids=[failure.test_nodeid],
            )
        )
        verification_run.status = RunStatus.PASSED.value
        verification_run.total = 1
        verification_run.passed = 1
        await repo.add_execution(verification_run.id, failure.test_nodeid, status=RunStatus.PASSED)
        failure.repair_proposal = proposal
        started_event = make_trace_event(
            failure.run_id,
            "verification.started",
            stage="verification",
            step_id=f"{analysis_id}:repair:verifying_fix",
            title="Verification started",
            message="Repair verification started",
            metadata={"verification_run_id": verification_run.id},
        )
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                events=[started_event.model_dump(mode="json")],
                result={
                    "repair_state": "PATCH_APPLIED",
                    "repair_proposal": proposal,
                    "verification_run_id": verification_run.id,
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        workflow = FailureWorkflowService(get_failure_service(session))
        state = await workflow.get_repair_workflow(failure_id, analysis_id)
        history = await workflow.list_history(failure_id)

    assert state.state == "VERIFIED"
    recorded_types = {event["type"] for event in history[0]["events"]}
    assert "verification.completed" in recorded_types
    assert "repair.verified" in recorded_types


@pytest.mark.asyncio
async def test_failed_applied_patch_requires_rollback_before_reanalysis(client, test_db_session):
    from app.persistence.models import FailureRecordORM, TestRunORM

    _, failure_id, _ = await seed(client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI")
    proposal = {
        "proposed_locator": 'get_by_test_id("checkout-new")',
        "verified": True,
        "provider": "jev",
        "decision_summary": {"fallback_used": False, "verification_source": "playwright", "confidence": 0.92},
        "ai_provider": "openai-compatible",
        "ai_fallback_used": False,
        "candidate_id": "candidate_1",
        "code_diff": "- old locator\n+ new locator",
        "source_sha256": "source-hash",
        "applied": True,
        "rollback_status": "AVAILABLE",
    }
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        original_run = await session.get(TestRunORM, failure.run_id)
        original_run.status = RunStatus.FAILED
        failure.repair_proposal = proposal
        session.add(
            FailureAnalysisORM(
                id="analysis-failed-applied",
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "FAILED",
                    "repair_proposal": proposal,
                    "verification_run_id": failure.run_id,
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id)

    assert state.state == "FAILED"
    assert "ROLLBACK" in state.allowed_actions
    assert "START_ANALYSIS" not in state.allowed_actions


@pytest.mark.asyncio
async def test_rolled_back_patch_allows_fresh_analysis(client, test_db_session):
    from app.persistence.models import FailureRecordORM

    _, failure_id, _ = await seed(client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI")
    proposal = {"proposed_locator": 'get_by_test_id("checkout-new")', "rollback_status": "ROLLED_BACK"}
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = proposal
        session.add(
            FailureAnalysisORM(
                id="analysis-rolled-back",
                failure_id=failure_id,
                status="COMPLETED",
                result={"repair_state": "ROLLED_BACK", "repair_proposal": proposal},
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id)

    assert state.state == "ROLLED_BACK"
    assert state.allowed_actions == ["START_ANALYSIS"]


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_type", ["LOCAL", "WORKER", "JENKINS"])
async def test_workflow_authorizes_retry_from_real_diagnosis_and_starts_one_server_run(
    client, test_db_session, runner_type
):
    from app.persistence.models import FailureRecordORM, TestRunORM

    project_id, failure_id, _ = await seed(client, test_db_session, error="Connection timed out")
    analysis_id = "failure-retry-command"
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        original = await session.get(TestRunORM, failure.run_id)
        original.runner_type = runner_type
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "NOT_APPLICABLE",
                    "diagnosis": {
                        "classification": "NETWORK",
                        "provider": "openai-compatible",
                        "fallback_used": False,
                    },
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        service = get_failure_service(session)
        runs = make_run_service(service, session)
        runs._schedule_run_if_queued = lambda *_args, **_kwargs: None
        workflow = FailureWorkflowService(service, run_service=runs)
        state = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert "RETRY" in state.allowed_actions
        retry = await workflow.start_retry(failure_id, analysis_id)
        repeated = await workflow.start_retry(failure_id, analysis_id)
        assert retry.id == repeated.id
        assert retry.project_id == project_id
        assert retry.nodeids == ["tests/test_workflow.py::test_workflow"]
        assert retry.origin_failure_id == failure_id
        assert retry.runner_type == runner_type
        refreshed = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert refreshed.retry_run_id == retry.id
        assert "RETRY" not in refreshed.allowed_actions


@pytest.mark.asyncio
async def test_workflow_does_not_authorize_retry_or_issue_draft_from_fake_diagnosis(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    analysis_id = "failure-fake-diagnosis"
    async with test_db_session() as session:
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "NOT_APPLICABLE",
                    "diagnosis": {
                        "classification": "PRODUCT_DEFECT",
                        "provider": "fake",
                        "fallback_used": False,
                    },
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        state = await FailureWorkflowService(get_failure_service(session)).get_repair_workflow(failure_id, analysis_id)
        assert "RETRY" not in state.allowed_actions
        assert "CREATE_ISSUE_DRAFT" not in state.allowed_actions


async def seed(
    client,
    test_db_session,
    *,
    error,
    kind="PYTHON",
    candidates=None,
    url="http://localhost/checkout",
    source="def test_workflow():\n    actual = 1\n    assert actual == 2\n",
):
    project = (
        await client.post("/api/projects", json={"name": "Workflow evidence", "bootstrap_workspace": False})
    ).json()
    written = await client.put(
        f"/api/workspaces/{project['id']}/file", json={"path": "tests/test_workflow.py", "content": source}
    )
    assert written.status_code == 200
    async with test_db_session() as session:
        repo = TestRunRepository(session)
        run = await repo.create_run(
            TestRunCreate(project_id=project["id"], workspace_id=project["id"], environment={"QA_REGION": "JP"})
        )
        execution = await repo.add_execution(run.id, "tests/test_workflow.py::test_workflow", status=RunStatus.FAILED)
        failure = await repo.create_failure_record(
            run_id=run.id,
            execution_id=execution.id,
            test_nodeid=execution.nodeid,
            test_name="test_workflow",
            classification="UNKNOWN",
            exception_type="TestError",
            error_message=error,
            stack_trace="tests/test_workflow.py:3",
            failing_locator="#checkout" if kind == "UI" else None,
        )
        if kind == "UI":
            session.add(
                BrowserSessionORM(
                    id="workflow-browser",
                    run_id=run.id,
                    case_execution_id=execution.id,
                    browser_session_id="browser",
                    page_id="page",
                    nodeid=execution.nodeid,
                    current_url=url,
                    page_evidence_json=json.dumps(
                        {
                            "url": url,
                            "controls": [
                                {"visible": True, "enabled": True, "candidates": [candidate]}
                                for candidate in (
                                    candidates
                                    or [
                                        {"kind": "test_id", "value": "checkout-submit"},
                                        {"kind": "role", "value": "button", "name": "Checkout"},
                                        {"kind": "text", "value": "Checkout"},
                                        {"kind": "id", "value": "checkout-new"},
                                    ]
                                )
                            ],
                        }
                    ),
                )
            )
        await session.commit()
        return project["id"], failure.id, source


@pytest.mark.asyncio
async def test_rollback_history_is_idempotent_and_resists_stale_failure_updates(client, test_db_session):
    from qa_core.ai.trace import make_trace_event

    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        service = get_failure_service(session)
        workflow = FailureWorkflowService(service)
        failure = await service.get_failure_state(failure_id)
        analysis_id = await workflow._history_create(failure_id)
        rollback_event = make_trace_event(
            failure.run_id,
            "repair.rolled_back",
            stage="repair",
            step_id=f"{analysis_id}:repair:rolled_back",
            title="Repair patch rolled back",
            message="The failed repair was safely rolled back",
            metadata={"state": "ROLLED_BACK", "automatic": True},
        )
        await workflow._history_append(
            analysis_id,
            make_trace_event(
                failure.run_id,
                "repair.rolled_back",
                stage="repair",
                step_id=f"{analysis_id}:repair:rolled_back",
                title="Repair patch rolled back",
                message="The failed repair was safely rolled back",
                metadata={"state": "ROLLED_BACK", "automatic": True, "verification_run_id": "run-stale"},
            ),
            result={"repair_state": "ROLLED_BACK", "auto_rolled_back": True, "changes_applied": False},
        )
        await workflow._history_append(
            analysis_id,
            make_trace_event(
                failure.run_id,
                "repair.failed",
                stage="repair",
                step_id=f"{analysis_id}:repair:failed",
                title="Repair verification failed",
                message="A stale concurrent reconciliation",
                metadata={"state": "FAILED"},
            ),
            result={"repair_state": "FAILED", "changes_applied": True},
        )
        await workflow._history_append(
            analysis_id,
            rollback_event,
            result={"repair_state": "ROLLED_BACK", "auto_rolled_back": True, "changes_applied": False},
        )
        row = next(item for item in await workflow._history_list(failure_id) if item["id"] == analysis_id)

    assert row["result"] == {
        "repair_state": "ROLLED_BACK",
        "auto_rolled_back": True,
        "changes_applied": False,
    }
    assert [event["type"] for event in row["events"]].count("repair.rolled_back") == 1
    assert not any(event["type"] == "repair.failed" for event in row["events"])


@pytest.mark.asyncio
async def test_successful_ai_classification_is_not_overwritten_by_rule_classification(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        service = get_failure_service(session)

        class SuccessfulDiagnosis:
            ai_provider = type("Provider", (), {"records_usage": True})()
            last_completion = None

            async def diagnose_failure_ai(self, **_kwargs):
                return FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The failing test step uses a locator that no longer matches its target.",
                    provider="openai-compatible",
                    fallback_used=False,
                    confidence=0.92,
                )

            @staticmethod
            def last_invocation_metadata():
                return {
                    "provider": "openai-compatible",
                    "model": "unit-test-model",
                    "fallback_used": False,
                    "prompt_version": "test",
                }

        service.orchestrator = SuccessfulDiagnosis()
        diagnosis = await service.diagnose_failure_ai(failure_id)

    assert diagnosis.classification == "LOCATOR_CHANGED"
    assert diagnosis.provider == "openai-compatible"
    assert diagnosis.fallback_used is False


class RecordingDecision:
    def __init__(self, *, fallback=False, confidence=0.95, probability=0.95):
        self.calls = []
        self.signal_calls = []
        self.fallback = fallback
        self.confidence = confidence
        self.probability = probability

    async def choose(self, request, **kwargs):
        self.calls.append(request)
        return DecisionResult(
            choice=request.options[0].key,
            provider="jev",
            model="unit-test-jev",
            confidence=self.confidence,
            fallback_used=self.fallback,
            reason="unit-test-fallback" if self.fallback else None,
        )

    async def ask_probability(self, request, **kwargs):
        self.signal_calls.append(request)
        return DecisionResult(
            probability=self.probability,
            provider="fallback" if self.fallback else "jev",
            model="unit-test-jev",
            confidence=self.confidence,
            fallback_used=self.fallback,
            reason="unit-test-fallback" if self.fallback else None,
        )


@pytest.mark.asyncio
async def test_automatic_failure_analysis_requires_human_approval_before_patch(
    client, test_db_session, local_html_url, monkeypatch
):
    url = local_html_url('<button aria-label="Complete order">Continue</button>')
    source = 'def test_workflow(page):\n    page.locator("#checkout").click()\n'
    project_id, failure_id, _ = await seed(
        client,
        test_db_session,
        error='AssertionError: locator("#checkout") did not resolve',
        kind="UI",
        candidates=[{"kind": "role", "value": "button", "name": "Complete order", "exact": True}],
        url=url,
        source=source,
    )
    decision = RecordingDecision()
    async with test_db_session() as session:
        service = get_failure_service(session)

        async def diagnose(*_args, **_kwargs):
            return FailureAnalysisResponse(
                classification="LOCATOR_CHANGED",
                root_cause="The checkout locator changed to an accessible Complete order button.",
                provider="openai-compatible",
                fallback_used=False,
                confidence=0.94,
            )

        service.diagnose_failure_ai = diagnose
        runs = make_run_service(service, session)
        runs._schedule_local_run = lambda *_args, **_kwargs: None
        workflow = FailureWorkflowService(
            service,
            LocatorDecisionService(decision_service=decision),
            run_service=runs,
            auto_repair_mode="AUTO",
        )

        async def ready_for_analysis():
            return {"ready": True}

        monkeypatch.setattr(workflow, "_runtime_readiness", ready_for_analysis)
        events = [event async for event in workflow.stream(failure_id, auto_triggered=True)]
        completed = next(event for event in events if event.type == "run.completed")
        result = completed.metadata
        proposal = result["repair_proposal"]
        analysis_id = result["analysis_id"]

        assert events[-1].type == "run.completed"
        assert result["initial_classification"] == "ASSERTION_FAILURE"
        assert result["resolved_classification"] == "LOCATOR_CHANGED"
        assert result["classification_source"] == "AI_DIAGNOSIS"
        assert len(decision.calls) == 1
        assert result["selection"]["provider"] == "jev"
        assert proposal["proposed_locator"] == 'get_by_role("button", name="Complete order", exact=True)'
        assert proposal["verified"] is True
        assert proposal["code_diff"]
        assert result["repair_state"] == "PATCH_READY"
        assert result["changes_applied"] is False
        assert result.get("verification_run_id") is None
        assert not any(
            event.type == "workflow.step" and event.stage == "verification" and event.metadata.get("test_rerun") is True
            for event in events
        )
        workflow_state = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert workflow_state.state == "PATCH_READY"
        assert "APPLY" in workflow_state.allowed_actions
        assert await service.workspace_service.read_file(project_id, "tests/test_workflow.py") == source

        # The explicit approval path still applies the exact reviewed proposal and supports rollback.
        await workflow.apply_repair(
            failure_id,
            analysis_id,
            ApplyRepairRequest(
                file_path=proposal["file_path"],
                old_code=proposal["source_locator"],
                new_code=proposal["proposed_locator"],
            ),
        )
        verification_run = await workflow.start_verification(failure_id, analysis_id)
        assert verification_run.nodeids == ["tests/test_workflow.py::test_workflow"]
        verification_monitors = tuple(workflow._verification_monitors)
        await service.run_repo.update_run_status(
            verification_run.id,
            RunStatus.FAILED,
            failed=1,
            total=1,
            log_output="Simulated asynchronous verification failure",
        )
        await service.run_repo.add_execution(
            verification_run.id,
            "tests/test_workflow.py::test_workflow",
            RunStatus.FAILED,
            error_message="Simulated asynchronous verification failure",
        )
        await session.commit()

    run_response = await client.get(f"/api/runs/{verification_run.id}")
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["nodeids"] == ["tests/test_workflow.py::test_workflow"]
    patched_response = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"})
    assert patched_response.status_code == 200, patched_response.text
    assert proposal["proposed_locator"] in patched_response.json()["content"]

    history = []
    for _ in range(30):
        await asyncio.sleep(0.1)
        async with test_db_session() as session:
            history = await FailureWorkflowService(get_failure_service(session))._history_list(failure_id)
        if history[0]["result"].get("auto_rolled_back"):
            break
    assert len(history) == 1, "A failed verification must not start another unattended analysis."
    assert history[0]["result"]["repair_state"] == "ROLLED_BACK", history[0]["result"]
    assert history[0]["result"]["auto_rolled_back"] is True
    assert history[0]["result"]["changes_applied"] is False
    assert any(event["type"] == "repair.rolled_back" for event in history[0]["events"])
    restored_response = await client.get(
        f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"}
    )
    assert restored_response.status_code == 200, restored_response.text
    assert restored_response.json()["content"] == source
    await asyncio.gather(*verification_monitors, return_exceptions=True)


@pytest.mark.asyncio
async def test_repair_releases_snapshot_write_transaction_before_jev_budget_reservation(client, test_db_session):
    from types import SimpleNamespace

    from app.services.ai_execution_service import AIExecutionService
    from app.services.failure_service import LocatorRepairNotApplicableError
    from project_model.models import FailureSnapshotBundle

    _, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        source='def test_workflow(page):\n    page.locator("#checkout").click()\n',
    )
    async with test_db_session() as session:
        browser = await session.get(BrowserSessionORM, "workflow-browser")
        browser.failure_snapshot_json = FailureSnapshotBundle(
            status="PARTIAL", url="http://localhost/checkout", failed_locator="#checkout"
        ).model_dump_json()
        await session.commit()

    class Browser:
        async def create_session(self):
            return SimpleNamespace(id="verification-session")

        async def navigate(self, *_args, **_kwargs):
            pass

        async def close_session(self, *_args):
            pass

    reservations = []

    class BudgetedDecision:
        async def decide(self, **_kwargs):
            reservations.append("started")
            await AIExecutionService.reserve_daily_limit(100, TaskRepositoryScopeFactory())
            reservations.append("reserved")
            return {}

    async with test_db_session() as session:
        service = get_failure_service(session)
        service.browser_runtime = Browser()
        with pytest.raises(LocatorRepairNotApplicableError):
            await service.generate_repair_proposal(
                failure_id,
                diagnosis_override=FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The checkout selector changed.",
                    provider="openai-compatible",
                    fallback_used=False,
                    confidence=0.95,
                ),
                resolved_classification="LOCATOR_CHANGED",
                decision_service=BudgetedDecision(),
            )
    assert reservations == ["started", "reserved"]


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupted_state", [FailureRepairState.APPLYING, FailureRepairState.PATCH_READY])
async def test_manual_repair_persists_applied_and_rolled_back_state(
    client, test_db_session, local_html_url, monkeypatch, interrupted_state
):
    url = local_html_url('<button type="submit">Continue</button>')
    source = 'def test_workflow(page):\n    page.locator("#old-submit").click()\n'
    project_id, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#old-submit")',
        kind="UI",
        candidates=[{"kind": "role", "value": "button", "name": "Continue", "exact": True}],
        url=url,
        source=source,
    )
    analysis_id = "manual-repair-state-transition"

    async with test_db_session() as session:
        service = get_failure_service(session)
        decision = RecordingDecision()
        proposal = await service.generate_repair_proposal(
            failure_id,
            diagnosis_override=FailureAnalysisResponse(
                classification="LOCATOR_CHANGED",
                root_cause="The checkout submit button has a new selector.",
                provider="openai-compatible",
                fallback_used=False,
                confidence=0.95,
            ),
            resolved_classification="LOCATOR_CHANGED",
            decision_service=LocatorDecisionService(decision_service=decision),
        )
        assert proposal.source_locator == 'page.locator("#old-submit")'
        assert proposal.code_diff
        assert proposal.decision_summary["same_function_signal"]["probability"] == 0.95
        assert proposal.decision_summary["same_function_signal"]["advisory_only"] is True
        assert decision.signal_calls[0].state["candidate"]["candidate_id"] == proposal.candidate_id
        assert decision.signal_calls[0].state["observed_controls"]
        assert len(decision.signal_calls) == 1
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": proposal.model_dump(mode="json"),
                },
            )
        )
        await session.commit()
        workflow = FailureWorkflowService(service)
        from app.services.workspace_service import WorkspaceService

        write_count = 0
        successful_write_count = 0
        write_file_if_unchanged = WorkspaceService.write_file_if_unchanged

        async def count_source_writes(*args, **kwargs):
            nonlocal write_count, successful_write_count
            write_count += 1
            result = await write_file_if_unchanged(*args, **kwargs)
            successful_write_count += 1
            return result

        monkeypatch.setattr(WorkspaceService, "write_file_if_unchanged", count_source_writes)

        stale_source = source + "# changed after review\n"
        await service.workspace_service.write_file(project_id, proposal.file_path, stale_source)
        with pytest.raises(ValueError, match="Source changed after repair candidates were generated"):
            await workflow.apply_repair(
                failure_id,
                analysis_id,
                ApplyRepairRequest(
                    file_path=proposal.file_path,
                    old_code=proposal.source_locator,
                    new_code=proposal.proposed_locator,
                ),
            )
        assert await service.workspace_service.read_file(project_id, proposal.file_path) == stale_source
        blocked_workflow = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert blocked_workflow.state == "PATCH_READY"
        repair_record = await workflow._locator_repair_for_analysis(analysis_id)
        assert repair_record.candidate_id == proposal.candidate_id
        assert repair_record.block_reason is None
        blocked_analysis = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert blocked_analysis["result"]["block_reason"] == "PATCH_APPLY_FAILED"
        assert blocked_analysis["result"].get("changes_applied") is not True
        await service.workspace_service.write_file(project_id, proposal.file_path, source)

        async def fail_source_write(*args, **kwargs):
            raise OSError("synthetic workspace write failure")

        monkeypatch.setattr(WorkspaceService, "write_file_if_unchanged", fail_source_write)
        with pytest.raises(OSError, match="synthetic workspace write failure"):
            await workflow.apply_repair(
                failure_id,
                analysis_id,
                ApplyRepairRequest(
                    file_path=proposal.file_path,
                    old_code=proposal.source_locator,
                    new_code=proposal.proposed_locator,
                ),
            )
        assert await service.workspace_service.read_file(project_id, proposal.file_path) == source
        failed_write_history = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert failed_write_history["result"]["block_reason"] == "PATCH_APPLY_FAILED"
        assert failed_write_history["result"]["error_type"] == "OSError"
        failed_repair = await workflow._locator_repair_for_analysis(analysis_id)
        assert failed_repair.state == FailureRepairState.PATCH_READY
        assert failed_repair.block_reason is None
        assert (await service.get_failure_state(failure_id)).repair_proposal["applied"] is False
        monkeypatch.setattr(WorkspaceService, "write_file_if_unchanged", count_source_writes)

        async def apply_from_fresh_session():
            async with test_db_session() as apply_session:
                apply_service = get_failure_service(apply_session)
                apply_workflow = FailureWorkflowService(apply_service)
                return await apply_workflow.apply_repair(
                    failure_id,
                    analysis_id,
                    ApplyRepairRequest(
                        file_path=proposal.file_path,
                        old_code=proposal.source_locator,
                        new_code=proposal.proposed_locator,
                    ),
                )

        concurrent_results = await asyncio.gather(
            apply_from_fresh_session(), apply_from_fresh_session(), return_exceptions=True
        )
        successful_applies = [result for result in concurrent_results if isinstance(result, dict)]
        rejected_applies = [result for result in concurrent_results if isinstance(result, Exception)]
        assert 1 <= len(successful_applies) <= 2, concurrent_results
        assert len(rejected_applies) + len(successful_applies) == 2, concurrent_results
        assert len(rejected_applies) <= 1, concurrent_results
        assert successful_write_count == 1
        assert all(result["status"] == "applied" for result in successful_applies)
        if rejected_applies:
            rejection = rejected_applies[0]
            # Any guard may lose the race: the repair-state or candidate-staleness check (ValueError)
            # or the workspace optimistic write guard, which is a 409 conflict by design
            # (FileExistsError). What matters is that the loser refuses to write.
            assert isinstance(rejection, (ValueError, FileExistsError)), concurrent_results
            message = str(rejection)
            assert "does not allow applying a patch" in message or "changed" in message, concurrent_results
        applied = successful_applies[0]
        assert applied["repair"]["state"] == "PATCH_APPLIED"
        applied_analysis = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert applied_analysis["result"]["changes_applied"] is True
        assert applied_analysis["result"]["repair_proposal"]["applied"] is True
        patched = await service.workspace_service.read_file(project_id, "tests/test_workflow.py")
        assert proposal.proposed_locator in patched
        applied_event_count = len(applied_analysis["events"])

        with pytest.raises(ValueError, match="does not allow applying a patch"):
            await workflow.apply_repair(
                failure_id,
                analysis_id,
                ApplyRepairRequest(
                    file_path=proposal.file_path,
                    old_code=proposal.source_locator,
                    new_code=proposal.proposed_locator,
                ),
            )
        assert await service.workspace_service.read_file(project_id, "tests/test_workflow.py") == patched
        current_workflow = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert current_workflow.state == "PATCH_APPLIED"
        assert "APPLY" not in current_workflow.allowed_actions
        current_analysis = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert len(current_analysis["events"]) == applied_event_count
        assert current_analysis["result"]["repair_proposal"]["applied"] is True

        async with workflow.repository_scope() as repositories:
            interrupted_repair = await repositories.locator_repairs.get_by_analysis(analysis_id)
            interrupted_repair.state = interrupted_state
            await repositories.commit()
        async with test_db_session() as session:
            interrupted_analysis = await session.get(FailureAnalysisORM, analysis_id)
            interrupted_analysis.result = {
                key: value
                for key, value in interrupted_analysis.result.items()
                if key not in {"changes_applied", "file_path"}
            }
            interrupted_analysis.result["repair_state"] = interrupted_state.value
            interrupted_proposal = dict(interrupted_analysis.result["repair_proposal"])
            interrupted_proposal["applied"] = False
            interrupted_analysis.result["repair_proposal"] = interrupted_proposal
            interrupted_analysis.events = [
                event for event in interrupted_analysis.events if event.get("type") != "patch.applied"
            ]
            await session.commit()

        interrupted_failure = await service.get_failure_state(failure_id)
        interrupted_history = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        selected_proposal = interrupted_history["result"]["repair_proposal"]
        interrupted_history["result"]["repair_proposal"] = {
            **selected_proposal,
            "file_path": "tests/another_file.py",
        }
        assert await workflow._recover_interrupted_apply(interrupted_failure, interrupted_history) is False
        interrupted_history["result"]["repair_proposal"] = selected_proposal
        event_count_before_stale_recovery = len(interrupted_history["events"])
        async with test_db_session() as session:
            analysis_row = await session.get(FailureAnalysisORM, analysis_id)
            analysis_row.result = {**analysis_row.result, "repair_state": "ROLLED_BACK"}
            await session.commit()
        with pytest.raises(ValueError, match="Repair state changed before patch application"):
            await workflow._recover_interrupted_apply(interrupted_failure, interrupted_history)
        unchanged_history = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert len(unchanged_history["events"]) == event_count_before_stale_recovery
        async with test_db_session() as session:
            analysis_row = await session.get(FailureAnalysisORM, analysis_id)
            analysis_row.result = {**analysis_row.result, "repair_state": interrupted_state.value}
            await session.commit()
        interrupted_history = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        await workflow._recover_interrupted_apply(interrupted_failure, interrupted_history)
        recovered_history = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert any(event["type"] == "patch.recovered" for event in recovered_history["events"])
        recovered_event_count = len(recovered_history["events"])
        await workflow._record_transition(
            interrupted_failure,
            interrupted_history,
            "PATCH_APPLIED",
            "patch.applied",
            "Late completion from the interrupted apply request",
            expected_current_state=FailureRepairState.APPLYING,
            candidate_id=proposal.candidate_id,
            changes_applied=True,
            repair_proposal=interrupted_failure.repair_proposal,
        )
        after_late_completion = next(
            row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id
        )
        assert len(after_late_completion["events"]) == recovered_event_count

        applied_content = await service.workspace_service.read_file(project_id, "tests/test_workflow.py")
        await service.workspace_service.write_file(project_id, "tests/test_workflow.py", source)
        with pytest.raises(ValueError, match="没有可回滚的修复补丁"):
            await workflow.rollback_repair(failure_id, analysis_id)
        assert (await service.get_failure_state(failure_id)).repair_proposal["applied"] is True
        await service.workspace_service.write_file(project_id, "tests/test_workflow.py", applied_content)

        failure_repo = workflow.failures.failure_repo
        persist_rollback = failure_repo.update_repair_proposal
        rollback_updates = 0

        async def fail_rollback_persistence_once(*args, **kwargs):
            nonlocal rollback_updates
            rollback_updates += 1
            result = await persist_rollback(*args, **kwargs)
            if rollback_updates == 2:
                raise RuntimeError("synthetic rollback persistence failure")
            return result

        monkeypatch.setattr(failure_repo, "update_repair_proposal", fail_rollback_persistence_once)
        with pytest.raises(RuntimeError, match="synthetic rollback persistence failure"):
            await workflow.rollback_repair(failure_id, analysis_id)
        assert await service.workspace_service.read_file(project_id, "tests/test_workflow.py") == source
        await session.rollback()
        await session.close()

        async with test_db_session() as verify_session:
            persisted_failure = await get_failure_service(verify_session).get_failure_state(failure_id)
            assert persisted_failure.repair_proposal["applied"] is True
            assert persisted_failure.repair_proposal["rollback_status"] == "ROLLBACK_PENDING"

        async with test_db_session() as retry_session:
            retry_service = get_failure_service(retry_session)
            retry_workflow = FailureWorkflowService(retry_service)
            rolled_back = await retry_workflow.rollback_repair(failure_id, analysis_id)
            assert rollback_updates == 2
            assert rolled_back["repair"]["state"] == "ROLLED_BACK"
            rolled_back_analysis = next(
                row for row in await retry_workflow._history_list(failure_id) if row["id"] == analysis_id
            )
            assert rolled_back_analysis["result"]["changes_applied"] is False
            assert rolled_back_analysis["result"]["repair_proposal"]["applied"] is False
            assert sum(event["type"] == "repair.rolled_back" for event in rolled_back_analysis["events"]) == 1
            repeated_rollback = await retry_workflow.rollback_repair(failure_id, analysis_id)
            assert repeated_rollback["repair"]["state"] == "ROLLED_BACK"
            repeated_history = next(
                row for row in await retry_workflow._history_list(failure_id) if row["id"] == analysis_id
            )
            assert sum(event["type"] == "repair.rolled_back" for event in repeated_history["events"]) == 1
            assert await retry_service.workspace_service.read_file(project_id, "tests/test_workflow.py") == source

        async with test_db_session() as final_session:
            final_failure = await get_failure_service(final_session).get_failure_state(failure_id)
            assert final_failure.repair_proposal["applied"] is False


@pytest.mark.asyncio
async def test_low_same_function_probability_blocks_locator_repair_apply(client, test_db_session):
    from app.services.failure_service import LocatorRepairNotApplicableError

    project_id, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#old-submit")',
        kind="UI",
        candidates=[{"kind": "role", "value": "button", "name": "Continue", "exact": True}],
        source='def test_workflow(page):\n    page.locator("#old-submit").click()\n',
    )
    decision = RecordingDecision(probability=0.42)
    async with test_db_session() as session:
        service = get_failure_service(session)
        with pytest.raises(LocatorRepairNotApplicableError, match="LOCATOR_IDENTITY_BELOW_THRESHOLD") as blocked:
            await service.generate_repair_proposal(
                failure_id,
                diagnosis_override=FailureAnalysisResponse(
                    classification="LOCATOR_CHANGED",
                    root_cause="The observed button may have a new accessible name.",
                    provider="openai-compatible",
                    fallback_used=False,
                    confidence=0.95,
                ),
                resolved_classification="LOCATOR_CHANGED",
                decision_service=LocatorDecisionService(decision_service=decision),
            )

    assert decision.signal_calls
    assert blocked.value.decision_summary["same_function_signal"]["probability"] == 0.42
    assert blocked.value.decision_summary["same_function_signal"]["threshold"] > 0.42
    assert any(event.type == "locator.same_function_signal" for event in blocked.value.execution_trace)


@pytest.mark.asyncio
async def test_ui_assertion_never_enters_locator_decision_even_with_page_candidates(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2", kind="UI")
    decision = RecordingDecision()
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        events = [
            event
            async for event in FailureWorkflowService(
                service, LocatorDecisionService(decision_service=decision)
            ).stream(failure_id)
        ]
        assert events[0].metadata["domain"] == "UI"
        assert events[-1].metadata["diagnosis"]["classification"] == "ASSERTION_FAILURE"
        assert not decision.calls
        assert next(event for event in events if event.stage == "decision").status == "SKIPPED"


@pytest.mark.asyncio
async def test_missing_page_evidence_blocks_locator_decision(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error='Timeout waiting for locator("#checkout")')
    decision = RecordingDecision()
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        events = [
            event
            async for event in FailureWorkflowService(
                service, LocatorDecisionService(decision_service=decision)
            ).stream(failure_id)
        ]
        assert events[0].metadata["domain"] == "UI"
        assert (
            next(event for event in events if event.stage == "inspection" and event.status != "RUNNING").status
            == "BLOCKED"
        )
        assert next(event for event in events if event.stage == "decision").status == "BLOCKED"
        assert not decision.calls
        assert events[-1].metadata["selection"] is None
        workflow_dto = await FailureWorkflowService(service).get_repair_workflow(failure_id)
        assert workflow_dto.failure_snapshot.status == "INSUFFICIENT_EVIDENCE"
        assert workflow_dto.failure_snapshot.replay.status == "INSUFFICIENT_EVIDENCE"
        assert "failure_snapshot_not_captured" in workflow_dto.failure_snapshot.evidence_gaps


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "domain"),
    [
        ("AssertionError: assert 1 == 2", "PYTHON"),
        ("TypeError: unsupported operand type(s) for +", "PYTHON"),
        ("httpx.HTTPStatusError: HTTP/1.1 500 Internal Server Error; status_code=500", "API"),
    ],
)
async def test_non_ui_workflow_is_replayable_and_never_calls_locator_decision(
    client, anonymous_client, test_db_session, error, domain
):
    project_id, failure_id, original = await seed(client, test_db_session, error=error)
    decision = RecordingDecision()
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        workflow = FailureWorkflowService(service, LocatorDecisionService(decision_service=decision))
        events = [event async for event in workflow.stream(failure_id)]
        assert events[0].metadata["domain"] == domain
        assert events[-1].type == "run.completed"
        assert not decision.calls
        context = next(event for event in events if event.stage == "context" and event.status == "COMPLETED")
        assert "JP" in context.message
        assert len(context.metadata["source_sha256"]) == 64
        assert (
            next(event for event in events if event.stage == "decision" and event.type == "workflow.step").status
            == "SKIPPED"
        )
        verification = next(event for event in events if event.stage == "verification")
        assert verification.status == "PENDING"
        assert verification.metadata["test_rerun"] is False
        persisted = await workflow.list_history(failure_id)
        assert persisted[0]["status"] == "COMPLETED"
        assert persisted[0]["events"][-1]["event_id"] == events[-1].event_id
        assert persisted[0]["result"]["verified"] is False
        await asyncio.sleep(0.01)
        await anext_second_run(workflow, failure_id)
        assert len(await workflow.list_history(failure_id)) == 2
        app.dependency_overrides[get_failure_service] = lambda: service
        try:
            streamed = await client.post(f"/api/failures/{failure_id}/analyze/stream")
            assert streamed.status_code == 200, streamed.text
            assert "text/event-stream" in streamed.headers["content-type"]
            replayed = [json.loads(line[6:]) for line in streamed.text.splitlines() if line.startswith("data: ")]
            assert replayed[-1]["type"] == "run.completed"
            assert replayed[-1]["metadata"]["verified"] is False
            history = await client.get(f"/api/failures/{failure_id}/analyses")
            assert history.status_code == 200
            assert len(history.json()) == 3
            denied = await anonymous_client.get(f"/api/failures/{failure_id}/analyses")
            assert denied.status_code == 401
        finally:
            app.dependency_overrides.pop(get_failure_service, None)
    content = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"})
    assert content.json()["content"] == original


async def anext_second_run(workflow, failure_id):
    return [event async for event in workflow.stream(failure_id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_ui_candidates_stream_the_actual_decision_engine_without_claiming_verification(
    client, test_db_session, fallback, local_html_url
):
    url = local_html_url('<button aria-label="Checkout">Checkout</button>')
    _, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        url=url,
        source='def test_workflow(page):\n    page.locator("#checkout").click()\n',
    )
    decision = RecordingDecision(fallback=fallback)
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        events = [
            event
            async for event in FailureWorkflowService(
                service, LocatorDecisionService(decision_service=decision)
            ).stream(failure_id)
        ]
        inspection = next(event for event in events if event.stage == "inspection" and event.status == "COMPLETED")
        assert inspection.metadata["candidate_count"] == 4
        assert len(decision.calls) == 1
        actual = next(event for event in events if event.type == "decision_completed")
        assert actual.metadata["provider"] == ("blocked" if fallback else "jev")
        proposal = events[-1].metadata["repair_proposal"]
        if fallback:
            assert events[-1].metadata["selection"]["provider"] == "blocked"
            assert proposal is None
        else:
            assert proposal["verified"] is True, proposal
            assert proposal["provider"] == "jev"
        assert events[-1].metadata["repair_state"] == "BLOCKED"  # Fake AI cannot authorize a repair.


def test_locator_candidates_prioritize_the_most_specific_failed_target_match():
    candidates = LocatorDecisionService.generate_candidates(
        {
            "candidates": [
                {"kind": "role", "value": "button", "name": "Cart (0)", "exact": True},
                {"kind": "role", "value": "button", "name": "Add to cart", "exact": True},
                {"kind": "test_id", "value": "add-to-cart"},
            ]
        }
    )

    relevant = LocatorDecisionService.prioritize_candidates_for_failure('[data-testid="legacy-add-cart"]', candidates)

    assert [candidate["name"] if candidate.get("name") else candidate["value"] for candidate in relevant] == [
        "Add to cart",
        "add-to-cart",
        "Cart (0)",
    ]


@pytest.mark.asyncio
async def test_semantically_unrelated_local_fallback_candidate_is_blocked_before_auto_apply(
    client, test_db_session, local_html_url
):
    url = local_html_url("<button>Logout</button>")
    _, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        candidates=[{"kind": "role", "value": "button", "name": "Logout", "exact": True}],
        url=url,
        source='def test_workflow(page):\n    page.locator("#checkout").click()\n',
    )
    decision = RecordingDecision(fallback=True)
    async with test_db_session() as session:
        service = get_failure_service(session)

        async def diagnose(*_args, **_kwargs):
            return FailureAnalysisResponse(
                classification="LOCATOR_CHANGED",
                root_cause="The failed checkout control is no longer present.",
                provider="openai-compatible",
                fallback_used=False,
                confidence=0.91,
            )

        service.diagnose_failure_ai = diagnose
        events = [
            event
            async for event in FailureWorkflowService(
                service, LocatorDecisionService(decision_service=decision)
            ).stream(failure_id)
        ]
        assert len(decision.calls) == 1
        assert decision.calls[0].options[0].description == 'get_by_role("button", name="Logout", exact=True)'
        assert events[-1].metadata["selection"]["provider"] == "blocked"
        assert events[-1].metadata["repair_proposal"] is None
        decision_event = next(event for event in events if event.type == "decision_completed")
        assert decision_event.metadata["provider"] == "blocked"
        assert decision_event.metadata["fallback_used"] is True
        assert events[-1].metadata["repair_state"] == "BLOCKED"
        assert events[-1].metadata["changes_applied"] is False


@pytest.mark.asyncio
async def test_jev_low_confidence_is_blocked_after_playwright_and_never_applied(
    client, test_db_session, local_html_url
):
    url = local_html_url('<button aria-label="Checkout">Checkout</button>')
    project_id, failure_id, source = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        url=url,
        source='def test_workflow(page):\n    page.locator("#checkout").click()\n',
    )
    decision = RecordingDecision(confidence=0.65)
    async with test_db_session() as session:
        service = get_failure_service(session)

        async def diagnose(*_args, **_kwargs):
            return FailureAnalysisResponse(
                classification="LOCATOR_CHANGED",
                root_cause="The checkout locator changed.",
                provider="openai-compatible",
                fallback_used=False,
                confidence=0.92,
            )

        service.diagnose_failure_ai = diagnose
        workflow = FailureWorkflowService(
            service,
            LocatorDecisionService(decision_service=decision),
            auto_repair_mode="AUTO",
        )
        events = [event async for event in workflow.stream(failure_id)]

    result = next(event.metadata for event in events if event.type == "run.completed")
    assert len(decision.calls) == 1
    assert result["repair_state"] == "BLOCKED"
    assert result["selection"]["confidence"] == 0.65
    assert result["repair_proposal"] is None
    assert result["changes_applied"] is False
    assert not any(event.type == "patch.generated" for event in events)
    current = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"})
    assert current.json()["content"] == source


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["JEV_DISABLED", "JEV_TIMEOUT", "AI_BUDGET_EXHAUSTED"])
async def test_automatic_runtime_block_prevents_diagnosis_decision_and_patch(
    client, test_db_session, monkeypatch, reason
):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    decision = RecordingDecision()
    async with test_db_session() as session:
        service = get_failure_service(session)
        diagnosis_calls = []

        async def unexpected_diagnosis(*_args, **_kwargs):
            diagnosis_calls.append(True)
            raise AssertionError("Runtime readiness must block before diagnosis")

        async def blocked_readiness():
            return {"ready": False, "reason": reason}

        service.diagnose_failure_ai = unexpected_diagnosis
        workflow = FailureWorkflowService(
            service,
            LocatorDecisionService(decision_service=decision),
            auto_repair_mode="AUTO",
        )
        monkeypatch.setattr(workflow, "_runtime_readiness", blocked_readiness)
        events = [event async for event in workflow.stream(failure_id, auto_triggered=True)]

    completed = next(event for event in events if event.type == "run.completed")
    assert completed.metadata["block_reason"] == reason
    assert completed.metadata["repair_state"] == "BLOCKED"
    assert completed.metadata["automatic_triggered"] is True
    assert not diagnosis_calls
    assert not decision.calls
    assert not any(event.type in {"patch.generated", "patch.applied"} for event in events)


@pytest.mark.asyncio
async def test_jev_upstream_outage_blocks_auto_repair_before_diagnosis_or_write(client, test_db_session, monkeypatch):
    from app.services import failure_workflow_service as workflow_module
    from app.services.ai_settings_service import AISettingsService
    from app.services.decision_service import DecisionService
    from app.services.decision_settings_service import DecisionRuntimeConfig
    from app.settings import get_config

    source = 'def test_workflow(page):\n    page.locator("#old-submit").click()\n'
    project_id, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#old-submit")',
        kind="UI",
        source=source,
    )

    requests = []

    class UnavailableJevHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(self.path)
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), UnavailableJevHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LocalJevSettings:
        async def get_runtime_config(self):
            return DecisionRuntimeConfig(
                provider="jev",
                enabled=True,
                api_key="local-test-key",
                model="jev-test",
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                timeout=1,
                minimum_confidence=0.7,
                retries=0,
            )

    base = get_config()
    runtime_config = base.model_copy(
        update={
            "repair": base.repair.model_copy(update={"enabled": True, "require_jev": True}),
            "features": base.features.model_copy(update={"ai_repair": True, "jev_decision": True}),
        }
    )
    monkeypatch.setattr(workflow_module, "get_config", lambda: runtime_config)
    ai_policy = SimpleNamespace(
        enabled=True,
        provider="openai-compatible",
        api_key="local-test-ai-key",
        model="test-model",
        budget_enabled=False,
        max_request_tokens=10_000,
        max_daily_requests=100,
    )
    ai_status = SimpleNamespace(
        real_model_available=True,
        provider="openai-compatible",
        model="test-model",
        failure_reason=None,
    )

    async def ready_ai_policy(_self):
        return ai_policy

    async def ready_ai_status(_self, refresh=False):
        return ai_status

    monkeypatch.setattr(AISettingsService, "_effective_config", ready_ai_policy)
    monkeypatch.setattr(AISettingsService, "get_status", ready_ai_status)

    try:
        async with test_db_session() as session:
            service = get_failure_service(session)
            diagnoses = []

            async def unexpected_diagnosis(*_args, **_kwargs):
                diagnoses.append(True)
                raise AssertionError("Jev outage must block before AI diagnosis")

            service.diagnose_failure_ai = unexpected_diagnosis
            scope = TaskRepositoryScopeFactory()
            decision = DecisionService(settings_service=LocalJevSettings(), repository_scope=scope)
            workflow = FailureWorkflowService(
                service,
                LocatorDecisionService(decision_service=decision),
                auto_repair_mode="AUTO",
            )
            events = [event async for event in workflow.stream(failure_id, auto_triggered=True)]

        completed = next(event for event in events if event.type == "run.completed")
        assert completed.metadata["block_reason"] == "JEV_RUNTIME_NOT_READY"
        assert completed.metadata["jev_reasons"] == ["upstream_error"]
        assert completed.metadata["jev_provider"] == "jev"
        assert completed.metadata["automatic_triggered"] is True
        assert requests == ["/v1/systemone"]
        assert not diagnoses
        assert not any(event.type in {"patch.generated", "patch.applied"} for event in events)
        current = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"})
        assert current.json()["content"] == source
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_failed_model_is_redacted_and_persisted_without_success(client, test_db_session):
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")

    class BrokenProvider(FakeAIProvider):
        async def complete(self, request):
            raise RuntimeError("Authorization: Bearer private-workflow-token")

    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=BrokenProvider())
        workflow = FailureWorkflowService(service)
        events = [event async for event in workflow.stream(failure_id)]
        assert events[-1].type == "run.failed"
        records = await workflow.list_history(failure_id)
        assert records[0]["status"] == "FAILED"
        assert "private-workflow-token" not in json.dumps(records)
        assert records[0]["result"] == {
            "repair_state": "BLOCKED",
            "verified": False,
            "changes_applied": False,
        }


@pytest.mark.asyncio
async def test_analysis_outlives_its_connection_and_stops_only_on_request(client, test_db_session):
    """D1: reloading the page must not kill or lose an analysis, and CANCEL must really stop it."""
    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class WaitingProvider(FakeAIProvider):
        async def complete(self, request):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=WaitingProvider())
        workflow = FailureWorkflowService(service)
        stream = workflow.stream(failure_id)
        while (await asyncio.wait_for(anext(stream), timeout=3)).type != "model.started":
            pass
        await asyncio.wait_for(entered.wait(), timeout=3)
        analysis_id = (await workflow.list_history(failure_id))[0]["id"]

        # Leaving the page (or losing the SSE connection) must not cancel the work.
        await stream.aclose()
        await asyncio.sleep(0.2)
        assert not cancelled.is_set()
        assert (await workflow.list_history(failure_id))[0]["status"] == "RUNNING"

        # Re-attaching — what a reload does — replays what already happened instead of restarting.
        resumed = workflow.stream(failure_id)
        replayed: list[str] = []
        while "model.started" not in replayed:
            replayed.append((await asyncio.wait_for(anext(resumed), timeout=3)).type)
        await resumed.aclose()
        assert replayed
        assert not cancelled.is_set()

        # An explicit cancel is the only thing that stops it, and it must actually stop it.
        await workflow.cancel_analysis(failure_id, analysis_id)
        await asyncio.wait_for(cancelled.wait(), timeout=3)
        record = (await workflow.list_history(failure_id))[0]
        assert record["status"] == "CANCELLED"
        assert record["events"][-1]["type"] == "run.cancelled"
        assert record["result"]["block_reason"] == "ANALYSIS_CANCELLED"
        assert "START_ANALYSIS" in (await workflow.get_repair_workflow(failure_id)).allowed_actions

        # A process restart must never leave an analysis RUNNING forever.
        async with workflow.repository_scope() as repositories:
            unfinished = await repositories.failure_analyses.create(failure_id)
            await repositories.commit()
        assert unfinished in await workflow.recover_interrupted_analyses()
        records = await workflow.list_history(failure_id)
        assert next(record for record in records if record["id"] == unfinished)["status"] == "INTERRUPTED"


@pytest.mark.asyncio
async def test_analysis_timeout_ends_the_run_with_an_explicit_retryable_error(client, test_db_session, monkeypatch):
    """D2: a request that never reports back ends as TIMEOUT with a message, never as an open spinner."""
    from app.services import failure_workflow_service as workflow_module
    from app.settings import get_config

    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    cancelled = asyncio.Event()

    class HangingProvider(FakeAIProvider):
        async def complete(self, request):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    base = get_config()
    monkeypatch.setattr(
        workflow_module,
        "get_config",
        lambda: base.model_copy(update={"repair": base.repair.model_copy(update={"analysis_timeout_seconds": 0.5})}),
    )
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=HangingProvider())
        workflow = FailureWorkflowService(service)
        events = [event async for event in workflow.stream(failure_id)]
        assert events[-1].type == "run.timeout"
        assert "0.5" in events[-1].message
        await asyncio.wait_for(cancelled.wait(), timeout=3)
        record = (await workflow.list_history(failure_id))[0]
        assert record["status"] == "TIMEOUT"
        assert record["result"]["block_reason"] == "ANALYSIS_TIMEOUT"
        assert "START_ANALYSIS" in (await workflow.get_repair_workflow(failure_id)).allowed_actions


@pytest.mark.asyncio
async def test_reload_reclaims_an_orphaned_analysis_instead_of_hanging(client, test_db_session):
    """A worker that dies mid-analysis must not leave a RUNNING record behind for the next reload."""
    from datetime import timedelta

    from app.persistence.models import utc_now

    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        workflow = FailureWorkflowService(service)
        async with workflow.repository_scope() as repositories:
            orphan_id = await repositories.failure_analyses.create(failure_id)
            row = await repositories.failure_analyses.session.get(FailureAnalysisORM, orphan_id)
            row.created_at = utc_now() - timedelta(hours=1)
            await repositories.commit()

        # Re-attaching is what a reload does: it must converge to a terminal state, not to a spinner.
        events = [event async for event in workflow.stream(failure_id)]
        assert [event.type for event in events] == ["run.timeout"]
        record = next(row for row in await workflow.list_history(failure_id) if row["id"] == orphan_id)
        assert record["status"] == "TIMEOUT"
        assert "START_ANALYSIS" in (await workflow.get_repair_workflow(failure_id)).allowed_actions


@pytest.mark.asyncio
async def test_cancel_endpoint_stops_a_running_analysis(client, test_db_session):
    """The stop control is an API contract, not a front-end animation."""
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class WaitingProvider(FakeAIProvider):
        async def complete(self, request):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    _, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=WaitingProvider())
        workflow = FailureWorkflowService(service)
        stream = workflow.stream(failure_id)
        while (await asyncio.wait_for(anext(stream), timeout=3)).type != "model.started":
            pass
        await asyncio.wait_for(entered.wait(), timeout=3)
        analysis_id = (await workflow.list_history(failure_id))[0]["id"]
        running = (await client.get(f"/api/failures/{failure_id}/repair-workflow")).json()
        assert "CANCEL" in running["allowed_actions"]
        app.dependency_overrides[get_failure_service] = lambda: service
        try:
            response = await client.post(f"/api/failures/{failure_id}/analyses/{analysis_id}/cancel")
        finally:
            app.dependency_overrides.pop(get_failure_service, None)
        assert response.status_code == 200, response.text
        assert response.json()["allowed_actions"] == ["START_ANALYSIS"]
        await asyncio.wait_for(cancelled.wait(), timeout=3)
        await stream.aclose()
        assert (await workflow.list_history(failure_id))[0]["status"] == "CANCELLED"
        missing = await client.post(f"/api/failures/{failure_id}/analyses/unknown/cancel")
        assert missing.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [RunStatus.PASSED, RunStatus.FAILED])
async def test_only_an_actual_matching_rerun_updates_verification(client, test_db_session, status):
    from app.persistence.models import FailureRecordORM

    project_id, failure_id, _ = await seed(client, test_db_session, error="AssertionError: assert 1 == 2")
    async with test_db_session() as session:
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        workflow = FailureWorkflowService(service)
        events = [event async for event in workflow.stream(failure_id)]
        analysis_id = events[-1].metadata["analysis_id"]
        repo = service.run_repo
        original = await repo.get_failure_by_id(failure_id)
        with pytest.raises(ValueError, match="new run"):
            await workflow.attach_verification(failure_id, analysis_id, original.run_id)
        nodeid = "tests/test_workflow.py::test_workflow"
        pre_apply_run = await repo.create_run(
            TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=[nodeid])
        )
        await session.commit()
        applied_at = datetime.now(timezone.utc).isoformat()
        failure_record = await session.get(FailureRecordORM, failure_id)
        analysis_record = await session.get(FailureAnalysisORM, analysis_id)
        applied_proposal = {
            "applied": True,
            "applied_at": applied_at,
            "candidate_id": "candidate-verification",
            "file_path": "tests/test_workflow.py",
            "proposed_locator": 'get_by_test_id("checkout")',
        }
        failure_record.repair_proposal = applied_proposal
        analysis_record.result = {
            **(analysis_record.result or {}),
            "repair_state": "PATCH_APPLIED",
            "repair_proposal": applied_proposal,
        }
        await session.commit()
        with pytest.raises(ValueError, match="start after the repair was applied"):
            await workflow.attach_verification(failure_id, analysis_id, pre_apply_run.id)
        valid_analysis_result = dict(analysis_record.result)
        for mismatched_proposal in (
            {**applied_proposal, "candidate_id": "different-candidate"},
            {key: value for key, value in applied_proposal.items() if key != "candidate_id"},
        ):
            analysis_record.result = {**valid_analysis_result, "repair_proposal": mismatched_proposal}
            await session.commit()
            mismatched_run = await repo.create_run(
                TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=[nodeid])
            )
            await session.commit()
            with pytest.raises(ValueError, match="proposal selected"):
                await workflow.attach_verification(failure_id, analysis_id, mismatched_run.id)
        analysis_record.result = valid_analysis_result
        await session.commit()
        wrong = await repo.create_run(
            TestRunCreate(
                project_id=project_id, workspace_id=project_id, nodeids=["tests/test_workflow.py::other_case"]
            )
        )
        await session.commit()
        with pytest.raises(ValueError, match="exactly"):
            await workflow.attach_verification(failure_id, analysis_id, wrong.id)
        rerun = await repo.create_run(TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=[nodeid]))
        await session.commit()
        await workflow.attach_verification(failure_id, analysis_id, rerun.id)
        rows = await workflow.list_history(failure_id)
        assert rows[0]["result"]["verified"] is False
        assert rows[0]["events"][-1]["status"] == "RUNNING"
        await repo.add_execution(rerun.id, nodeid, status=status)
        await repo.update_run_status(rerun.id, status)
        await session.commit()
        rows = await workflow.list_history(failure_id)
        assert rows[0]["result"]["verified"] is (status == RunStatus.PASSED)
        assert rows[0]["events"][-1]["status"] == ("COMPLETED" if status == RunStatus.PASSED else "FAILED")
        assert rows[0]["events"][-1]["metadata"]["evidence_source"] == "pytest_execution"
        replayed = await workflow.list_history(failure_id)
        assert len(rows[0]["events"]) == len(replayed[0]["events"])
        second_rerun = await repo.create_run(
            TestRunCreate(project_id=project_id, workspace_id=project_id, nodeids=[nodeid])
        )
        await repo.add_execution(second_rerun.id, nodeid, status=status)
        await repo.update_run_status(second_rerun.id, status)
        await session.commit()
        await workflow.attach_verification(failure_id, analysis_id, second_rerun.id)
        repeated = await workflow.list_history(failure_id)
        assert repeated[0]["result"]["verified"] is (status == RunStatus.PASSED)
        assert repeated[0]["events"][-1]["metadata"]["verification_run_id"] == second_rerun.id


@pytest.mark.asyncio
async def test_rejected_locator_proposal_persists_and_cannot_be_applied(client, test_db_session):
    from app.persistence.models import FailureRecordORM, LocatorRepairORM
    from project_model.models import FailureRepairState

    project_id, failure_id, source = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        source='def test_workflow(page):\n    page.locator("#checkout").click()\n',
    )
    analysis_id = "analysis-human-rejected"
    proposal = {
        "old_locator": "#checkout",
        "proposed_locator": 'get_by_test_id("checkout-new")',
        "file_path": "tests/test_workflow.py",
        "applied": False,
        "verified": True,
        "provider": "jev",
        "decision_summary": {
            "fallback_used": False,
            "verification_source": "playwright",
            "confidence": 0.92,
        },
        "ai_provider": "openai-compatible",
        "ai_fallback_used": False,
        "candidate_id": "candidate_1",
        "code_diff": '- page.locator("#checkout")\n+ page.get_by_test_id("checkout-new")',
        "source_sha256": "source-hash",
    }
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = proposal
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": proposal,
                    "changes_applied": False,
                    "verified": False,
                },
            )
        )
        session.add(
            LocatorRepairORM(
                id="repair-human-rejected",
                failure_id=failure_id,
                analysis_id=analysis_id,
                state=FailureRepairState.PATCH_READY,
                candidate_id="candidate_1",
            )
        )
        await session.commit()

    rejected = await client.post(f"/api/failures/{failure_id}/analyses/{analysis_id}/reject")
    assert rejected.status_code == 200, rejected.text
    workflow = rejected.json()
    assert workflow["state"] == "BLOCKED"
    assert workflow["block_reason"] == "HUMAN_REJECTED"
    assert workflow["allowed_actions"] == ["START_ANALYSIS"]
    assert workflow["repair_proposal"]["proposed_locator"] == proposal["proposed_locator"]
    assert workflow["repair_proposal"]["applied"] is False

    persisted = await client.get(f"/api/failures/{failure_id}/repair-workflow", params={"analysis_id": analysis_id})
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["block_reason"] == "HUMAN_REJECTED"
    history = await client.get(f"/api/failures/{failure_id}/analyses")
    assert history.status_code == 200, history.text
    rejected_analysis = next(row for row in history.json() if row["id"] == analysis_id)
    assert rejected_analysis["result"]["block_reason"] == "HUMAN_REJECTED"
    assert any(event["type"] == "repair.rejected" for event in rejected_analysis["events"])

    apply = await client.post(
        f"/api/failures/{failure_id}/analyses/{analysis_id}/apply",
        json={
            "file_path": proposal["file_path"],
            "old_code": proposal["old_locator"],
            "new_code": proposal["proposed_locator"],
        },
    )
    assert apply.status_code == 422
    current_source = await client.get(f"/api/workspaces/{project_id}/file", params={"path": "tests/test_workflow.py"})
    assert current_source.status_code == 200, current_source.text
    assert current_source.json()["content"] == source
