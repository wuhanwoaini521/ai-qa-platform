"""Cancel is a request, not a status write (R18-B2).

The defect: whoever served `POST /api/tasks/{id}/cancel` wrote `CANCELLED` straight into the row, so a
replica that owned nothing could end a task another replica was still executing — overwriting that
owner's run state with a status it never produced. These tests pin the split: any authorized user may
record the request; only the lease holder (or recovery once the lease is provably gone) may write the
terminal status, and every terminal write is a single conditional statement.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import TaskEventORM, TaskORM, TaskStepORM, utc_now
from app.repositories.task_repo import TaskRepository
from app.services.task_lease_context import lease_scope, reset_lease
from project_model.task_models import TaskStatus
from sqlalchemy import select

pytestmark = pytest.mark.integration

runtime = get_task_runtime_service()
commands = runtime.commands
orchestrator = runtime.execution
scheduler = runtime.scheduler


async def _seed(
    session_factory,
    task_id: str = "task_cancel",
    *,
    status: str = "RUNNING",
    step_status: str = "RUNNING",
    cancel_requested: bool = False,
) -> str:
    async with session_factory() as session:
        session.add(
            TaskORM(
                id=task_id,
                type="RUN_REGRESSION",
                goal="Cancel me",
                status=status,
                owner_id="owner",
                inputs={},
                context={},
                verification={},
                current_step_id=f"{task_id}-step",
                cancel_requested_at=utc_now() if cancel_requested else None,
                cancel_requested_by="owner" if cancel_requested else None,
            )
        )
        session.add(
            TaskStepORM(
                id=f"{task_id}-step",
                task_id=task_id,
                position=0,
                key="run",
                name="Run the target test",
                tool="tests.run_target",
                status=step_status,
            )
        )
        await session.commit()
    return task_id


async def _claim(session_factory, task_id: str, *, owner: str = "worker-a", lease_seconds: int = 60) -> int:
    async with session_factory() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner=owner, lease_seconds=lease_seconds)
        await session.commit()
    assert token, "the test could not claim the task"
    return token


async def _row(session_factory, task_id: str) -> TaskORM:
    async with session_factory() as session:
        return await session.get(TaskORM, task_id)


async def _step(session_factory, step_id: str) -> TaskStepORM:
    async with session_factory() as session:
        return await session.get(TaskStepORM, step_id)


async def _events(session_factory, task_id: str) -> list[str]:
    async with session_factory() as session:
        rows = await session.execute(select(TaskEventORM.type).where(TaskEventORM.task_id == task_id))
        return [row[0] for row in rows]


async def test_the_owner_ends_its_own_task_at_a_boundary(test_db_session):
    task_id = await _seed(test_db_session)
    token = await _claim(test_db_session, task_id)

    detail = await commands.cancel(task_id, "owner")
    assert detail is not None
    row = await _row(test_db_session, task_id)
    assert row.status == "PLANNING", "a replica must not end a task another replica is still executing"
    assert row.cancel_requested_at is not None

    # The owner reaches a step boundary, sees the request and ends the task under its own lease.
    scope = lease_scope("worker-a", token)
    try:
        await orchestrator._finish(task_id, TaskStatus.CANCELLED, "Cancelled by user.")
    finally:
        reset_lease(scope)

    row = await _row(test_db_session, task_id)
    assert row.status == "CANCELLED"
    step = await _step(test_db_session, f"{task_id}-step")
    assert step.status == "CANCELLED"


async def test_a_replica_without_the_lease_only_records_the_request(test_db_session):
    task_id = await _seed(test_db_session)
    await _claim(test_db_session, task_id)

    await commands.cancel(task_id, "owner")

    row = await _row(test_db_session, task_id)
    events = await _events(test_db_session, task_id)
    assert row.status == "PLANNING"
    assert row.cancel_requested_by == "owner"
    assert "task.cancel_requested" in events
    assert "task.cancelled" not in events, "the replica that does not own the lease wrote the terminal status"


async def test_a_stale_replica_cannot_write_a_terminal_status(test_db_session):
    task_id = await _seed(test_db_session)
    first = await _claim(test_db_session, task_id, lease_seconds=-1)
    second = await _claim(test_db_session, task_id, owner="worker-b")

    async with test_db_session() as session:
        written = await TaskRepository(session).finish_fenced(task_id, "COMPLETED", owner="worker-a", token=first)
        await session.commit()

    row = await _row(test_db_session, task_id)
    assert second > first
    assert written is False
    assert row.status == "PLANNING", "the previous owner overwrote the task the new owner holds"


async def test_a_cancel_after_the_lease_expired_is_finalised_immediately(test_db_session):
    task_id = await _seed(test_db_session)
    await _claim(test_db_session, task_id, lease_seconds=-1)

    detail = await commands.cancel(task_id, "owner")

    row = await _row(test_db_session, task_id)
    assert detail is not None
    assert row.status == "CANCELLED", "nobody holds a live lease, so the cancel can be completed here"
    assert (await _step(test_db_session, f"{task_id}-step")).status == "CANCELLED"


async def test_recovery_closes_a_crashed_task_as_cancelled_when_the_user_asked(test_db_session):
    cancelled = await _seed(test_db_session, "task_recover_cancel", cancel_requested=True)
    blocked = await _seed(test_db_session, "task_recover_block")
    async with test_db_session() as session:
        for task_id in (cancelled, blocked):
            row = await session.get(TaskORM, task_id)
            row.lease_owner = "dead-worker"
            row.lease_token = 3
            row.lease_expires_at = utc_now() - timedelta(minutes=5)
            row.updated_at = utc_now() - timedelta(hours=1)
        await session.commit()

    recovered = await scheduler.recover_interrupted()

    assert set(recovered) == {cancelled, blocked}
    assert (await _row(test_db_session, cancelled)).status == "CANCELLED"
    assert (await _row(test_db_session, blocked)).status == "BLOCKED", "a crash without a request is still a block"


async def test_cancel_and_completion_cannot_both_win(test_db_session):
    task_id = await _seed(test_db_session)
    token = await _claim(test_db_session, task_id)

    async def owner_finishes() -> bool:
        scope = lease_scope("worker-a", token)
        try:
            await orchestrator._finish(task_id, TaskStatus.COMPLETED, None)
        finally:
            reset_lease(scope)
        return True

    _, completed = await asyncio.gather(commands.cancel(task_id, "owner"), owner_finishes())

    row = await _row(test_db_session, task_id)
    events = await _events(test_db_session, task_id)
    assert completed is True, "the owner held the lease, so its own completion must land"
    assert row.status == "COMPLETED"
    assert row.cancel_requested_at is not None, "the request is still recorded as a fact"
    terminal_events = [event for event in events if event in {"task.completed", "task.cancelled"}]
    assert terminal_events == ["task.completed"], "exactly one terminal transition may be announced"


async def test_a_worker_that_lost_its_lease_is_told_it_was_evicted(test_db_session):
    task_id = await _seed(test_db_session)
    stale = await _claim(test_db_session, task_id, lease_seconds=-1)
    await _claim(test_db_session, task_id, owner="worker-b")

    scope = lease_scope("worker-a", stale)
    try:
        await orchestrator._finish(task_id, TaskStatus.COMPLETED, None)
    finally:
        reset_lease(scope)

    row = await _row(test_db_session, task_id)
    events = await _events(test_db_session, task_id)
    assert row.status == "PLANNING"
    assert "task.lease_lost" in events


async def test_cancelling_twice_keeps_one_request_and_one_transition(test_db_session):
    task_id = await _seed(test_db_session)
    await _claim(test_db_session, task_id)

    first = await commands.cancel(task_id, "owner")
    second = await commands.cancel(task_id, "owner")

    row = await _row(test_db_session, task_id)
    events = await _events(test_db_session, task_id)
    assert first is not None and second is not None
    assert events.count("task.cancel_requested") == 1, "a repeated cancel must not rewrite the recorded request"
    assert row.status == "PLANNING"

    # The owner stops; cancelling an already-terminal task stays a no-op that reports nothing to do.
    scope = lease_scope("worker-a", 1)
    try:
        await orchestrator._finish(task_id, TaskStatus.CANCELLED, "Cancelled by user.")
    finally:
        reset_lease(scope)
    assert await commands.cancel(task_id, "owner") is None
    assert (await _events(test_db_session, task_id)).count("task.cancelled") == 1


async def test_the_request_survives_a_schema_round_trip(test_db_session):
    """Both supported backends must store and return the two new columns unchanged."""
    task_id = await _seed(test_db_session)
    async with test_db_session() as session:
        repo = TaskRepository(session)
        requested = await repo.request_cancel(task_id, "someone")
        await session.commit()
    assert requested is not None
    again = await _row(test_db_session, task_id)
    assert again.cancel_requested_at is not None
    assert again.cancel_requested_by == "someone"


@pytest.mark.postgres
async def test_postgres_cancel_and_completion_race_keeps_one_terminal_state(test_db_session):
    """Real concurrent transactions: the conditional writes must not lose each other's update."""
    task_id = await _seed(test_db_session)
    token = await _claim(test_db_session, task_id)

    async def request_cancel() -> None:
        async with test_db_session() as session:
            await TaskRepository(session).request_cancel(task_id, "owner")
            await TaskRepository(session).finish_fenced(
                task_id, "CANCELLED", require_no_live_lease=True, failure_reason=None
            )
            await session.commit()

    async def owner_finishes() -> bool:
        async with test_db_session() as session:
            written = await TaskRepository(session).finish_fenced(task_id, "COMPLETED", owner="worker-a", token=token)
            await session.commit()
            return written

    finished = await owner_finishes()

    row = await _row(test_db_session, task_id)
    assert finished is (row.status == "COMPLETED"), "the owner's write and the row must agree"
    assert row.status in {"COMPLETED", "CANCELLED"}
    assert await _row(test_db_session, task_id) is not None
