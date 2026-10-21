from __future__ import annotations

import json
from typing import Any

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import ProjectORM, TaskEvidenceORM, TestCaseORM
from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.repositories.task_repo import TaskRepository
from app.services.discovery_evidence_capture import EvidenceRecord
from project_model.models import DecisionResult
from qa_core.ai.models import AICompletionResponse
from qa_core.ai.provider import AIProviderError
from qa_core.ai.registry import AIProviderRegistry
from sqlalchemy import select

pytestmark = pytest.mark.integration

PROJECT = "project_intelligence"
RUN = "qd_intelligence"
task_runtime_service = get_task_runtime_service()
commands = task_runtime_service.commands
scheduler = task_runtime_service.scheduler


async def _seed(session_factory, *, scenarios: list[dict[str, Any]], evidence: list[EvidenceRecord]) -> None:
    async with session_factory() as session:
        session.add(ProjectORM(id=PROJECT, name="Intelligence project"))
        run = await QualityDiscoveryRepository(session).create(
            project_id=PROJECT,
            requested_by="owner-1",
            mode="EXPLORE",
            start_url="https://example.test/shop",
            requirement_id=None,
            requirement_text="",
            allowed_domains=[],
        )
        await QualityDiscoveryRepository(session).update(run.id, status="COMPLETED", result={"states": []})
        repository = DiscoveryEvidenceRepository(session)
        await repository.record(run.id, PROJECT, evidence, max_records=100)
        await repository.replace_scenarios(run.id, PROJECT, scenarios)
        await session.commit()
    # the run id is generated, so the seeded rows have to be found again by start url
    async with session_factory() as session:
        rows = await QualityDiscoveryRepository(session).list_by_project(PROJECT, limit=5)
        global RUN
        RUN = rows[0].id


def _element(evidence_id: str = "dom_a", name: str = "View health") -> EvidenceRecord:
    return EvidenceRecord(
        kind="dom_element",
        evidence_id=evidence_id,
        dedupe_key=f"{evidence_id}|key",
        payload={"tag": "button", "role": "button", "name": name, "count_in_state": 1, "enabled": True},
        state_id="state_a",
    )


def _network(evidence_id: str = "net_a") -> EvidenceRecord:
    return EvidenceRecord(
        kind="network_request",
        evidence_id=evidence_id,
        dedupe_key=f"{evidence_id}|key",
        payload={
            "method": "GET",
            "url_template": "https://example.test/api/health",
            "statuses": [200],
            "resource": "api",
        },
        state_id="state_a",
        step_id="step_a",
    )


def _action(evidence_id: str = "act_a") -> EvidenceRecord:
    return EvidenceRecord(
        kind="user_action",
        evidence_id=evidence_id,
        dedupe_key=f"{evidence_id}|key",
        payload={
            "action": "click",
            "target": "View health",
            "status": "executed",
            "state_changed": True,
            "network_evidence_ids": ["net_a"],
        },
        state_id="state_a",
        step_id="step_a",
    )


def _scenario(scenario_id: str, status: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "title": f"Click View health on {scenario_id}",
        "url_template": "https://example.test/shop",
        "evidence_ids": evidence_ids,
        "test_case_ids": [],
        "coverage_status": status,
        "match_method": "target_wording" if status == "COVERED" else "",
        "note": "",
    }


class _Provider:
    """A provider double: the analysis path is exercised, the network is not."""

    def __init__(self, answer: dict[str, Any] | Exception, *, provider: str = "openai-compatible") -> None:
        self.answer = answer
        self.provider = provider
        self.prompts: list[str] = []

    async def complete(self, request):
        self.prompts.append(request.prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return AICompletionResponse(
            content="{}",
            structured_data=self.answer,
            provider=self.provider,
            model="test-model",
            invocation_id="inv-1",
            input_tokens=120,
            output_tokens=40,
            fallback_used=self.provider == "fake",
        )


def _install(monkeypatch, provider: _Provider, *, jev: Any = None) -> None:
    monkeypatch.setattr(AIProviderRegistry, "get_provider", classmethod(lambda cls, *a, **k: provider))
    if jev is not None:
        from app.services.task_decision_service import TaskDecisionService

        async def ask_score(self, request, *, task_id, run_id):
            if isinstance(jev, Exception):
                raise jev
            return jev

        monkeypatch.setattr(TaskDecisionService, "ask_score", ask_score)


async def _run_task(client, session_factory) -> str:
    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_DISCOVERY",
            "goal": "Read the unsettled scenarios",
            "project_id": PROJECT,
            "inputs": {"discovery_run_id": RUN},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    await scheduler._execute_task(task_id)
    return task_id


async def _suggestions(session_factory) -> list[Any]:
    async with session_factory() as session:
        return await DiscoverySuggestionRepository(session).list_by_run(RUN, limit=50)


async def _task(session_factory, task_id: str):
    async with session_factory() as session:
        return await TaskRepository(session).get(task_id)


ANALYSIS = {
    "is_gap": True,
    "summary": "Clicking View health is not asserted anywhere.",
    "reasoning": "The action ran and produced a 200, but no case references it.",
    "evidence_ids": ["dom_a", "net_a", "act_a"],
    "related_test_case_ids": [],
    "suggested_title": "Health status is visible after clicking View health",
    "suggested_steps": [{"action": "click", "target": "View health", "expectation": "A 200 health response"}],
    "uncertainty": "",
    "needs_human_review": True,
    "risk": "medium",
}


async def test_only_unsettled_scenarios_are_sent_to_the_model(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[
            _scenario("scen_covered", "COVERED", ["dom_a"]),
            _scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"]),
            _scenario("scen_unknown", "UNDETERMINED", ["dom_a"]),
        ],
        evidence=[_element(), _network(), _action()],
    )
    provider = _Provider(ANALYSIS)
    _install(monkeypatch, provider)

    task_id = await _run_task(client, test_db_session)

    assert len(provider.prompts) == 2
    assert all("scen_covered" not in prompt for prompt in provider.prompts)
    assert any("scen_candidate" in prompt for prompt in provider.prompts)
    task = await _task(test_db_session, task_id)
    assert task.status == "COMPLETED"
    suggestions = await _suggestions(test_db_session)
    assert {row.scenario_id for row in suggestions} == {"scen_candidate", "scen_unknown"}


async def test_a_suggestion_cannot_cite_evidence_the_database_does_not_hold(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    provider = _Provider({**ANALYSIS, "evidence_ids": ["dom_a", "dom_invented"]})
    _install(monkeypatch, provider)

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "REJECTED"
    assert row.error_type == "UNKNOWN_EVIDENCE"
    assert row.evidence_ids == []
    assert row.payload.get("summary") is None
    assert row.payload["unknown_evidence_ids"] == ["dom_invented"]


async def test_a_suggestion_cannot_reference_a_foreign_test_case(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider({**ANALYSIS, "related_test_case_ids": ["tc_not_here"]}))

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "REJECTED"
    assert row.error_type == "UNKNOWN_TEST_CASE"


async def test_a_scenario_without_evidence_is_reported_as_insufficient_not_guessed(
    client, test_db_session, monkeypatch
):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_bare", "UNDETERMINED", ["dom_missing"])],
        evidence=[_element()],
    )
    provider = _Provider(ANALYSIS)
    _install(monkeypatch, provider)

    await _run_task(client, test_db_session)

    assert provider.prompts == []
    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "INSUFFICIENT_EVIDENCE"
    assert "no reading was attempted" in row.payload["reason"]


async def test_the_answer_is_kept_with_the_evidence_it_read_and_repeats_are_idempotent(
    client, test_db_session, monkeypatch
):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))

    await _run_task(client, test_db_session)
    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "COMPLETED"
    assert row.payload["grounded"] is True
    assert row.evidence_ids == ["dom_a", "net_a", "act_a"]
    assert row.attempts == 2
    assert row.payload["coverage_status"] == "CANDIDATE_GAP"


async def test_an_explicit_reanalysis_keeps_the_previous_reading(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))
    await _run_task(client, test_db_session)

    created = await client.post(
        "/api/tasks",
        json={
            "type": "ANALYZE_DISCOVERY",
            "goal": "Read again",
            "project_id": PROJECT,
            "inputs": {"discovery_run_id": RUN, "reanalyze_token": "token-2"},
        },
    )
    assert created.status_code == 201, created.text
    await scheduler._execute_task(created.json()["id"])

    rows = await _suggestions(test_db_session)
    assert len(rows) == 2
    assert len({row.input_hash for row in rows}) == 2


async def test_a_provider_failure_is_recorded_without_failing_the_task(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(AIProviderError("timeout", "upstream timed out")))

    task_id = await _run_task(client, test_db_session)

    task = await _task(test_db_session, task_id)
    assert task.status == "COMPLETED"
    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "FAILED"
    assert row.error_type == "AIProviderError"
    assert "timed out" in row.error_detail


async def test_a_fallback_answer_is_not_recorded_as_a_model_reading(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS, provider="fake"))

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.analysis_status == "DEGRADED"
    assert row.payload["grounded"] is None
    assert row.evidence_ids == []


async def test_jev_fallback_does_not_claim_a_jev_grade(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(
        monkeypatch,
        _Provider(ANALYSIS),
        jev=DecisionResult(provider="fallback", fallback_used=True, reason="invalid_request"),
    )

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.jev["status"] == "JEV_FALLBACK"
    assert row.jev["source"] == "rules"
    assert row.jev["grade"] == row.jev["rule_grade"]
    assert row.jev["calibrated"] is False


async def test_a_low_confidence_jev_answer_is_not_reported_as_unavailable(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(
        monkeypatch,
        _Provider(ANALYSIS),
        jev=DecisionResult(
            provider="fallback",
            fallback_used=True,
            reason="below_minimum_confidence",
            confidence=0.17,
        ),
    )

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.jev["status"] == "JEV_LOW_CONFIDENCE"
    assert row.jev["source"] == "rules"
    assert row.jev["grade"] == row.jev["rule_grade"]
    assert row.jev["reason"] == "below_minimum_confidence"
    summary = await client.get(f"/api/discovery/runs/{RUN}/suggestions/summary")
    assert summary.json()["jev_fallback"] == 1
    assert summary.json()["jev_graded"] == 0


async def test_a_jev_timeout_is_reported_as_a_timeout(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(
        monkeypatch,
        _Provider(ANALYSIS),
        jev=DecisionResult(provider="fallback", fallback_used=True, reason="timeout"),
    )

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.jev["status"] == "JEV_TIMEOUT"
    assert row.jev["source"] == "rules"


async def test_a_jev_grade_records_where_the_number_came_from(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(
        monkeypatch,
        _Provider(ANALYSIS),
        jev=DecisionResult(provider="jev", model="jev-1.13.0", score=0.82, confidence=0.9),
    )

    await _run_task(client, test_db_session)

    [row] = await _suggestions(test_db_session)
    assert row.jev["status"] == "JEV_GRADED"
    assert row.jev["source"] == "jev"
    assert row.jev["score"] == 0.82
    assert row.jev["grade"] == "sufficient"
    assert row.jev["calibrated"] is False


async def test_a_rejection_needs_a_reason_and_writes_no_case(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))
    await _run_task(client, test_db_session)
    [row] = await _suggestions(test_db_session)

    without_reason = await client.post(
        f"/api/discovery/runs/{RUN}/suggestions/{row.suggestion_id}/review",
        json={"decision": "REJECT", "comment": ""},
    )
    assert without_reason.status_code == 422

    rejected = await client.post(
        f"/api/discovery/runs/{RUN}/suggestions/{row.suggestion_id}/review",
        json={"decision": "REJECT", "comment": "The wording is too vague to be a case."},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["suggestion"]["review_status"] == "REJECTED"
    async with test_db_session() as session:
        assert (await session.execute(TestCaseORM.__table__.select())).all() == []


async def test_an_approved_suggestion_becomes_a_case_only_after_approval(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))
    await _run_task(client, test_db_session)
    [row] = await _suggestions(test_db_session)

    accepted = await client.post(
        f"/api/discovery/runs/{RUN}/suggestions/{row.suggestion_id}/review",
        json={"decision": "ACCEPT", "comment": "Looks real."},
    )
    assert accepted.json()["created_case_id"] is None

    approved = await client.post(
        f"/api/discovery/runs/{RUN}/suggestions/{row.suggestion_id}/review",
        json={"decision": "APPROVE_CREATE_CASE", "comment": "Create it."},
    )
    assert approved.status_code == 200, approved.text
    case_id = approved.json()["created_case_id"]
    assert case_id
    async with test_db_session() as session:
        case = await session.get(TestCaseORM, case_id)
    assert case is not None
    assert case.title == ANALYSIS["suggested_title"]
    assert "ai-suggestion" in case.tags
    assert f"suggestion:{row.suggestion_id}" in case.tags

    again = await client.post(
        f"/api/discovery/runs/{RUN}/suggestions/{row.suggestion_id}/review",
        json={"decision": "APPROVE_CREATE_CASE", "comment": "Twice."},
    )
    assert again.json()["created_case_id"] == case_id


async def test_a_repeated_analysis_request_reuses_the_live_task(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))

    first = await client.post(f"/api/discovery/runs/{RUN}/intelligence", json={})
    assert first.status_code == 202, first.text
    second = await client.post(f"/api/discovery/runs/{RUN}/intelligence", json={})
    assert second.status_code == 202, second.text
    assert second.json()["reused"] is True
    assert second.json()["task_id"] == first.json()["task_id"]


async def test_reading_suggestions_never_starts_a_task(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))
    await _run_task(client, test_db_session)
    async with test_db_session() as session:
        before = len(await TaskRepository(session).list_by_project(PROJECT, limit=50))

    listed = await client.get(f"/api/discovery/runs/{RUN}/suggestions")
    summary = await client.get(f"/api/discovery/runs/{RUN}/suggestions/summary")
    suggestion_id = listed.json()["suggestions"][0]["suggestion_id"]
    detail = await client.get(f"/api/discovery/runs/{RUN}/suggestions/{suggestion_id}")

    assert listed.status_code == 200 and listed.json()["summary"]["total"] == 1
    assert summary.status_code == 200 and summary.json()["pending_review"] == 1
    assert detail.status_code == 200 and detail.json()["evidence"]
    async with test_db_session() as session:
        assert len(await TaskRepository(session).list_by_project(PROJECT, limit=50)) == before


async def test_an_analysis_of_a_run_that_does_not_exist_is_refused(client, test_db_session, monkeypatch):
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))

    created = await client.post("/api/discovery/runs/qd_missing/intelligence", json={})
    listed = await client.get("/api/discovery/runs/qd_missing/suggestions")

    assert created.status_code == 404
    assert listed.status_code in {403, 404}


async def test_a_reading_leaves_a_task_level_evidence_reference(client, test_db_session, monkeypatch):
    """The execution trace has to find the discovery evidence a reading read, on the task itself."""
    await _seed(
        test_db_session,
        scenarios=[_scenario("scen_candidate", "CANDIDATE_GAP", ["dom_a", "net_a", "act_a"])],
        evidence=[_element(), _network(), _action()],
    )
    _install(monkeypatch, _Provider(ANALYSIS))

    task_id = await _run_task(client, test_db_session)

    async with test_db_session() as session:
        rows = (
            (await session.execute(select(TaskEvidenceORM).where(TaskEvidenceORM.task_id == task_id))).scalars().all()
        )
    assert rows, "the analysis step left no task-level evidence"
    [row] = rows
    assert row.type == "RuntimeMetadata"
    assert row.source == f"discovery_evidence:{RUN}"
    assert "3 evidence rows" in row.summary
    assert json.loads(row.content)[0]["evidence_ids"] == ["dom_a", "net_a", "act_a"]
