from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.persistence.models import ProjectORM
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.services.quality_discovery_models import DiscoveryRunCreate, DiscoveryStatus
from app.services.quality_discovery_service import QualityDiscoveryService
from app.services.task_errors import TaskBlocked
from project_model.task_models import TaskType

pytestmark = pytest.mark.integration


class _NoBrowser:
    async def create_session(self, **_kwargs):  # pragma: no cover - these tests never explore
        raise AssertionError("no browser session is expected")


class _CaptureTasks:
    def __init__(self, status: str = "PENDING") -> None:
        self.created: list[tuple[object, str]] = []
        self.resumed: list[str] = []
        self.status = status

    async def create(self, data, owner_id):
        self.created.append((data, owner_id))
        return SimpleNamespace(id="task-discovery", status=self.status)

    async def get(self, task_id):
        if task_id != "task-discovery":
            return None
        return SimpleNamespace(id=task_id, status=self.status)

    async def resume(self, task_id, owner_id):
        self.resumed.append(task_id)
        return SimpleNamespace(id=task_id, status="PENDING")


async def _project(session_factory, project_id: str = "project_discovery_task") -> str:
    async with session_factory() as session:
        session.add(ProjectORM(id=project_id, name="Discovery task project"))
        await session.commit()
    return project_id


async def _run_row(session_factory, project_id: str, status: str) -> str:
    async with session_factory() as session:
        row = await QualityDiscoveryRepository(session).create(
            project_id=project_id,
            requested_by="owner-1",
            mode="EXPLORE",
            start_url="https://example.test/shop",
            requirement_id=None,
            requirement_text="",
            allowed_domains=[],
        )
        await QualityDiscoveryRepository(session).update(row.id, status=status)
        await session.commit()
        return row.id


@pytest.mark.asyncio
async def test_a_discovery_run_is_owned_by_the_task_runtime(test_db_session):
    project_id = await _project(test_db_session)
    tasks = _CaptureTasks()
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser(), task_commands=tasks)

    run = await service.create(
        DiscoveryRunCreate(project_id=project_id, start_url="https://example.test/shop"),
        "owner-1",
    )

    assert len(tasks.created) == 1
    data, owner_id = tasks.created[0]
    assert data.type is TaskType.EXPLORE_PRODUCT
    assert data.project_id == project_id
    assert data.inputs == {"discovery_run_id": run.id}
    assert owner_id == "owner-1"
    assert run.result["runtime_task_id"] == "task-discovery"
    # The loop must not also start in-process, or the run would execute twice.
    assert not service._tasks


@pytest.mark.asyncio
async def test_a_stopped_run_blocks_the_runtime_task_instead_of_reporting_success(test_db_session):
    project_id = await _project(test_db_session)
    run_id = await _run_row(test_db_session, project_id, DiscoveryStatus.RUNNING.value)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser())

    async def stop_immediately(_run_id: str) -> None:
        await service._update(_run_id, status=DiscoveryStatus.STOPPED.value, error="用户停止了探索。")

    service._execute = stop_immediately

    with pytest.raises(TaskBlocked, match="STOPPED"):
        await service.execute_run(run_id)


@pytest.mark.asyncio
async def test_a_completed_run_reports_its_progress_to_the_runtime(test_db_session):
    project_id = await _project(test_db_session)
    run_id = await _run_row(test_db_session, project_id, DiscoveryStatus.RUNNING.value)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser())

    async def complete_immediately(_run_id: str) -> None:
        await service._update(_run_id, status=DiscoveryStatus.COMPLETED.value)

    service._execute = complete_immediately

    result = await service.execute_run(run_id)

    assert result["discovery_run_id"] == run_id
    assert result["status"] == DiscoveryStatus.COMPLETED.value
    assert set(result["progress"]) == {"states", "actions", "features"}
    assert run_id not in service._tasks


@pytest.mark.asyncio
async def test_a_queued_run_is_not_scheduled_twice_when_it_is_paused_and_resumed(test_db_session):
    project_id = await _project(test_db_session)
    tasks = _CaptureTasks()
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser(), task_commands=tasks)
    run = await service.create(
        DiscoveryRunCreate(project_id=project_id, start_url="https://example.test/shop"),
        "owner-1",
    )

    # Pausing a still-queued run and resuming it must not schedule a second loop: both tasks would
    # drive a browser against the same site and double every budget.
    assert (await service.pause(run.id)).status == DiscoveryStatus.PAUSED.value
    assert (await service.resume(run.id)).status == DiscoveryStatus.RUNNING.value
    assert len(tasks.created) == 1

    # A finished task no longer owns the run, so the next resume may schedule another attempt.
    tasks.status = "COMPLETED"
    await service.pause(run.id)
    await service.resume(run.id)
    assert len(tasks.created) == 2


@pytest.mark.asyncio
async def test_a_pause_issued_while_queued_survives_the_loop_starting(test_db_session):
    project_id = await _project(test_db_session)
    run_id = await _run_row(test_db_session, project_id, DiscoveryStatus.PAUSED.value)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser())
    seen: list[bool] = []

    async def observe_pause(_run_id: str) -> None:
        seen.append(service._resume_events[run_id].is_set())
        await service._update(_run_id, status=DiscoveryStatus.COMPLETED.value)

    service._execute = observe_pause

    await service.execute_run(run_id)

    assert seen == [False]


@pytest.mark.asyncio
@pytest.mark.parametrize("finished", ["COMPLETED", "BLOCKED"])
async def test_a_finished_task_no_longer_owns_its_run(test_db_session, finished):
    project_id = await _project(test_db_session)
    tasks = _CaptureTasks(status=finished)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser(), task_commands=tasks)
    run = await service.create(
        DiscoveryRunCreate(project_id=project_id, start_url="https://example.test/shop"),
        "owner-1",
    )

    # COMPLETED is the normal end; BLOCKED is what the scheduler writes after a restart, and both must
    # let the next resume schedule a fresh attempt.
    await service.pause(run.id)
    assert (await service.resume(run.id)).status == DiscoveryStatus.RUNNING.value
    assert len(tasks.created) == 2


@pytest.mark.asyncio
async def test_a_task_paused_in_the_task_centre_is_handed_back_to_the_queue(test_db_session):
    project_id = await _project(test_db_session)
    tasks = _CaptureTasks(status="PAUSED")
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser(), task_commands=tasks)
    run = await service.create(
        DiscoveryRunCreate(project_id=project_id, start_url="https://example.test/shop"),
        "owner-1",
    )

    # A paused task is never claimed again, so resuming only the run must requeue that task instead of
    # leaving the run RUNNING with no executor.
    await service.pause(run.id)
    assert (await service.resume(run.id)).status == DiscoveryStatus.RUNNING.value
    assert tasks.resumed == ["task-discovery"]
    assert len(tasks.created) == 1


@pytest.mark.asyncio
async def test_a_second_loop_cannot_drive_the_same_run(test_db_session):
    project_id = await _project(test_db_session)
    run_id = await _run_row(test_db_session, project_id, DiscoveryStatus.RUNNING.value)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser())
    owner = asyncio.ensure_future(asyncio.Event().wait())
    service._tasks[run_id] = owner
    try:
        with pytest.raises(TaskBlocked, match="Another exploration loop"):
            await service.execute_run(run_id)
    finally:
        owner.cancel()


@pytest.mark.asyncio
async def test_a_paused_run_takes_no_action_before_it_is_resumed(test_db_session):
    project_id = await _project(test_db_session)
    run_id = await _run_row(test_db_session, project_id, DiscoveryStatus.PAUSED.value)
    opened: list[str] = []

    class _RecordingBrowser:
        async def create_session(self, **_kwargs):
            opened.append("create_session")
            raise AssertionError("the loop must not open a browser while paused")

    service = QualityDiscoveryService(test_db_session, browser_runtime=_RecordingBrowser())
    service._assert_runtime_ready = lambda _config: None

    running = asyncio.ensure_future(service.execute_run(run_id))
    await asyncio.sleep(0.05)
    assert opened == []
    assert (await service.get(run_id)).status == DiscoveryStatus.PAUSED.value

    service._resume_events[run_id].set()
    with pytest.raises(TaskBlocked, match="ended FAILED"):
        await running
    assert opened == ["create_session"]


@pytest.mark.asyncio
async def test_startup_recovery_pauses_runs_a_dead_process_left_running(test_db_session):
    project_id = await _project(test_db_session)
    running = await _run_row(test_db_session, project_id, DiscoveryStatus.RUNNING.value)
    completed = await _run_row(test_db_session, project_id, DiscoveryStatus.COMPLETED.value)
    service = QualityDiscoveryService(test_db_session, browser_runtime=_NoBrowser())

    assert await service.recover_interrupted_runs() == 1

    paused = await service.get(running)
    assert paused.status == DiscoveryStatus.PAUSED.value
    assert "restarted" in (paused.error or "")
    assert (await service.get(completed)).status == DiscoveryStatus.COMPLETED.value
