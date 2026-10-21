"""Workflow tests use explicit fixtures; these are not Golden Demo invocation evidence."""

import json
import time
from types import SimpleNamespace

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import RequirementORM, TaskORM, utc_now
from app.repositories.ai_repo import AIRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.repositories.test_case_repo import TestCaseRepository as CaseRepo
from app.repositories.test_design_repo import TestDesignRepository as DesignRepo
from app.services import requirement_lifecycle_service
from app.services.golden_demo_service import DEMO_REQUIREMENT, demo_document
from app.services.requirement_lifecycle_service import RequirementAnalysisBusy, RequirementLifecycleService
from app.services.requirement_service import RequirementService
from project_model.lifecycle import RequirementDocument
from project_model.models import DecisionResult, RequirementUpdate
from qa_core.ai.models import AICompletionResponse
from qa_core.ai.provider import AIProviderError, FakeAIProvider
from sqlalchemy import select

task_runtime_service = get_task_runtime_service()


class TestOrchestrator:
    __test__ = False
    ai_provider = SimpleNamespace(provider_name="unit_fixture", model="schema_fixture", timeout=30)

    async def complete_streaming(self, request, *, timeout_seconds):
        assert timeout_seconds == requirement_lifecycle_service.MIN_REQUIREMENT_ANALYSIS_TIMEOUT_SECONDS
        self.streaming_calls = getattr(self, "streaming_calls", 0) + 1
        return await self.complete(request)

    async def complete(self, request):
        assert request.max_tokens == 10000
        analysis = demo_document().analysis
        analysis.summary = "A structured fixture response, not a production model invocation"
        return AICompletionResponse(
            content="{}",
            structured_data=analysis.model_dump(mode="json"),
            provider="unit_fixture",
            model="schema_fixture",
        )


class RuntimeTestOrchestrator(TestOrchestrator):
    async def complete(self, request):
        await AIRepository().record_invocation(
            task="requirement_lifecycle",
            provider="unit_fixture",
            model="schema_fixture",
            task_id=request.task_id,
            run_id=request.run_id,
            status="SUCCESS",
        )
        return await super().complete(request)


class TestDecisions:
    __test__ = False

    async def choose(self, request, **kwargs):
        choice = "SCN-004" if request.name.endswith("scenario_priority") else "RISK-002"
        return DecisionResult(
            choice=choice,
            provider="jev",
            model="unit_fixture",
            confidence=0.9,
            reason="Fixture decision with explicit references",
        )


class RuntimeTestDecisions(TestDecisions):
    async def choose(self, request, **kwargs):
        task_id = kwargs.get("task_id")
        reserve_task_call = kwargs.get("reserve_task_call")
        if task_id and reserve_task_call and not await reserve_task_call():
            return DecisionResult(provider="fallback", fallback_used=True, reason="task_ai_budget_exhausted")
        if task_id:
            await AIRepository().record_invocation(
                task=request.name,
                provider="jev",
                model="unit_fixture",
                task_id=task_id,
                run_id=kwargs.get("run_id"),
                status="SUCCESS",
            )
        return await super().choose(request, **kwargs)


@pytest.mark.asyncio
async def test_structured_analysis_preserves_history_and_detects_changed_inputs(client):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), TestOrchestrator(), TestDecisions())
    events = [event async for event in workflow.stream(DEMO_REQUIREMENT)]
    assert events[-1].type == "run.completed"
    assert workflow.orchestrator.streaming_calls == 1
    requirement = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()
    document = RequirementDocument.model_validate(requirement["qa_model"])
    assert document.analysis.scenarios[0].id == "SCN-004"
    assert document.analysis.risks[0].id == "RISK-002"
    record = document.history[-1]
    assert record.status == "SUCCESS" and record.analysis_snapshot.summary == document.analysis.summary
    stage_ids = {stage.id for stage in record.stages}
    assert (
        record.input_hash
        and {"project_context", "existing_cases", "business_rules", "coverage_gaps", "test_design"} <= stage_ids
    )
    assert len(record.decisions) == 2
    assert not requirement["analysis_stale"]
    changed = await client.patch(
        f"/api/requirements/{DEMO_REQUIREMENT}", json={"description": "Changed requirement intent"}
    )
    assert changed.status_code == 200 and changed.json()["analysis_stale"]
    document.analysis.summary = "Forged edited analysis"
    rejected = await client.patch(
        f"/api/requirements/{DEMO_REQUIREMENT}", json={"qa_model": document.model_dump(mode="json")}
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_runtime_requirement_analysis_projects_events_ai_decisions_and_evidence(
    client, test_db_session, monkeypatch
):
    await client.post("/api/projects/golden-demo/seed")
    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_REQUIREMENT",
            "goal": "Analyze the Golden Demo requirement",
            "project_id": "proj_golden_shop_v1",
            "inputs": {"requirement_id": DEMO_REQUIREMENT},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    monkeypatch.setattr(
        requirement_lifecycle_service,
        "RequirementLifecycleService",
        lambda **kwargs: RequirementLifecycleService(
            kwargs["repository_scope"], RuntimeTestOrchestrator(), RuntimeTestDecisions()
        ),
    )

    await task_runtime_service.scheduler._execute_dag(task_id, time.monotonic())
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None and task.status == "COMPLETED"
        step = (await TaskRepository(session).steps_for_task(task_id))[0]
        result = step.outputs
        assert result["requirement_id"] == DEMO_REQUIREMENT
        assert result["risk_count"] > 0 and result["scenario_count"] > 0

    runtime = await client.get(f"/api/tasks/{task_id}/runtime")
    assert runtime.status_code == 200, runtime.text
    snapshot = runtime.json()
    assert snapshot["task"]["type"] == "ANALYZE_REQUIREMENT"
    assert snapshot["steps"][0]["status"] == "COMPLETED"
    assert len(snapshot["ai_invocations"]) == 3
    assert all(invocation["task_id"] == task_id for invocation in snapshot["ai_invocations"])
    assert all(invocation["step_id"] == snapshot["steps"][0]["id"] for invocation in snapshot["ai_invocations"])
    assert {invocation["provider"] for invocation in snapshot["ai_invocations"]} == {"unit_fixture", "jev"}
    assert {event["type"] for event in snapshot["events"]} >= {"workflow.step", "run.completed"}
    assert all(
        event["step_id"] == snapshot["steps"][0]["id"]
        for event in snapshot["events"]
        if event["type"] == "workflow.step"
    )
    assert len(snapshot["decisions"]) == 2
    assert any(item["type"] == "Analysis" for item in snapshot["evidence"])

    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    assert saved["history"][-1]["status"] == "SUCCESS"
    assert saved["history"][-1]["id"] == result["analysis_record_id"]


@pytest.mark.asyncio
async def test_runtime_requirement_analysis_can_run_without_explicit_criteria(client, test_db_session, monkeypatch):
    project = (
        await client.post("/api/projects", json={"name": "No criteria project", "bootstrap_workspace": False})
    ).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Empty cart state",
                "description": "When the cart has no items, show an empty-state message and a zero total.",
            },
        )
    ).json()
    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_REQUIREMENT",
            "goal": "Analyze an empty-cart requirement without supplied criteria",
            "project_id": project["id"],
            "inputs": {"requirement_id": requirement["id"]},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    class NoCriteriaRuntimeTestOrchestrator(RuntimeTestOrchestrator):
        async def complete(self, request):
            assert '"criteria": []' in request.prompt
            assert "do not invent user-confirmed criteria" in request.system_instruction
            await AIRepository().record_invocation(
                task="requirement_lifecycle",
                provider="unit_fixture",
                model="schema_fixture",
                task_id=request.task_id,
                run_id=request.run_id,
                status="SUCCESS",
            )
            analysis = demo_document().analysis.model_copy(deep=True)
            for flow_step in analysis.business_flow:
                flow_step.criterion_ids = []
            for risk in analysis.risks:
                risk.criterion_ids = []
            for scenario in analysis.scenarios:
                scenario.coverage.criterion_ids = []
                scenario.coverage.rule_ids = []
                scenario.coverage.risk_ids = ["RISK-UNKNOWN"]
            payload = analysis.model_dump(mode="json")
            payload["scenarios_note"] = "Scenarios are provisional."
            return AICompletionResponse(
                content="{}",
                structured_data=payload,
                provider="unit_fixture",
                model="schema_fixture",
            )

    monkeypatch.setattr(
        requirement_lifecycle_service,
        "RequirementLifecycleService",
        lambda **kwargs: RequirementLifecycleService(
            kwargs["repository_scope"], NoCriteriaRuntimeTestOrchestrator(), RuntimeTestDecisions()
        ),
    )
    await task_runtime_service.scheduler._execute_dag(task_id, time.monotonic())

    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None and task.status == "COMPLETED"
        step = (await TaskRepository(session).steps_for_task(task_id))[0]
        assert step.status == "COMPLETED"
        assert step.outputs["scenario_count"] > 0

    runtime = await client.get(f"/api/tasks/{task_id}/runtime")
    assert runtime.status_code == 200, runtime.text
    snapshot = runtime.json()
    assert snapshot["blocking"] is None
    assert len(snapshot["ai_invocations"]) == 3
    criteria_event = next(
        event
        for event in snapshot["events"]
        if event["type"] == "workflow.step" and event["title"] == "提取验收标准与业务规则"
    )
    assert "没有预填验收标准" in criteria_event["summary"]

    saved = (await client.get(f"/api/requirements/{requirement['id']}")).json()["qa_model"]
    assert saved["criteria"] == []
    assert saved["history"][-1]["status"] == "SUCCESS"
    assert all(not item["coverage"]["criterion_ids"] for item in saved["analysis"]["scenarios"])
    assert all(
        set(item["coverage"]["risk_ids"]) <= {risk["id"] for risk in saved["analysis"]["risks"]}
        for item in saved["analysis"]["scenarios"]
    )
    assert any("忽略" in item for item in saved["analysis"]["coverage_gaps"])
    assert any("非标准字段" in item for item in saved["analysis"]["coverage_gaps"])


@pytest.mark.asyncio
async def test_runtime_requirement_analysis_rejects_unstructured_output_as_recoverable_block(
    client, test_db_session, monkeypatch
):
    await client.post("/api/projects/golden-demo/seed")

    class InvalidOrchestrator:
        ai_provider = type("Provider", (), {"provider_name": "unit_fixture", "model": "invalid_fixture"})()

        async def complete(self, request):
            from project_model.lifecycle import RequirementAnalysis

            return RequirementAnalysis.model_validate({})

    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_REQUIREMENT",
            "goal": "Verify invalid analysis recovery",
            "project_id": "proj_golden_shop_v1",
            "inputs": {"requirement_id": DEMO_REQUIREMENT},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    monkeypatch.setattr(
        requirement_lifecycle_service,
        "RequirementLifecycleService",
        lambda **kwargs: RequirementLifecycleService(
            kwargs["repository_scope"], InvalidOrchestrator(), TestDecisions()
        ),
    )

    await task_runtime_service.scheduler._execute_dag(task_id, time.monotonic())
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None and task.status == "BLOCKED"
        step = (await TaskRepository(session).steps_for_task(task_id))[0]
        assert step.status == "FAILED"
        assert step.outputs["failure_type"] == "AI_OUTPUT_INVALID"

    runtime = await client.get(f"/api/tasks/{task_id}/runtime")
    assert runtime.status_code == 200, runtime.text
    assert runtime.json()["blocking"]["failure_type"] == "AI_OUTPUT_INVALID"
    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    assert saved["history"][-1]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_fake_provider_is_explicit_and_reference_analysis_is_preserved(client):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(
        TaskRepositoryScopeFactory(), SimpleNamespace(ai_provider=FakeAIProvider()), TestDecisions()
    )
    events = [event async for event in workflow.stream(DEMO_REQUIREMENT)]
    assert events[-1].type == "run.failed"
    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    assert saved["history"][-1]["status"] == "FALLBACK"
    assert "Fake AI" in saved["history"][-1]["error"]
    assert saved["analysis"]["summary"] == demo_document().analysis.summary


@pytest.mark.asyncio
async def test_invalid_provider_output_is_explicitly_failed_before_jev(client):
    await client.post("/api/projects/golden-demo/seed")

    class InvalidOrchestrator:
        ai_provider = SimpleNamespace(provider_name="fixture_gateway", model="plain-text-only")

        async def complete(self, request):
            return AICompletionResponse(
                content="generic text", structured_data=None, provider="fixture_gateway", model="plain-text-only"
            )

    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), InvalidOrchestrator(), TestDecisions())
    events = [event async for event in workflow.stream(DEMO_REQUIREMENT)]
    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    latest = saved["history"][-1]

    assert events[-1].type == "run.failed"
    assert latest["status"] == "FAILED"
    assert latest["error_code"] == "INVALID_STRUCTURED_OUTPUT"
    assert latest["decisions"] == []
    assert latest["stages"][-1]["status"] == "failed"
    assert latest["stages"][-1]["source"] == "fixture_gateway"
    assert "Jev 尚未运行" in latest["stages"][-1]["summary"]
    assert saved["analysis"]["summary"] == demo_document().analysis.summary


@pytest.mark.asyncio
async def test_provider_output_limit_code_is_preserved_in_requirement_history(client):
    await client.post("/api/projects/golden-demo/seed")

    class OutputLimitedOrchestrator(TestOrchestrator):
        async def complete_streaming(self, _request, *, timeout_seconds):
            raise AIProviderError(
                "output_limit",
                "AI Provider 因输出长度上限提前终止；结果不完整，未作为有效分析返回。",
            )

    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), OutputLimitedOrchestrator(), TestDecisions())
    events = [event async for event in workflow.stream(DEMO_REQUIREMENT)]
    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    latest = saved["history"][-1]

    assert events[-1].type == "run.failed"
    assert latest["status"] == "FAILED"
    assert latest["error_code"] == "output_limit"
    assert latest["decisions"] == []
    assert latest["stages"][-1]["status"] == "failed"
    assert "输出长度上限" in latest["stages"][-1]["summary"]


@pytest.mark.asyncio
async def test_concurrent_analysis_and_edits_are_rejected_and_close_is_recorded(client, test_db_session):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), TestOrchestrator(), TestDecisions())
    stream = workflow.stream(DEMO_REQUIREMENT)
    await anext(stream)
    competing = workflow.stream(DEMO_REQUIREMENT)
    with pytest.raises(RequirementAnalysisBusy):
        await anext(competing)
    async with test_db_session() as session:
        with pytest.raises(ValueError, match="running"):
            await RequirementService(
                RequirementRepository(session), CaseRepo(session), DesignRepo(session)
            ).update_requirement(DEMO_REQUIREMENT, RequirementUpdate(title="New title"))
    await stream.aclose()
    saved = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()["qa_model"]
    assert saved["history"][-1]["status"] == "FAILED"
    assert "cancelled" in saved["history"][-1]["error"]


@pytest.mark.asyncio
async def test_analysis_handles_nullable_legacy_models_and_restart_recovery(client, test_db_session):
    project = (await client.post("/api/projects", json={"name": "Legacy", "bootstrap_workspace": False})).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Legacy requirement",
                "acceptance_criteria": "Search shows correct product",
            },
        )
    ).json()
    async with test_db_session() as session:
        from sqlalchemy import text

        await session.execute(text("UPDATE requirements SET qa_model = NULL WHERE id = :id"), {"id": requirement["id"]})
        await session.commit()
    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), TestOrchestrator(), TestDecisions())
    stream = workflow.stream(requirement["id"])
    await anext(stream)
    # A second replica may be waiting on the model right now: recovery only abandons an entry whose
    # own start is older than the window, so backdate this one before asserting recovery.
    from datetime import timedelta

    async with test_db_session() as session:
        row = await session.scalar(select(RequirementORM).where(RequirementORM.id == requirement["id"]))
        history = list(row.qa_model["history"])
        history[-1] = {**history[-1], "started_at": (utc_now() - timedelta(seconds=3600)).isoformat()}
        await session.execute(
            text("UPDATE requirements SET qa_model = :model WHERE id = :id"),
            {"model": json.dumps({**row.qa_model, "history": history}), "id": requirement["id"]},
        )
        await session.commit()
    await RequirementLifecycleService(TaskRepositoryScopeFactory()).recover_interrupted()
    async with test_db_session() as session:
        row = await session.scalar(select(RequirementORM).where(RequirementORM.id == requirement["id"]))
        assert row.qa_model["history"][-1]["status"] == "FAILED"
        assert row.qa_model["criteria"][0]["id"] == "AC-001"
    await stream.aclose()


@pytest.mark.asyncio
async def test_a_fresh_running_analysis_survives_recovery(client, test_db_session):
    """The mirror image: recovery must not mark a live replica's analysis failed."""
    project = (await client.post("/api/projects", json={"name": "Recovery guard", "description": ""})).json()
    requirement = (
        await client.post(
            "/api/requirements",
            json={
                "project_id": project["id"],
                "title": "Fresh analysis",
                "acceptance_criteria": "Search shows correct product",
            },
        )
    ).json()
    workflow = RequirementLifecycleService(TaskRepositoryScopeFactory(), TestOrchestrator(), TestDecisions())
    stream = workflow.stream(requirement["id"])
    await anext(stream)
    await RequirementLifecycleService(TaskRepositoryScopeFactory()).recover_interrupted()
    async with test_db_session() as session:
        row = await session.scalar(select(RequirementORM).where(RequirementORM.id == requirement["id"]))
        assert row.qa_model["history"][-1]["status"] == "RUNNING"
    await stream.aclose()
