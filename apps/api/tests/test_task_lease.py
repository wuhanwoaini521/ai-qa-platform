from __future__ import annotations

from datetime import timedelta

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import TaskORM, utc_now
from app.repositories.task_repo import TaskRepository
from app.services.task_lease_context import lease_scope, reset_lease

pytestmark = pytest.mark.integration

runtime = get_task_runtime_service()
scheduler = runtime.scheduler


async def _task(session_factory, task_id: str = "task_lease") -> str:
    async with session_factory() as session:
        session.add(
            TaskORM(
                id=task_id,
                type="RUN_REGRESSION",
                goal="Prove the lease",
                status="PENDING",
                owner_id="owner",
                project_id=None,
                inputs={},
                context={},
                verification={},
            )
        )
        await session.commit()
    return task_id


async def test_two_workers_cannot_claim_the_same_task(test_db_session):
    task_id = await _task(test_db_session)

    async with test_db_session() as first:
        token = await TaskRepository(first).claim_for_execution(task_id, owner="worker-a", lease_seconds=60)
        await first.commit()
    async with test_db_session() as second:
        taken = await TaskRepository(second).claim_for_execution(task_id, owner="worker-b", lease_seconds=60)
        await second.commit()

    assert token == 1
    assert taken is None, "a second worker claimed a task that is already owned"


async def test_an_expired_lease_can_be_taken_over_by_another_worker(test_db_session):
    task_id = await _task(test_db_session, "task_expired")

    async with test_db_session() as first:
        first_token = await TaskRepository(first).claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await first.commit()
    async with test_db_session() as second:
        second_token = await TaskRepository(second).claim_for_execution(task_id, owner="worker-b", lease_seconds=60)
        await second.commit()

    assert (first_token, second_token) == (1, 2), "the fencing token must move on so the old owner is stale"
    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        assert row.lease_owner == "worker-b"


async def test_a_heartbeat_only_renews_the_current_owner(test_db_session):
    task_id = await _task(test_db_session, "task_heartbeat")
    async with test_db_session() as first:
        token = await TaskRepository(first).claim_for_execution(task_id, owner="worker-a", lease_seconds=30)
        await first.commit()
    async with test_db_session() as second:
        repo = TaskRepository(second)
        assert await repo.renew_lease(task_id, "worker-b", token or 0, 30) is False
        assert await repo.renew_lease(task_id, "worker-a", (token or 0) + 1, 30) is False
        assert await repo.renew_lease(task_id, "worker-a", token or 0, 300) is True
        await second.commit()

    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        assert row.lease_expires_at is not None
        assert row.lease_expires_at > utc_now() + timedelta(seconds=200)


async def test_a_worker_that_lost_its_lease_cannot_write_a_terminal_state(test_db_session):
    task_id = await _task(test_db_session, "task_fenced")
    async with test_db_session() as first:
        token = await TaskRepository(first).claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await first.commit()
    async with test_db_session() as second:
        await TaskRepository(second).claim_for_execution(task_id, owner="worker-b", lease_seconds=60)
        await second.commit()

    context_token = lease_scope("worker-a", token or 0)
    try:
        await runtime.execution._finish(
            task_id,
            runtime.execution.TERMINAL.__class__
            and __import__("project_model.task_models", fromlist=["TaskStatus"]).TaskStatus.COMPLETED,
            "stale writer",
        )
    finally:
        reset_lease(context_token)

    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        events = await TaskRepository(session).events_after(task_id, 0)
    assert row.status == "PLANNING", "a stale worker wrote a terminal state over the new owner"
    assert any(event.type == "task.lease_lost" for event in events)


async def test_recovery_leaves_a_live_lease_alone_and_recovers_a_stale_one(test_db_session):
    async with test_db_session() as session:
        session.add_all(
            [
                TaskORM(
                    id="task_live",
                    type="RUN_REGRESSION",
                    goal="Someone is working on this",
                    status="RUNNING",
                    owner_id="owner",
                    inputs={},
                    context={},
                    verification={},
                    lease_owner="worker-a",
                    lease_token=1,
                    lease_expires_at=utc_now() + timedelta(seconds=60),
                ),
                TaskORM(
                    id="task_dead",
                    type="RUN_REGRESSION",
                    goal="Its owner disappeared",
                    status="RUNNING",
                    owner_id="owner",
                    inputs={},
                    context={},
                    verification={},
                    lease_owner="worker-b",
                    lease_token=1,
                    lease_expires_at=utc_now() - timedelta(seconds=120),
                ),
            ]
        )
        await session.commit()

    recovered = await scheduler.recover_interrupted()

    async with test_db_session() as session:
        live = await session.get(TaskORM, "task_live")
        dead = await session.get(TaskORM, "task_dead")
    assert recovered == ["task_dead"]
    assert live.status == "RUNNING", "startup recovery blocked a task another replica is executing"
    assert dead.status == "BLOCKED"
