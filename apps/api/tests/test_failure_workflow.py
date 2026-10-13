from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

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
from project_model.models import ApplyRepairRequest, DecisionResult, RunStatus, TestRunCreate
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


@pytest.fixture
def local_html_url():
    servers = []

    def serve(html: str) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/"

    yield serve
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
async def test_repair_verification_command_creates_and_links_exact_idempotent_run(client, test_db_session):
    from app.persistence.models import FailureRecordORM, TestRunORM
    from sqlalchemy import select

    project_id, failure_id, _ = await seed(
        client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI"
    )
    analysis_id = "repair-analysis-command"
    async with test_db_session() as session:
        failure = await session.get(FailureRecordORM, failure_id)
        failure.repair_proposal = {"applied": True, "proposed_locator": "#checkout-new"}
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": {"proposed_locator": "#checkout-new"},
                },
            )
        )
        await session.commit()

    async with test_db_session() as session:
        failure_service = get_failure_service(session)
        runs = make_run_service(failure_service, session)
        runs._schedule_local_run = lambda *_args, **_kwargs: None
        workflow = FailureWorkflowService(failure_service, run_service=runs)
        run = await workflow.start_verification(failure_id, analysis_id)
        repeated = await workflow.start_verification(failure_id, analysis_id)
        assert run.id == repeated.id
        assert run.project_id == project_id
        assert run.workspace_id == project_id
        assert run.nodeids == ["tests/test_workflow.py::test_workflow"]
        assert run.origin_failure_id == failure_id

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
        failure.repair_proposal = {"applied": True, "proposed_locator": "#checkout-new"}
        session.add(
            FailureAnalysisORM(
                id=analysis_id,
                failure_id=failure_id,
                status="COMPLETED",
                result={
                    "repair_state": "PATCH_READY",
                    "repair_proposal": {"proposed_locator": "#checkout-new"},
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
async def test_patch_ready_workflow_keeps_apply_and_allows_fresh_analysis(
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
    assert state.allowed_actions == ["APPLY", "START_ANALYSIS"]


@pytest.mark.asyncio
async def test_terminal_manual_verification_records_completion_even_if_state_was_not_reconciled(
    client, test_db_session
):
    from app.persistence.models import FailureRecordORM
    from qa_core.ai.trace import make_trace_event

    project_id, failure_id, _ = await seed(
        client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI"
    )
    analysis_id = "analysis-manual-verification-reconcile"
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
async def test_workflow_authorizes_retry_from_real_diagnosis_and_starts_one_server_run(client, test_db_session):
    project_id, failure_id, _ = await seed(client, test_db_session, error="Connection timed out")
    analysis_id = "failure-retry-command"
    async with test_db_session() as session:
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
        runs._schedule_local_run = lambda *_args, **_kwargs: None
        workflow = FailureWorkflowService(service, run_service=runs)
        state = await workflow.get_repair_workflow(failure_id, analysis_id)
        assert "RETRY" in state.allowed_actions
        retry = await workflow.start_retry(failure_id, analysis_id)
        repeated = await workflow.start_retry(failure_id, analysis_id)
        assert retry.id == repeated.id
        assert retry.project_id == project_id
        assert retry.nodeids == ["tests/test_workflow.py::test_workflow"]
        assert retry.origin_failure_id == failure_id
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
async def test_manual_repair_persists_applied_and_rolled_back_state(client, test_db_session, local_html_url):
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
        applied = await workflow.apply_repair(
            failure_id,
            analysis_id,
            ApplyRepairRequest(
                file_path=proposal.file_path,
                old_code=proposal.source_locator,
                new_code=proposal.proposed_locator,
            ),
        )
        assert applied["repair"]["state"] == "PATCH_APPLIED"
        applied_analysis = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert applied_analysis["result"]["changes_applied"] is True
        assert applied_analysis["result"]["repair_proposal"]["applied"] is True
        patched = await service.workspace_service.read_file(project_id, "tests/test_workflow.py")
        assert proposal.proposed_locator in patched

        rolled_back = await workflow.rollback_repair(failure_id, analysis_id)
        assert rolled_back["repair"]["state"] == "ROLLED_BACK"
        rolled_back_analysis = next(row for row in await workflow._history_list(failure_id) if row["id"] == analysis_id)
        assert rolled_back_analysis["result"]["changes_applied"] is False
        assert rolled_back_analysis["result"]["repair_proposal"]["applied"] is False
        assert await service.workspace_service.read_file(project_id, "tests/test_workflow.py") == source


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
async def test_cancel_and_restart_preserve_incomplete_analysis(client, test_db_session):
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
        await stream.aclose()
        assert cancelled.is_set()
        records = await workflow.list_history(failure_id)
        assert records[0]["status"] == "CANCELLED"
        assert records[0]["events"][-1]["type"] == "run.cancelled"
        async with workflow.repository_scope() as repositories:
            unfinished = await repositories.failure_analyses.create(failure_id)
            await repositories.commit()
            await repositories.failure_analyses.recover_interrupted()
            await repositories.commit()
        records = await workflow.list_history(failure_id)
        assert next(record for record in records if record["id"] == unfinished)["status"] == "INTERRUPTED"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [RunStatus.PASSED, RunStatus.FAILED])
async def test_only_an_actual_matching_rerun_updates_verification(client, test_db_session, status):
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
