from __future__ import annotations

import asyncio
import json

import pytest
from app.api.failures import get_failure_service
from app.main import app
from app.persistence.models import BrowserSessionORM
from app.repositories.test_run_repo import TestRunRepository
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.locator_decision_service import LocatorDecisionService
from project_model.models import DecisionResult, RunStatus, TestRunCreate
from qa_core.ai.provider import FakeAIProvider
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


async def seed(client, test_db_session, *, error, kind="PYTHON", candidates=None):
    project = (
        await client.post("/api/projects", json={"name": "Workflow evidence", "bootstrap_workspace": False})
    ).json()
    source = "def test_workflow():\n    actual = 1\n    assert actual == 2\n"
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
                    current_url="http://localhost/checkout",
                    page_evidence_json=json.dumps(
                        {
                            "controls": [
                                {
                                    "candidates": candidates
                                    or [
                                        {"kind": "test_id", "value": "checkout-submit"},
                                        {"kind": "role", "value": "button", "name": "Checkout"},
                                        {"kind": "text", "value": "Checkout"},
                                        {"kind": "id", "value": "checkout-new"},
                                    ]
                                }
                            ]
                        }
                    ),
                )
            )
        await session.commit()
        return project["id"], failure.id, source


class RecordingDecision:
    def __init__(self, *, fallback=False):
        self.calls = []
        self.fallback = fallback

    async def choose(self, request, **kwargs):
        self.calls.append(request)
        return DecisionResult(
            choice=request.options[0].key,
            provider="jev",
            model="unit-test-jev",
            fallback_used=self.fallback,
            reason="unit-test-fallback" if self.fallback else None,
        )


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
        persisted = await workflow.history.list(failure_id)
        assert persisted[0]["status"] == "COMPLETED"
        assert persisted[0]["events"][-1]["event_id"] == events[-1].event_id
        assert persisted[0]["result"]["verified"] is False
        await asyncio.sleep(0.01)
        await anext_second_run(workflow, failure_id)
        assert len(await workflow.history.list(failure_id)) == 2
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
    client, test_db_session, fallback
):
    _, failure_id, _ = await seed(client, test_db_session, error='Timeout waiting for locator("#checkout")', kind="UI")
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
        engine = "Local Strategy" if fallback else "Jev"
        actual = next(event for event in events if event.type == "decision_completed")
        assert actual.metadata["provider"] == ("local-strategy" if fallback else "jev")
        assert events[-1].metadata["selection"]["engine"] == engine
        assert events[-1].metadata["verified"] is False
        assert not any(event.type == "verification_completed" for event in events)


@pytest.mark.asyncio
async def test_unrelated_page_elements_do_not_become_a_locator_repair(client, test_db_session):
    _, failure_id, _ = await seed(
        client,
        test_db_session,
        error='Timeout waiting for locator("#checkout")',
        kind="UI",
        candidates=[{"kind": "test_id", "value": "logout"}],
    )
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
        assert not decision.calls
        assert next(event for event in events if event.stage == "decision").status == "BLOCKED"
        assert events[-1].metadata["selection"] is None


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
        records = await workflow.history.list(failure_id)
        assert records[0]["status"] == "FAILED"
        assert "private-workflow-token" not in json.dumps(records)
        assert not records[0]["result"]


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
        records = await workflow.history.list(failure_id)
        assert records[0]["status"] == "CANCELLED"
        assert records[0]["events"][-1]["type"] == "run.cancelled"
        unfinished = await workflow.history.create(failure_id)
        await workflow.history.recover_interrupted()
        records = await workflow.history.list(failure_id)
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
