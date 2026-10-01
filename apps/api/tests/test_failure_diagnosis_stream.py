from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from app.api.failures import get_failure_service
from app.main import app
from app.persistence.models import FailureRecordORM
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.test_run_service import TestRunService
from app.services.workspace_service import WorkspaceService
from project_model.models import TestRunCreate
from qa_core.ai.provider import FakeAIProvider
from qa_core.execution.models import SingleTestResult, SuiteExecutionResult, TestExecutionStatus
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator
from sqlalchemy import select


@pytest_asyncio.fixture
async def failure_service(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Diagnosis Progress"})).json()
    async with test_db_session() as session:
        repository = TestRunRepository(session)
        run = await repository.create_run(TestRunCreate(project_id=project["id"], workspace_id=project["id"]))
        await session.commit()
        await TestRunService(repository, WorkspaceRepository(session), WorkspaceService()).persist_suite_result(
            run.id,
            SuiteExecutionResult(
                exit_code=1,
                total=1,
                failed=1,
                results=[
                    SingleTestResult(
                        nodeid="tests/test_login.py::test_login_failed",
                        status=TestExecutionStatus.FAILED,
                        error_message="AssertionError: assert 1 == 2",
                        stack_trace="tests/test_login.py:20: AssertionError",
                    )
                ],
            ),
        )
        failure = (
            await session.execute(select(FailureRecordORM).where(FailureRecordORM.run_id == run.id))
        ).scalar_one()
        service = get_failure_service(session)
        service.orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())
        yield service, failure.id


class WaitingProvider(FakeAIProvider):
    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def complete(self, request):
        self.entered.set()
        try:
            await self.release.wait()
            return await super().complete(request)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.asyncio
async def test_progress_reaches_client_before_model_finishes(failure_service):
    service, failure_id = failure_service
    provider = WaitingProvider()
    service.orchestrator = ProductionQAOrchestrator(ai_provider=provider)
    stream = service.stream_diagnosis(failure_id)
    try:
        first = await asyncio.wait_for(anext(stream), timeout=2)
        evidence = await asyncio.wait_for(anext(stream), timeout=2)
        model = await asyncio.wait_for(anext(stream), timeout=2)
        assert [first.type, evidence.type, model.type] == ["analysis_started", "evidence_collected", "model.started"]
        assert "assert 1 == 2" in evidence.message
        await asyncio.wait_for(provider.entered.wait(), timeout=2)
        assert not provider.release.is_set()
        provider.release.set()
        remaining = [event async for event in stream]
        assert [event.type for event in remaining] == ["model.completed", "diagnosis_completed", "run.completed"], [
            event.message for event in remaining
        ]
        result = remaining[-1].metadata["diagnosis"]
        assert result["classification"] == "ASSERTION_FAILURE"
        assert result["provider"] == "fake"
        assert result["execution_trace"][0]["event_id"] == first.event_id
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_cancelling_stream_stops_model_request(failure_service):
    service, failure_id = failure_service
    provider = WaitingProvider()
    service.orchestrator = ProductionQAOrchestrator(ai_provider=provider)
    stream = service.stream_diagnosis(failure_id)
    for _ in range(3):
        await asyncio.wait_for(anext(stream), timeout=2)
    await asyncio.wait_for(provider.entered.wait(), timeout=2)
    await stream.aclose()
    assert provider.cancelled.is_set()


@pytest.mark.asyncio
async def test_stream_reports_redacted_provider_error_without_a_result(failure_service):
    service, failure_id = failure_service

    class BrokenProvider(FakeAIProvider):
        async def complete(self, _):
            raise RuntimeError("connection_error Authorization: Bearer secret-stream-token")

    service.orchestrator = ProductionQAOrchestrator(ai_provider=BrokenProvider())
    events = [event async for event in service.stream_diagnosis(failure_id)]
    assert events[-1].type == "run.failed"
    assert "connection_error" in events[-1].message
    assert "secret-stream-token" not in json.dumps([event.model_dump(mode="json") for event in events])
    assert not any(event.type == "run.completed" for event in events)


@pytest.mark.asyncio
async def test_stream_route_and_legacy_diagnosis_remain_compatible(client, anonymous_client, failure_service):
    service, failure_id = failure_service
    app.dependency_overrides[get_failure_service] = lambda: service
    try:
        path = f"/api/failures/{failure_id}/diagnose-ai"
        denied = await anonymous_client.post(path + "/stream")
        assert denied.status_code == 401
        missing = await client.post("/api/failures/missing/diagnose-ai/stream")
        assert missing.status_code == 404
        response = await client.post(path + "/stream")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[0]["type"] == "analysis_started"
        assert events[-1]["metadata"]["diagnosis"]["classification"] == "ASSERTION_FAILURE"
        legacy = await client.post(path)
        assert legacy.status_code == 200
        assert legacy.json()["classification"] == "ASSERTION_FAILURE"
    finally:
        app.dependency_overrides.pop(get_failure_service, None)
