"""Workflow tests use explicit fixtures; these are not Golden Demo invocation evidence."""

from types import SimpleNamespace

import pytest
from app.persistence.models import RequirementORM
from app.repositories.requirement_repo import RequirementRepository
from app.services.golden_demo_service import DEMO_REQUIREMENT, demo_document
from app.services.requirement_lifecycle_service import RequirementAnalysisBusy, RequirementLifecycleService
from app.services.requirement_service import RequirementService
from project_model.lifecycle import RequirementDocument
from project_model.models import DecisionResult, RequirementUpdate
from qa_core.ai.models import AICompletionResponse
from qa_core.ai.provider import FakeAIProvider
from sqlalchemy import select


class TestOrchestrator:
    __test__ = False
    ai_provider = SimpleNamespace(provider_name="unit_fixture", model="schema_fixture")

    async def complete(self, request):
        analysis = demo_document().analysis
        analysis.summary = "A structured fixture response, not a production model invocation"
        return AICompletionResponse(
            content="{}",
            structured_data=analysis.model_dump(mode="json"),
            provider="unit_fixture",
            model="schema_fixture",
        )


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


@pytest.mark.asyncio
async def test_structured_analysis_preserves_history_and_detects_changed_inputs(client):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(TestOrchestrator(), TestDecisions())
    events = [event async for event in workflow.stream(DEMO_REQUIREMENT)]
    assert events[-1].type == "run.completed"
    requirement = (await client.get(f"/api/requirements/{DEMO_REQUIREMENT}")).json()
    document = RequirementDocument.model_validate(requirement["qa_model"])
    assert document.analysis.scenarios[0].id == "SCN-004"
    assert document.analysis.risks[0].id == "RISK-002"
    record = document.history[-1]
    assert record.status == "SUCCESS" and record.analysis_snapshot.summary == document.analysis.summary
    assert record.input_hash and len(record.stages) == 4 and len(record.decisions) == 2
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
async def test_fake_provider_is_explicit_and_reference_analysis_is_preserved(client):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(SimpleNamespace(ai_provider=FakeAIProvider()), TestDecisions())
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

    workflow = RequirementLifecycleService(InvalidOrchestrator(), TestDecisions())
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
async def test_concurrent_analysis_and_edits_are_rejected_and_close_is_recorded(client, test_db_session):
    await client.post("/api/projects/golden-demo/seed")
    workflow = RequirementLifecycleService(TestOrchestrator(), TestDecisions())
    stream = workflow.stream(DEMO_REQUIREMENT)
    await anext(stream)
    competing = workflow.stream(DEMO_REQUIREMENT)
    with pytest.raises(RequirementAnalysisBusy):
        await anext(competing)
    async with test_db_session() as session:
        with pytest.raises(ValueError, match="running"):
            await RequirementService(RequirementRepository(session)).update_requirement(
                DEMO_REQUIREMENT, RequirementUpdate(title="New title")
            )
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
    workflow = RequirementLifecycleService(TestOrchestrator(), TestDecisions())
    stream = workflow.stream(requirement["id"])
    await anext(stream)
    await RequirementLifecycleService.recover_interrupted()
    async with test_db_session() as session:
        row = await session.scalar(select(RequirementORM).where(RequirementORM.id == requirement["id"]))
        assert row.qa_model["history"][-1]["status"] == "FAILED"
        assert row.qa_model["criteria"][0]["id"] == "AC-001"
    await stream.aclose()
