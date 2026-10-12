from __future__ import annotations

import pytest
from app.services.locator_repair_state_machine import (
    IllegalLocatorRepairTransition,
    LocatorRepairStateMachine,
)
from project_model.models import FailureRepairState


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (FailureRepairState.CREATED, FailureRepairState.ANALYZING),
        (FailureRepairState.ANALYZING, FailureRepairState.DECIDING),
        (FailureRepairState.DECIDING, FailureRepairState.VERIFYING_CANDIDATE),
        (FailureRepairState.VERIFYING_CANDIDATE, FailureRepairState.PATCH_READY),
        (FailureRepairState.PATCH_READY, FailureRepairState.APPLYING),
        (FailureRepairState.APPLYING, FailureRepairState.PATCH_APPLIED),
        (FailureRepairState.PATCH_APPLIED, FailureRepairState.VERIFYING_FIX),
        (FailureRepairState.VERIFYING_FIX, FailureRepairState.VERIFIED),
        (FailureRepairState.FAILED, FailureRepairState.ROLLED_BACK),
    ],
)
def test_locator_repair_state_machine_accepts_declared_transitions(current, target):
    assert LocatorRepairStateMachine().transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (FailureRepairState.CREATED, FailureRepairState.VERIFIED),
        (FailureRepairState.ANALYZING, FailureRepairState.PATCH_APPLIED),
        (FailureRepairState.PATCH_READY, FailureRepairState.VERIFIED),
        (FailureRepairState.VERIFIED, FailureRepairState.PATCH_READY),
        (FailureRepairState.ROLLED_BACK, FailureRepairState.APPLYING),
    ],
)
def test_locator_repair_state_machine_rejects_illegal_transitions(current, target):
    with pytest.raises(IllegalLocatorRepairTransition):
        LocatorRepairStateMachine().transition(current, target)


def test_locator_repair_state_machine_allows_idempotent_reconciliation():
    assert (
        LocatorRepairStateMachine().transition(
            FailureRepairState.VERIFIED,
            FailureRepairState.VERIFIED,
        )
        is FailureRepairState.VERIFIED
    )


def test_locator_repair_block_reason_is_a_stable_non_sensitive_code():
    machine = LocatorRepairStateMachine()
    assert machine._reason_code("AI_BUDGET_EXHAUSTED", FailureRepairState.BLOCKED) == "AI_BUDGET_EXHAUSTED"
    assert machine._reason_code("Bearer secret-token", FailureRepairState.BLOCKED) == "UNSPECIFIED_BLOCK"


@pytest.mark.asyncio
async def test_illegal_persisted_transition_leaves_locator_repair_unchanged(test_db_session):
    from app.persistence.models import (
        FailureAnalysisORM,
        FailureRecordORM,
        ProjectORM,
        TestExecutionORM,
        TestRunORM,
    )
    from app.repositories.locator_repair_repo import LocatorRepairRepository

    repair_id = None
    async with test_db_session() as session:
        session.add(ProjectORM(id="project", name="State machine"))
        await session.flush()
        session.add(TestRunORM(id="run", project_id="project", workspace_id="project"))
        await session.flush()
        session.add(
            TestExecutionORM(
                id="execution",
                run_id="run",
                nodeid="tests/test_state.py::test_state",
            )
        )
        await session.flush()
        session.add(
            FailureRecordORM(
                id="failure",
                run_id="run",
                execution_id="execution",
                test_nodeid="tests/test_state.py::test_state",
                test_name="test_state",
            )
        )
        await session.flush()
        session.add(FailureAnalysisORM(id="analysis", failure_id="failure"))
        await session.flush()
        repository = LocatorRepairRepository(session)
        machine = LocatorRepairStateMachine()
        repair = await machine.create(repository, failure_id="failure", analysis_id="analysis")
        repair_id = repair.id
        await machine.move(repository, repair.id, FailureRepairState.ANALYZING)

        with pytest.raises(IllegalLocatorRepairTransition):
            await machine.move(repository, repair.id, FailureRepairState.VERIFIED)

        await session.commit()

    async with test_db_session() as verify_session:
        repository = LocatorRepairRepository(verify_session)
        persisted = await repository.get_by_id(repair_id)
        assert persisted is not None
        assert persisted.state is FailureRepairState.ANALYZING
        machine = LocatorRepairStateMachine()
        await machine.move(
            repository,
            repair_id,
            FailureRepairState.FAILED,
            block_reason="VERIFICATION_FAILED",
        )
        await machine.move(repository, repair_id, FailureRepairState.ROLLED_BACK)
        assert persisted.state is FailureRepairState.ROLLED_BACK
        assert persisted.block_reason == "VERIFICATION_FAILED"
