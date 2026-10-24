from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.container import get_task_runtime_service
from app.persistence.models import ArtifactORM, TaskArtifactORM, TaskEvidenceORM, TaskORM, TaskStepORM, utc_now
from app.repositories.task_evidence_repo import TaskEvidenceRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.task_evidence_service import TaskEvidenceService
from app.services.task_lease_context import lease_scope, reset_lease
from app.services.task_runtime_service import TaskRuntimeService
from project_model.task_models import EvidenceType, TaskStatus, TaskType
from sqlalchemy import select

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


async def test_an_expired_lease_cannot_be_renewed(test_db_session):
    task_id = await _task(test_db_session, "task_expired_heartbeat")
    async with test_db_session() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await session.commit()
    async with test_db_session() as session:
        assert await TaskRepository(session).renew_lease(task_id, "worker-a", token or 0, 60) is False
        await session.commit()
    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
    assert row.lease_expires_at < utc_now()


async def test_expired_owner_cannot_create_artifact_file_or_record(test_db_session, tmp_path, monkeypatch):
    task_id = await _task(test_db_session, "task_expired_artifact_file")
    async with test_db_session() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await session.commit()

    artifact_dir = tmp_path / "artifacts"
    runtime_service = TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory(test_db_session))
    monkeypatch.setattr(
        "app.services.artifact_storage_service.get_config",
        lambda: SimpleNamespace(app=SimpleNamespace(artifact_storage_dir=artifact_dir)),
    )
    evidence_service = TaskEvidenceService(runtime_service.execution.execution_ports)
    task_record, _ = await runtime_service.execution._load(task_id)

    context_token = lease_scope("worker-a", token or 0)
    try:
        with pytest.raises(RuntimeError, match="lease was lost"):
            await evidence_service.create_artifact(task_record, "step", "stale.txt", "TEST", b"stale", "text/plain")
    finally:
        reset_lease(context_token)

    assert not list(artifact_dir.glob("*"))
    async with test_db_session() as session:
        assert await session.scalar(select(ArtifactORM.id)) is None
        assert await session.scalar(select(TaskArtifactORM.id).where(TaskArtifactORM.task_id == task_id)) is None


async def test_a_live_lease_owner_persists_artifact_and_task_link_atomically(test_db_session, tmp_path, monkeypatch):
    task_id = await _task(test_db_session, "task_live_artifact_file")
    async with test_db_session() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner="worker-a", lease_seconds=60)
        await session.commit()

    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setattr(
        "app.services.artifact_storage_service.get_config",
        lambda: SimpleNamespace(app=SimpleNamespace(artifact_storage_dir=artifact_dir)),
    )
    runtime_service = TaskRuntimeService(repository_scope=TaskRepositoryScopeFactory(test_db_session))
    evidence_service = TaskEvidenceService(runtime_service.execution.execution_ports)
    task_record, _ = await runtime_service.execution._load(task_id)

    context_token = lease_scope("worker-a", token or 0)
    try:
        artifact = await evidence_service.create_artifact(
            task_record, "step", "owned.txt", "TEST", b"owned", "text/plain"
        )
        assert artifact["_persisted"] is True
        async with test_db_session() as session:
            assert (
                await evidence_service.persist_step_outputs(
                    TaskEvidenceRepository(session), task_id, "step-id", {"_artifacts": [artifact]}
                )
                == []
            )
            await session.commit()
    finally:
        reset_lease(context_token)

    async with test_db_session() as session:
        stored = await session.get(ArtifactORM, artifact["artifact_id"])
        linked = await session.scalar(
            select(TaskArtifactORM).where(
                TaskArtifactORM.task_id == task_id,
                TaskArtifactORM.artifact_id == artifact["artifact_id"],
            )
        )
    assert stored is not None and Path(stored.storage_path).read_bytes() == b"owned"
    assert linked is not None and linked.kind == "TEST"


async def test_a_worker_that_lost_its_lease_cannot_write_or_emit_terminal_state(test_db_session):
    task_id = await _task(test_db_session, "task_fenced")
    async with test_db_session() as first:
        token = await TaskRepository(first).claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await first.commit()
    async with test_db_session() as second:
        await TaskRepository(second).claim_for_execution(task_id, owner="worker-b", lease_seconds=60)
        await second.commit()

    context_token = lease_scope("worker-a", token or 0)
    try:
        await runtime.execution._finish(task_id, TaskStatus.COMPLETED, "stale writer")
    finally:
        reset_lease(context_token)

    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        events = await TaskRepository(session).events_after(task_id, 0)
    assert row.status == "PLANNING", "a stale worker wrote a terminal state over the new owner"
    assert events == [], "a stale worker must not persist an event after losing its lease"


async def test_a_live_lease_owner_can_write_task_evidence(test_db_session):
    task_id = await _task(test_db_session, "task_live_evidence")
    async with test_db_session() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner="worker-a", lease_seconds=60)
        await session.commit()

    context_token = lease_scope("worker-a", token or 0)
    try:
        async with test_db_session() as session:
            repository = TaskEvidenceRepository(session)
            evidence = await repository.add_evidence(
                task_id=task_id,
                type=EvidenceType.CONSOLE_LOG.value,
                source="test",
                summary="owned evidence",
            )
            event = await repository.add_event(task_id, "evidence.created", {"evidence_id": evidence.id})
            await session.commit()
    finally:
        reset_lease(context_token)

    assert evidence.id
    assert event.id


@pytest.mark.parametrize("write_kind", ["event", "evidence", "artifact"])
async def test_an_expired_lease_cannot_write_task_records(test_db_session, write_kind):
    task_id = await _task(test_db_session, f"task_expired_{write_kind}")
    async with test_db_session() as session:
        repo = TaskRepository(session)
        token = await repo.claim_for_execution(task_id, owner="worker-a", lease_seconds=-1)
        await session.commit()

    context_token = lease_scope("worker-a", token or 0)
    try:
        async with test_db_session() as session:
            repo = TaskEvidenceRepository(session)
            with pytest.raises(RuntimeError, match="lease was lost"):
                if write_kind == "event":
                    await repo.add_event(task_id, "stale.event", {})
                elif write_kind == "evidence":
                    await repo.add_evidence(
                        task_id=task_id,
                        type=EvidenceType.CONSOLE_LOG.value,
                        source="test",
                        summary="stale evidence",
                    )
                else:
                    await repo.add_artifact(
                        task_id=task_id,
                        artifact_id="missing-artifact",
                        name="stale.bin",
                        kind="TEST",
                    )
            await session.rollback()
    finally:
        reset_lease(context_token)

    async with test_db_session() as session:
        assert await TaskRepository(session).events_after(task_id, 0) == []
        assert await session.scalar(select(TaskEvidenceORM.id).where(TaskEvidenceORM.task_id == task_id)) is None
        assert await session.scalar(select(TaskArtifactORM.id).where(TaskArtifactORM.task_id == task_id)) is None


async def test_workflow_resume_preserves_its_saved_plan_and_identity(test_db_session):
    task_id = await _task(test_db_session, "task_workflow_resume")
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        task.type = TaskType.WORKFLOW_EXECUTION.value
        task.context = {"workflow_node_keys_by_kind": {"collector": "collect_custom"}, "keep": "same"}
        task.workflow_execution_id = "execution-1"
        task.workflow_definition_id = "definition-1"
        task.workflow_version_id = "version-row-1"
        task.workflow_version = 3
        task.workflow_checksum = "a" * 64
        task.max_retries = 0
        task.max_replans = 0
        session.add(
            TaskStepORM(
                id="workflow-step-1",
                task_id=task_id,
                position=0,
                key="collect_custom",
                name="Collect failure",
                tool="failure.collect",
                status="PENDING",
                inputs={"failure_id": "failure-1"},
            )
        )
        await session.commit()

    commands = get_task_runtime_service().commands
    paused = await commands.pause(task_id, "owner")
    assert paused is not None and paused.status == "PAUSED"
    resumed = await commands.resume(task_id, "owner")

    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        steps = await TaskRepository(session).steps_for_task(task_id)
    assert resumed is not None and resumed.status == "PENDING"
    assert row.workflow_execution_id == "execution-1"
    assert row.workflow_version_id == "version-row-1" and row.workflow_version == 3
    assert row.workflow_checksum == "a" * 64
    assert row.context == {"workflow_node_keys_by_kind": {"collector": "collect_custom"}, "keep": "same"}
    assert [(step.key, step.tool, step.status) for step in steps] == [("collect_custom", "failure.collect", "PENDING")]
    assert resumed.events[-1].type == "task.resumed"
    assert resumed.events[-1].payload["plan_refreshed"] is False


async def test_heartbeat_database_errors_retry_a_bounded_number_of_times(test_db_session, monkeypatch):
    import asyncio

    from app.services import task_scheduler_service

    task_id = await _task(test_db_session, "task_heartbeat_retry")
    instance = type(scheduler)(
        runtime.execution,
        repository_scope=TaskRepositoryScopeFactory(test_db_session),
        runtime_instance_id="heartbeat-retry",
    )
    instance._leases[task_id] = ("heartbeat-retry", 1)
    calls = 0

    class BrokenTasks:
        async def renew_lease(self, *_args):
            nonlocal calls
            calls += 1
            raise RuntimeError("temporary database outage")

    class Scope:
        async def __aenter__(self):
            return SimpleNamespace(tasks=BrokenTasks(), commit=self.commit)

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            return None

    instance.repository_scope = Scope
    monkeypatch.setattr(task_scheduler_service, "HEARTBEAT_SECONDS", 0)
    original_sleep = asyncio.sleep

    async def yield_now(_delay):
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", yield_now)
    await instance._heartbeat(task_id)
    assert calls == 3
    assert task_id not in instance._heartbeats


@pytest.mark.parametrize("renewal_result", [False, "database_error"])
async def test_heartbeat_stops_active_execution_before_next_side_effect(test_db_session, monkeypatch, renewal_result):
    import asyncio

    from app.services import task_scheduler_service

    task_id = await _task(test_db_session, f"task_heartbeat_fences_{renewal_result}")
    instance = type(scheduler)(
        runtime.execution,
        repository_scope=TaskRepositoryScopeFactory(test_db_session),
        runtime_instance_id=f"heartbeat-fences-{renewal_result}",
    )
    instance._leases[task_id] = (f"heartbeat-fences-{renewal_result}", 1)
    entered = asyncio.Event()
    allow_side_effect = asyncio.Event()
    side_effects: list[str] = []

    async def active_execution():
        entered.set()
        try:
            await allow_side_effect.wait()
            side_effects.append("executed")
        except asyncio.CancelledError:
            raise

    active = asyncio.create_task(active_execution())
    instance._active[task_id] = active
    await entered.wait()

    class Tasks:
        async def renew_lease(self, *_args):
            if renewal_result == "database_error":
                raise RuntimeError("database unavailable")
            return renewal_result

        async def get(self, *_args):
            raise AssertionError("task state must not be read after a lost lease")

    class Scope:
        async def __aenter__(self):
            return SimpleNamespace(tasks=Tasks(), commit=self.commit)

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            return None

    instance.repository_scope = Scope
    monkeypatch.setattr(task_scheduler_service, "HEARTBEAT_SECONDS", 0)
    original_sleep = asyncio.sleep

    async def yield_now(_delay):
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", yield_now)
    await instance._heartbeat(task_id)
    allow_side_effect.set()
    await asyncio.gather(active, return_exceptions=True)

    assert active.cancelled()
    assert side_effects == []
    assert task_id not in instance._heartbeats


async def test_scheduler_recovers_a_lease_that_expires_after_start(test_db_session):
    import asyncio

    from app.services.task_scheduler_service import TaskSchedulerService

    task_id = await _task(test_db_session, "task_expires_after_start")
    async with test_db_session() as session:
        await TaskRepository(session).claim_for_execution(task_id, owner="other-replica", lease_seconds=60)
        await session.commit()

    instance = TaskSchedulerService(
        runtime.execution,
        concurrency=1,
        poll_interval=0.01,
        repository_scope=TaskRepositoryScopeFactory(test_db_session),
        runtime_instance_id="recovery-test",
    )
    recovered_again = asyncio.Event()
    original_recover = instance.recover_interrupted
    recovery_calls = 0

    async def track_recovery():
        nonlocal recovery_calls
        recovery_calls += 1
        recovered = await original_recover()
        if recovery_calls > 1 and task_id in recovered:
            recovered_again.set()
        return recovered

    instance.recover_interrupted = track_recovery
    await instance.start()
    try:
        async with test_db_session() as session:
            row = await session.get(TaskORM, task_id)
            row.lease_expires_at = utc_now() - timedelta(seconds=1)
            await session.commit()
        await asyncio.wait_for(recovered_again.wait(), timeout=1)
        async with test_db_session() as session:
            row = await session.get(TaskORM, task_id)
            assert row.status == "BLOCKED"
    finally:
        await instance.stop()


async def test_initial_task_load_failure_releases_local_lease_and_heartbeat(test_db_session, monkeypatch):
    import asyncio

    task_id = await _task(test_db_session, "task_initial_load_failure")
    async with test_db_session() as session:
        token = await TaskRepository(session).claim_for_execution(task_id, owner="worker-local", lease_seconds=60)
        await session.commit()
    instance = type(scheduler)(
        runtime.execution,
        concurrency=1,
        repository_scope=TaskRepositoryScopeFactory(test_db_session),
        runtime_instance_id="worker-local",
    )
    instance._leases[task_id] = ("worker-local", token or 0)
    heartbeat = asyncio.create_task(asyncio.sleep(60))
    instance._heartbeats[task_id] = heartbeat

    async def fail_load(_task_id):
        raise RuntimeError("initial load failed")

    monkeypatch.setattr(runtime.execution, "_load", fail_load)
    await instance._execute_task(task_id)

    assert task_id not in instance._leases
    assert task_id not in instance._heartbeats
    assert heartbeat.cancelled() or heartbeat.done()
    async with test_db_session() as session:
        row = await session.get(TaskORM, task_id)
        assert row.lease_owner is None


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
