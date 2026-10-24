from __future__ import annotations

import asyncio
import logging
import time

from project_model.task_models import (
    TaskStatus,
    TaskStep,
    TaskStepStatus,
)

from app.persistence.models import utc_now
from app.ports.task_unit_of_work import TaskUnitOfWorkFactory
from app.services.task_errors import ApprovalRequired, TaskBlocked, TaskCancelled
from app.services.task_execution_orchestrator import TaskExecutionOrchestrator
from app.services.task_lease_context import lease_scope, reset_lease
from app.services.task_workspace import workspace_source_snapshot

logger = logging.getLogger("app.task_runtime")

# A lease outlives three missed heartbeats, so a slow database cannot make a live worker look dead.
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20


class TaskSchedulerService:
    """Own the persisted task queue, concurrency limits and worker lifecycle."""

    def __init__(
        self,
        execution: TaskExecutionOrchestrator,
        *,
        concurrency: int = 2,
        poll_interval: float = 0.5,
        repository_scope: TaskUnitOfWorkFactory,
        runtime_instance_id: str | None = None,
    ) -> None:
        self.execution = execution
        self.repository_scope = repository_scope
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self.runtime_instance_id = runtime_instance_id
        self._scheduler: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._child_runs = execution._child_runs
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._stopping = False
        self._next_recovery_at = 0.0
        self._leases: dict[str, tuple[str, int]] = {}
        self._heartbeats: dict[str, asyncio.Task] = {}

    async def cancel_active(self, task_id: str, run_id: str | None = None) -> None:
        active = self._active.get(task_id)
        if active:
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        run_id = self._child_runs.pop(task_id, None) or run_id
        if run_id:
            try:
                from app.container import open_run_service

                async with open_run_service() as service:
                    await service.cancel_run(run_id)
            except Exception:
                logger.warning("Could not cancel child TestRun for task %s", task_id)

    async def start(self) -> None:
        if self._scheduler is None or self._scheduler.done():
            self._stopping = False
            await self.recover_interrupted()
            self._scheduler = asyncio.create_task(self._schedule_loop(), name="agent-task-scheduler")

    async def stop(self) -> None:
        self._stopping = True
        if self._scheduler:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
            self._scheduler = None
        for task_id in list(self._active):
            try:
                row, _ = await self.execution._load(task_id)
                run_id = (row.context or {}).get("run_id") if row else None
                if run_id:
                    from app.container import open_run_service

                    async with open_run_service() as service:
                        await service.cancel_run(run_id)
            except Exception:
                logger.warning("Could not stop child TestRun for interrupted task %s", task_id)
        active = list(self._active.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        for task_id in list(self._leases):
            await self._release_lease(task_id, expired=True)

    async def recover_interrupted(self) -> list[str]:
        """Never replay a possibly side-effecting browser, patch or subprocess step blindly.

        Only tasks nobody holds a live lease on are recovered: a second replica must not block work
        that the first replica is still executing. An expired or missing lease is the evidence that
        the previous owner is gone.
        """
        recovered: list[str] = []
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            for row in await repo.unfinished_stale():
                failure_reason = "Interrupted by API restart. Review the current workspace and explicitly replan."
                cancelled = row.cancel_requested_at is not None
                written = await repo.finish_fenced(
                    row.id,
                    TaskStatus.CANCELLED.value if cancelled else TaskStatus.BLOCKED.value,
                    require_no_live_lease=True,
                    failure_reason=None if cancelled else failure_reason,
                )
                if not written:
                    # Another replica claimed it between the query and the write; leave it to its owner.
                    continue
                await repo.fail_running_steps(
                    row.id,
                    "API restarted while this tool was running; inspect side effects before retrying.",
                )
                if cancelled:
                    await repo.add_event(row.id, "task.cancelled", {"via": "recovery", "recovered": True})
                else:
                    await repo.add_event(row.id, "task.blocked", {"reason": failure_reason, "recovered": True})
                recovered.append(row.id)
            await repositories.commit()
        return recovered

    async def _schedule_loop(self) -> None:
        while not self._stopping:
            try:
                async with self.repository_scope() as repositories:
                    rows = await repositories.tasks.pending(
                        limit=self.concurrency * 2,
                        runtime_instance_id=self.runtime_instance_id,
                    )
                    candidates = [row.id for row in rows if row.id not in self._active]
                for task_id in candidates:
                    if len(self._active) >= self.concurrency:
                        break
                    claimed = await self._claim(task_id)
                    if claimed:
                        task = asyncio.create_task(self._execute_task(task_id), name=f"agent-task-{task_id}")
                        self._active[task_id] = task
                        task.add_done_callback(lambda done, tid=task_id: self._active.pop(tid, None))
                now = time.monotonic()
                if now >= self._next_recovery_at:
                    try:
                        await self.recover_interrupted()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("Periodic task recovery failed")
                    self._next_recovery_at = now + max(0.05, self.poll_interval * 10)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Task scheduler iteration failed")
                await asyncio.sleep(self.poll_interval)

    async def _claim(self, task_id: str) -> bool:
        owner = self.runtime_instance_id or "single-instance"
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            token = await repo.claim_for_execution(task_id, owner=owner, lease_seconds=LEASE_SECONDS)
            if token is None:
                await repositories.rollback()
                return False
            self._leases[task_id] = (owner, token)
            lease_token = lease_scope(owner, token)
            try:
                task = await repo.get(task_id)
                assert task is not None
                task_values = {"status": TaskStatus.RUNNING.value}
                if task.started_at is None:
                    task_values["started_at"] = utc_now()
                await repo.update_task(task_id, **task_values)
                await repo.add_event(task_id, "task.started", {})
                await repo.add_event(task_id, "task.planning", {"step_count": len(await repo.steps_for_task(task_id))})
                await repositories.commit()
            finally:
                reset_lease(lease_token)
        self._start_heartbeat(task_id)
        return True

    def _start_heartbeat(self, task_id: str) -> None:
        existing = self._heartbeats.get(task_id)
        if existing is not None and not existing.done():
            return
        self._heartbeats[task_id] = asyncio.create_task(self._heartbeat(task_id), name=f"lease-{task_id}")

    async def _heartbeat(self, task_id: str) -> None:
        """Keep the lease alive while this process is the owner; stop when the task ends."""
        try:
            while not self._stopping:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                lease = self._leases.get(task_id)
                if lease is None:
                    return
                owner, token = lease
                renewed = False
                fresh = None
                for attempt in range(3):
                    try:
                        async with self.repository_scope() as repositories:
                            renewed = await repositories.tasks.renew_lease(task_id, owner, token, LEASE_SECONDS)
                            fresh = await repositories.tasks.get(task_id) if renewed else None
                            await repositories.commit()
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        if attempt == 2:
                            logger.exception("Task %s heartbeat failed after bounded retries", task_id)
                        else:
                            await asyncio.sleep(0.1 * (attempt + 1))
                if not renewed:
                    logger.warning("Task %s no longer holds its lease; cancelling active execution", task_id)
                    active = self._active.get(task_id)
                    if active is not None and not active.done():
                        active.cancel()
                        await asyncio.gather(active, return_exceptions=True)
                    return
                if fresh is not None and fresh.cancel_requested_at is not None:
                    # A cancel from another replica travels through the row; stop our own execution here
                    # so a long step cannot outlive the request.
                    active = self._active.get(task_id)
                    if active is not None and not active.done():
                        active.cancel()
        except asyncio.CancelledError:
            raise
        finally:
            self._heartbeats.pop(task_id, None)

    async def _release_lease(self, task_id: str, *, expired: bool = False) -> None:
        heartbeat = self._heartbeats.pop(task_id, None)
        if heartbeat is not None:
            heartbeat.cancel()
        lease = self._leases.pop(task_id, None)
        if lease is None:
            return
        owner, token = lease
        async with self.repository_scope() as repositories:
            if expired:
                await repositories.tasks.release_lease(task_id, owner, token)
            await repositories.commit()

    async def _execute_task(self, task_id: str) -> None:
        async with self._semaphore:
            lease = self._leases.get(task_id)
            lease_token = lease_scope(*lease) if lease else None
            worker_started = time.monotonic()
            execution_started = worker_started
            try:
                task, _ = await self.execution._load(task_id)
                if task is not None:
                    elapsed_before = max(0.0, float((task.context or {}).get("_execution_elapsed_seconds", 0)))
                    execution_started = worker_started - elapsed_before
                    await self._execute_dag(task_id, execution_started)
            except asyncio.CancelledError:
                # The API lifespan owns process-level cancellation; recover_interrupted will
                # mark the task BLOCKED on the next start if it was not user-cancelled. A user
                # cancel writes its request first, so only that case may end the task here.
                await self._finish_cancelled_if_requested(task_id)
                raise
            except Exception as error:
                try:
                    await self.execution._finish(task_id, TaskStatus.FAILED, str(error))
                except Exception:
                    logger.exception("Task %s could not be finalized after execution failed", task_id)
            finally:
                try:
                    await self._persist_execution_elapsed(task_id, time.monotonic() - execution_started)
                except Exception:
                    logger.warning("Task %s failed to persist elapsed time", task_id, exc_info=True)
                finally:
                    if lease_token is not None:
                        reset_lease(lease_token)
                    try:
                        await self._release_lease(task_id, expired=True)
                    except Exception:
                        logger.exception("Task %s lease cleanup failed", task_id)

    async def _finish_cancelled_if_requested(self, task_id: str) -> None:
        """End a task whose owner was aborted, but only when a user actually asked for it."""
        task, _ = await self.execution._load(task_id)
        if task is None or task.cancel_requested_at is None or task.status in self.execution.TERMINAL:
            return
        await self.execution._finish(task_id, TaskStatus.CANCELLED, "Cancelled by user.")

    async def _persist_execution_elapsed(self, task_id: str, elapsed: float) -> None:
        async with self.repository_scope() as repositories:
            task = await repositories.tasks.get(task_id)
            if not task:
                return
            context = task.context or {}
            await repositories.tasks.update_context(
                task_id,
                _execution_elapsed_seconds=max(
                    max(0.0, float(context.get("_execution_elapsed_seconds", 0))),
                    max(0.0, elapsed),
                ),
            )
            await repositories.commit()

    async def _execute_dag(self, task_id: str, started: float) -> None:
        while True:
            task, steps = await self.execution._load(task_id)
            if (
                not task
                or task.status in self.execution.TERMINAL
                or task.status in {TaskStatus.WAITING.value, TaskStatus.PAUSED.value}
            ):
                return
            if task.status == TaskStatus.PAUSING.value:
                await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started)
                return
            if task.cancel_requested_at is not None:
                await self.execution._finish(task_id, TaskStatus.CANCELLED, "Cancelled by user.")
                return
            if len(steps) > task.max_steps:
                await self.execution._finish(task_id, TaskStatus.FAILED, "Task step limit exceeded.")
                return
            by_key = {step.key: step for step in steps}
            pending = [step for step in steps if step.status == TaskStepStatus.PENDING.value]
            if not pending:
                if await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started):
                    return
                verification = next(
                    (step.outputs for step in reversed(steps) if "verified" in (step.outputs or {})),
                    {"all_steps_terminal": True},
                )
                await self.execution._finish(task_id, TaskStatus.COMPLETED, None, verification=verification)
                return
            # Checked after completion so one long runtime step (Quality Discovery) cannot be
            # failed retroactively for work it already finished.
            deadline = started + task.max_duration_seconds
            if time.monotonic() >= deadline:
                await self.execution._finish(
                    task_id,
                    TaskStatus.BLOCKED,
                    "Task duration limit reached; inspect active child operations before retrying.",
                )
                return

            ready: list[TaskStep] = []
            for step in pending:
                parents = [by_key.get(key) for key in step.dependencies]
                if any(parent is None for parent in parents):
                    await self.execution._finish(
                        task_id, TaskStatus.FAILED, f"Step {step.key} has an unknown dependency."
                    )
                    return
                if any(
                    parent.status in {TaskStepStatus.FAILED.value, TaskStepStatus.CANCELLED.value} for parent in parents
                ):
                    await self.execution._finish(
                        task_id, TaskStatus.FAILED, f"Dependency failed before step {step.key}."
                    )
                    return
                if all(
                    parent.status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                    for parent in parents
                ):
                    ready.append(step)
            if not ready:
                await self.execution._finish(
                    task_id, TaskStatus.FAILED, "Task graph has a dependency cycle or no runnable step."
                )
                return

            # Only explicitly marked independent steps may run concurrently. The first normal
            # ready step preserves authored workflow order; ready parallel steps form one batch.
            if ready[0].parallelizable:
                batch = [step for step in ready if step.parallelizable]
            else:
                batch = [ready[0]]
            results = await asyncio.gather(
                *(self.execution._execute_step(task, step, deadline=deadline) for step in batch), return_exceptions=True
            )
            failed = any(
                isinstance(result, (TaskBlocked, TaskCancelled))
                or isinstance(result, BaseException)
                and not isinstance(result, ApprovalRequired)
                for result in results
            )
            if not failed and await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started):
                return
            for result in results:
                if isinstance(result, ApprovalRequired):
                    return
                if isinstance(result, TaskCancelled):
                    # The user stopped the goal the executor was driving; that is a deliberate stop, not a
                    # block that needs a decision.
                    await self.execution._finish(task_id, TaskStatus.CANCELLED, str(result) or None)
                    return
                if isinstance(result, TaskBlocked):
                    await self.execution._finish(task_id, TaskStatus.BLOCKED, str(result))
                    return
                if isinstance(result, BaseException):
                    # The individual step runner already persisted its retry/failure state.
                    await self.execution._finish(task_id, TaskStatus.FAILED, str(result))
                    return

    async def _pause_at_boundary(self, task_id: str, *, elapsed_seconds: float = 0.0) -> bool:
        task, _ = await self.execution._load(task_id)
        if not task or task.status != TaskStatus.PAUSING.value:
            return False
        snapshot = workspace_source_snapshot(task.workspace_id)
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            current = await repo.get(task_id)
            if not current or current.status in self.execution.TERMINAL or current.status != TaskStatus.PAUSING.value:
                return False
            context = {
                **(current.context or {}),
                "pause_workspace_snapshot": snapshot,
                "_execution_elapsed_seconds": max(
                    max(0.0, float((current.context or {}).get("_execution_elapsed_seconds", 0))),
                    max(0.0, elapsed_seconds),
                ),
            }
            await repo.update_task(
                task_id,
                context=context,
                status=TaskStatus.PAUSED.value,
                finished_at=None,
            )
            await repo.add_event(
                task_id,
                "task.paused",
                {
                    "boundary": "after_current_step",
                    "step_id": current.current_step_id,
                    "workspace_files": len(snapshot),
                },
            )
            await repositories.commit()
        return True
