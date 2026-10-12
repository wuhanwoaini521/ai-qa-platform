from __future__ import annotations

import json
from datetime import timedelta

import pytest
from app.persistence.models import (
    AIInvocationORM,
    BrowserSessionORM,
    FailureAnalysisORM,
    FailureRecordORM,
    LocatorRepairORM,
    ProjectORM,
    utc_now,
)
from app.persistence.models import (
    TestExecutionORM as _TestExecutionORM,
)
from app.persistence.models import (
    TestRunORM as _TestRunORM,
)
from app.repositories.ai_repo import AIRepository
from app.repositories.locator_repair_repo import LocatorRepairRepository
from app.services.locator_repair_context import bind_locator_repair, reset_locator_repair
from project_model.models import FailureRepairState
from qa_core.ai.trace import make_trace_event
from sqlalchemy import func, select


async def _create_repair(session, *, project_id: str, suffix: str, state: FailureRepairState, block_reason=None):
    run_id = f"run-{suffix}"
    execution_id = f"execution-{suffix}"
    failure_id = f"failure-{suffix}"
    analysis_id = f"analysis-{suffix}"
    session.add(_TestRunORM(id=run_id, project_id=project_id, workspace_id=project_id))
    await session.flush()
    session.add(_TestExecutionORM(id=execution_id, run_id=run_id, nodeid=f"tests/test_{suffix}.py::test_case"))
    await session.flush()
    session.add(
        FailureRecordORM(
            id=failure_id,
            run_id=run_id,
            execution_id=execution_id,
            test_nodeid=f"tests/test_{suffix}.py::test_case",
            test_name="test_case",
        )
    )
    await session.flush()
    session.add(FailureAnalysisORM(id=analysis_id, failure_id=failure_id))
    await session.flush()
    return await LocatorRepairRepository(session).create(
        failure_id,
        analysis_id=analysis_id,
        state=state,
        block_reason=block_reason,
    )


@pytest.mark.asyncio
async def test_repair_funnel_counts_states_reasons_and_correlated_invocations(client, test_db_session):
    async with test_db_session() as session:
        session.add_all(
            [
                ProjectORM(id="project-one", name="One"),
                ProjectORM(id="project-two", name="Two"),
            ]
        )
        await session.flush()
        blocked = await _create_repair(
            session,
            project_id="project-one",
            suffix="one",
            state=FailureRepairState.BLOCKED,
            block_reason="AI_BUDGET_EXHAUSTED",
        )
        ready = await _create_repair(
            session,
            project_id="project-one",
            suffix="two",
            state=FailureRepairState.PATCH_READY,
        )
        other = await _create_repair(
            session,
            project_id="project-two",
            suffix="three",
            state=FailureRepairState.FAILED,
            block_reason="VERIFICATION_FAILED",
        )
        invocations = [
            ("inv-1", blocked.id, "locator_choice", "jev", "SUCCESS", False),
            ("inv-2", blocked.id, "repair_diagnosis", "openai", "FAILED", True),
            ("inv-3", ready.id, "locator_choice", "fake", "FALLBACK", True),
            ("inv-4", other.id, "locator_choice", "jev", "SUCCESS", False),
        ]
        session.add_all(
            [
                AIInvocationORM(
                    id=invocation_id,
                    locator_repair_id=repair_id,
                    task=task,
                    provider=provider,
                    model="test-model",
                    status=status,
                    fallback_used=fallback,
                )
                for invocation_id, repair_id, task, provider, status, fallback in invocations
            ]
        )
        await session.commit()

        response = await client.get("/api/quality/repair-funnel?project_id=project-one")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["project_id"] == "project-one"
        assert payload["total_repairs"] == 2
        assert payload["stage_counts"]["BLOCKED"] == 1
        assert payload["stage_counts"]["PATCH_READY"] == 1
        assert sum(payload["stage_counts"].values()) == 2
        assert payload["blocking_reasons"] == {"AI_BUDGET_EXHAUSTED": 1}
        assert payload["ai_invocations"] == {
            "total": 3,
            "fallback": 2,
            "linked_repairs": 2,
            "by_task": {"locator_choice": 2, "repair_diagnosis": 1},
            "by_provider": {"fake": 1, "jev": 1, "openai": 1},
            "by_status": {"FAILED": 1, "FALLBACK": 1, "SUCCESS": 1},
            "by_repair_state": {"BLOCKED": 2, "PATCH_READY": 1},
        }

        linked_count = await session.scalar(
            select(func.count(AIInvocationORM.id)).where(AIInvocationORM.locator_repair_id.in_([blocked.id, ready.id]))
        )
        assert payload["ai_invocations"]["total"] == linked_count

        other_response = await client.get("/api/quality/repair-funnel?project_id=project-two")
        assert other_response.status_code == 200
        assert other_response.json()["total_repairs"] == 1
        assert other_response.json()["ai_invocations"]["total"] == 1


@pytest.mark.asyncio
async def test_repair_funnel_requires_project_scope(client):
    response = await client.get("/api/quality/repair-funnel")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ai_repository_correlates_invocations_with_current_locator_repair(test_db_session):
    async with test_db_session() as session:
        session.add(ProjectORM(id="context-project", name="Context"))
        await session.flush()
        repair = await _create_repair(
            session,
            project_id="context-project",
            suffix="context",
            state=FailureRepairState.ANALYZING,
        )
        await session.commit()

    token = bind_locator_repair(repair.id)
    try:
        invocation = await AIRepository(test_db_session).record_invocation(
            task="repair_diagnosis",
            provider="fake",
            model="fake-model",
        )
    finally:
        reset_locator_repair(token)

    assert invocation.locator_repair_id == repair.id


@pytest.mark.asyncio
async def test_failure_get_paths_project_verification_without_persisting_or_cleaning(client, test_db_session):
    async with test_db_session() as session:
        session.add(ProjectORM(id="read-only-project", name="Read only"))
        await session.flush()
        repair = await _create_repair(
            session,
            project_id="read-only-project",
            suffix="read-only",
            state=FailureRepairState.VERIFYING_FIX,
        )
        failure = await session.get(FailureRecordORM, repair.failure_id)
        analysis = await session.get(FailureAnalysisORM, repair.analysis_id)
        original_run = await session.get(_TestRunORM, failure.run_id)
        verification_run = _TestRunORM(
            id="verification-run",
            project_id="read-only-project",
            workspace_id="read-only-project",
            status="PASSED",
            nodeids=[failure.test_nodeid],
        )
        session.add(verification_run)
        await session.flush()
        session.add(
            _TestExecutionORM(
                id="verification-execution",
                run_id=verification_run.id,
                nodeid=failure.test_nodeid,
                status="PASSED",
            )
        )
        proposal = {
            "proposed_locator": 'get_by_test_id("checkout")',
            "applied": True,
            "applied_at": utc_now().isoformat(),
            "verified": True,
        }
        failure.repair_proposal = proposal
        analysis.result = {
            "repair_state": "VERIFYING_FIX",
            "repair_proposal": proposal,
            "verification_run_id": verification_run.id,
        }
        analysis.events = [
            make_trace_event(
                original_run.id,
                "verification.started",
                stage="verification",
                step_id=f"{analysis.id}:verification",
                title="Verification started",
                metadata={"verification_run_id": verification_run.id},
            ).model_dump(mode="json")
        ]
        repair.verification_run_id = verification_run.id
        session.add(
            BrowserSessionORM(
                id="expired-snapshot",
                run_id=original_run.id,
                case_execution_id=failure.execution_id,
                browser_session_id="browser-session",
                page_id="page",
                nodeid=failure.test_nodeid,
                current_url="https://example.test/checkout",
                failure_snapshot_json=json.dumps(
                    {
                        "status": "PARTIAL",
                        "storage_state_status": "AVAILABLE",
                        "evidence_gaps": [],
                        "replay": {"status": "PARTIAL"},
                    }
                ),
                encrypted_storage_state="encrypted-state-must-not-be-returned",
                storage_state_expires_at=utc_now() - timedelta(days=1),
            )
        )
        await session.commit()
        before = {
            "analysis_result": analysis.result,
            "analysis_events": analysis.events,
            "repair_state": repair.state.value,
            "encrypted_storage_state": "encrypted-state-must-not-be-returned",
        }

    workflow_response = await client.get(
        f"/api/failures/{repair.failure_id}/repair-workflow?analysis_id={repair.analysis_id}"
    )
    history_response = await client.get(f"/api/failures/{repair.failure_id}/analyses")
    assert workflow_response.status_code == 200, workflow_response.text
    assert history_response.status_code == 200, history_response.text
    assert workflow_response.json()["state"] == "VERIFIED"
    assert workflow_response.json()["repair_id"] == repair.id
    assert workflow_response.json()["failure_snapshot"]["storage_state_status"] == "EXPIRED"
    assert "encrypted-state-must-not-be-returned" not in workflow_response.text
    assert history_response.json()[0]["result"]["repair_state"] == "VERIFIED"
    assert any(event["type"] == "verification.completed" for event in history_response.json()[0]["events"])

    async with test_db_session() as session:
        persisted_analysis = await session.get(FailureAnalysisORM, repair.analysis_id)
        persisted_repair = await session.get(LocatorRepairORM, repair.id)
        expired_snapshot = await session.get(BrowserSessionORM, "expired-snapshot")
        assert persisted_analysis.result == before["analysis_result"]
        assert persisted_analysis.events == before["analysis_events"]
        assert persisted_repair.state.value == before["repair_state"]
        assert expired_snapshot.encrypted_storage_state == before["encrypted_storage_state"]
