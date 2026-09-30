from __future__ import annotations

import ast
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    DecisionOption,
    DecisionRequest,
    FrameworkType,
    RunStatus,
    TestCaseCreate,
    TestRunCreate,
)
from project_model.task_models import (
    EvidenceType,
    Task,
    TaskApprovalRequest,
    TaskCreate,
    TaskDetail,
    TaskStatus,
    TaskStep,
    TaskStepStatus,
    TaskType,
)
from qa_core.ai.models import AICompletionRequest, CodeAssistantResponse
from qa_core.ai.registry import AIProviderRegistry
from qa_core.ai.trace import make_trace_event
from qa_core.failure.classifier import FailureClassifier
from sqlalchemy import select, update

from app.persistence.database import async_session_factory
from app.persistence.models import (
    FailureRecordORM,
    ProjectORM,
    TaskORM,
    TaskStepORM,
    TestCaseORM,
    TestRunORM,
    WorkspaceORM,
    utc_now,
)
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.browser_proxy import browser_proxy_options
from app.services.decision_service import DecisionService
from app.services.task_workflows import build_plan
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger("app.task_runtime")


class TaskBlocked(RuntimeError):
    """The goal cannot continue safely without a user decision or unavailable dependency."""


class ApprovalRequired(Exception):
    pass


class TaskRuntimeService:
    """Persisted, bounded DAG executor. Existing runs, browser, AI and Jev remain its tools."""

    TERMINAL = {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.CANCELLED.value,
    }

    def __init__(self, concurrency: int = 2, poll_interval: float = 0.5) -> None:
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self._scheduler: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._child_runs: dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._stopping = False

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
                row, _ = await self._load(task_id)
                run_id = (row.context or {}).get("run_id") if row else None
                if run_id:
                    from app.api.runs import open_run_service

                    async with open_run_service() as service:
                        await service.cancel_run(run_id)
            except Exception:
                logger.warning("Could not stop child TestRun for interrupted task %s", task_id)
        active = list(self._active.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    async def recover_interrupted(self) -> list[str]:
        """Never replay a possibly side-effecting browser, patch or subprocess step blindly."""
        recovered: list[str] = []
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            for row in await repo.unfinished():
                steps = await repo.steps_for_task(row.id)
                for step in steps:
                    if step.status == TaskStepStatus.RUNNING.value:
                        step.status = TaskStepStatus.FAILED.value
                        step.error = "API restarted while this tool was running; inspect side effects before retrying."
                        step.finished_at = utc_now()
                row.status = TaskStatus.BLOCKED.value
                row.failure_reason = "Interrupted by API restart. Review the current workspace and explicitly replan."
                row.finished_at = utc_now()
                row.updated_at = utc_now()
                await repo.add_event(row.id, "task.blocked", {"reason": row.failure_reason, "recovered": True})
                recovered.append(row.id)
            await session.commit()
        return recovered

    async def create(self, data: TaskCreate, owner_id: str) -> Task:
        workspace_required = {
            TaskType.CREATE_TEST,
            TaskType.FIX_FAILURE,
            TaskType.OPTIMIZE_TEST,
            TaskType.REVIEW_TEST,
            TaskType.RUN_REGRESSION,
        }
        project_required = {TaskType.CREATE_TEST, TaskType.RUN_REGRESSION}
        if data.type in workspace_required and not data.workspace_id:
            raise ValueError(f"{data.type.value} requires workspace_id")
        if data.type in project_required and not data.project_id:
            raise ValueError(f"{data.type.value} requires project_id")
        if data.type in {TaskType.CREATE_TEST, TaskType.EXPLORE_PAGE}:
            page_url = str(data.inputs.get("url", "")).strip()
            parsed_url = urlparse(page_url)
            if (
                parsed_url.scheme not in {"http", "https"}
                or not parsed_url.hostname
                or parsed_url.username
                or parsed_url.password
            ):
                raise ValueError(f"{data.type.value} requires an http(s) URL without embedded credentials")
        if data.workspace_id:
            async with async_session_factory() as session:
                workspace_row = await session.get(WorkspaceORM, data.workspace_id)
                if workspace_row is None:
                    workspace_row = (
                        await session.execute(select(WorkspaceORM).where(WorkspaceORM.project_id == data.workspace_id))
                    ).scalar_one_or_none()
                if workspace_row is None:
                    raise ValueError("Workspace not found")
                if data.project_id and workspace_row.project_id != data.project_id:
                    raise ValueError("Workspace does not belong to the selected project")
                project_id = data.project_id or workspace_row.project_id
                if await session.get(ProjectORM, project_id) is None:
                    raise ValueError("Project not found")
            # All existing execution/file APIs use the project ID as the filesystem workspace key.
            # WorkspaceORM has a separate row ID, so normalize it at the boundary.
            data.workspace_id = project_id
            workspace = WorkspaceService().get_workspace_dir(project_id)
            if not workspace.exists():
                raise ValueError("Workspace directory is not available")
            if data.project_id is None:
                data.project_id = project_id
        elif data.project_id:
            async with async_session_factory() as session:
                if await session.get(ProjectORM, data.project_id) is None:
                    raise ValueError("Project not found")
        plan = build_plan(data.type)
        if len(plan) > data.max_steps:
            raise ValueError(f"Task plan has {len(plan)} steps, exceeding max_steps={data.max_steps}")
        steps = [
            {
                "key": item.key,
                "name": item.name,
                "tool": item.tool,
                "status": TaskStepStatus.PENDING.value,
                "dependencies": item.depends_on,
                "condition": item.when,
                "inputs": item.inputs,
                "outputs": {},
                "evidence_ids": [],
                "retry_count": 0,
                "max_retries": item.max_retries,
                "parallelizable": item.parallelizable,
            }
            for item in plan
        ]
        values = {
            "type": data.type.value,
            "goal": data.goal,
            "status": TaskStatus.PENDING.value,
            "owner_id": owner_id,
            "project_id": data.project_id,
            "workspace_id": data.workspace_id,
            "inputs": data.inputs,
            "context": {"ai_calls": 0, "tool_calls": 0},
            "verification": {},
            "retry_count": 0,
            "replan_count": 0,
            "max_steps": data.max_steps,
            "max_retries": data.max_retries,
            "max_replans": data.max_replans,
            "max_ai_calls": data.max_ai_calls,
            "max_duration_seconds": data.max_duration_seconds,
            "current_step_id": None,
            "failure_reason": None,
        }
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.create(values, steps)
            await session.commit()
            return Task(**repo.task_values(row))

    async def get(self, task_id: str, owner_id: str | None = None) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task_id, owner_id)
            return await repo.get_detail(row) if row else None

    async def list(self, owner_id: str, project_id: str | None = None, limit: int = 50) -> list[Task]:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            rows = await repo.list(owner_id, project_id=project_id, limit=limit)
            return [
                Task(
                    **repo.task_values(row),
                    plan=[TaskStep.model_validate(step, from_attributes=True) for step in await repo.get_steps(row.id)],
                )
                for row in rows
            ]

    async def approve(self, task_id: str, owner_id: str, request: TaskApprovalRequest) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id, owner_id)
            if not task or task.status != TaskStatus.WAITING.value or not task.current_step_id:
                return None
            step = await session.get(TaskStepORM, task.current_step_id)
            if not step or step.status != TaskStepStatus.WAITING_FOR_APPROVAL.value:
                return None
            if request.approved:
                step.status = TaskStepStatus.COMPLETED.value
                step.outputs = {"approved": True, "comment": request.comment}
                task.status = TaskStatus.PENDING.value
                task.failure_reason = None
                event_type = "decision.created"
            else:
                step.status = TaskStepStatus.SKIPPED.value
                step.outputs = {"approved": False, "comment": request.comment}
                task.status = TaskStatus.BLOCKED.value
                task.failure_reason = "User rejected the proposed workspace change."
                task.finished_at = utc_now()
                event_type = "task.blocked"
            step.finished_at = utc_now()
            task.updated_at = utc_now()
            await repo.add_event(
                task.id, event_type, {"step_id": step.id, "approved": request.approved, "comment": request.comment}
            )
            await session.commit()
        return await self.get(task_id, owner_id)

    async def cancel(self, task_id: str, owner_id: str) -> TaskStatus | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id, owner_id)
            if not task or task.status in self.TERMINAL:
                return None
            task.status = TaskStatus.CANCELLED.value
            task.finished_at = utc_now()
            task.updated_at = utc_now()
            if task.current_step_id:
                step = await session.get(TaskStepORM, task.current_step_id)
                if step and step.status in {
                    TaskStepStatus.RUNNING.value,
                    TaskStepStatus.WAITING_FOR_APPROVAL.value,
                }:
                    step.status = TaskStepStatus.CANCELLED.value
                    step.error = "Cancelled by user."
                    step.finished_at = utc_now()
            await repo.add_event(task.id, "task.cancelled", {})
            await session.commit()
        active = self._active.get(task_id)
        if active:
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
        run_id = self._child_runs.pop(task_id, None) or (task.context or {}).get("run_id")
        if run_id:
            try:
                from app.api.runs import open_run_service

                async with open_run_service() as service:
                    await service.cancel_run(run_id)
            except Exception:
                logger.warning("Could not cancel child TestRun for task %s", task_id)
        return TaskStatus.CANCELLED

    async def replan(self, task_id: str, owner_id: str, instructions: str) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id, owner_id)
            if not task or task.status not in {TaskStatus.BLOCKED.value, TaskStatus.FAILED.value}:
                return None
            if task.replan_count >= task.max_replans:
                raise ValueError("Task replan limit reached")
            rows = await repo.steps_for_task(task.id)
            unsafe_completed = [
                step.key
                for step in rows
                if step.status == TaskStepStatus.COMPLETED.value
                and step.tool in {"source.write_generated", "source.apply_repair"}
            ]
            if unsafe_completed:
                raise ValueError(
                    "This task already changed workspace source; inspect the diff and create a new task to continue safely."
                )
            task.replan_count += 1
            task.inputs = {**task.inputs, "replan_instructions": instructions[:4000]}
            task.status = TaskStatus.REPLANNING.value
            task.failure_reason = None
            task.finished_at = None
            task.current_step_id = None
            for step in rows:
                if step.status == TaskStepStatus.FAILED.value:
                    step.status = TaskStepStatus.PENDING.value
                    step.error = None
                    step.outputs = {}
                    step.finished_at = None
                    step.started_at = None
                    step.duration_ms = 0
                    step.retry_count = 0
            await repo.add_event(
                task.id, "task.replanning", {"instructions": instructions[:4000], "replan_count": task.replan_count}
            )
            await session.commit()
        return await self.get(task_id, owner_id)

    async def _schedule_loop(self) -> None:
        while not self._stopping:
            try:
                async with async_session_factory() as session:
                    rows = await TaskRepository(session).pending(limit=self.concurrency * 2)
                    candidates = [row.id for row in rows if row.id not in self._active]
                for task_id in candidates:
                    if len(self._active) >= self.concurrency:
                        break
                    claimed = await self._claim(task_id)
                    if claimed:
                        task = asyncio.create_task(self._execute_task(task_id), name=f"agent-task-{task_id}")
                        self._active[task_id] = task
                        task.add_done_callback(lambda done, tid=task_id: self._active.pop(tid, None))
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Task scheduler iteration failed")
                await asyncio.sleep(self.poll_interval)

    async def _claim(self, task_id: str) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                update(TaskORM)
                .where(
                    TaskORM.id == task_id, TaskORM.status.in_([TaskStatus.PENDING.value, TaskStatus.REPLANNING.value])
                )
                .values(status=TaskStatus.PLANNING.value, updated_at=utc_now())
            )
            if result.rowcount != 1:
                await session.rollback()
                return False
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            assert task is not None
            if task.started_at is None:
                task.started_at = utc_now()
            await repo.add_event(task_id, "task.started", {})
            await repo.add_event(task_id, "task.planning", {"step_count": len(await repo.steps_for_task(task_id))})
            task.status = TaskStatus.RUNNING.value
            await session.commit()
            return True

    async def _execute_task(self, task_id: str) -> None:
        async with self._semaphore:
            started = time.monotonic()
            try:
                await self._execute_dag(task_id, started)
            except asyncio.CancelledError:
                # The API lifespan owns process-level cancellation; recover_interrupted will
                # mark the task BLOCKED on the next start if it was not user-cancelled.
                raise
            except Exception as error:
                await self._finish(task_id, TaskStatus.FAILED, str(error))

    async def _execute_dag(self, task_id: str, started: float) -> None:
        while True:
            task, steps = await self._load(task_id)
            if not task or task.status in self.TERMINAL or task.status == TaskStatus.WAITING.value:
                return
            if time.monotonic() - started > task.max_duration_seconds:
                await self._finish(
                    task_id,
                    TaskStatus.BLOCKED,
                    "Task duration limit reached; inspect active child operations before retrying.",
                )
                return
            if len(steps) > task.max_steps:
                await self._finish(task_id, TaskStatus.FAILED, "Task step limit exceeded.")
                return
            by_key = {step.key: step for step in steps}
            pending = [step for step in steps if step.status == TaskStepStatus.PENDING.value]
            if not pending:
                verification = next(
                    (step.outputs for step in reversed(steps) if "verified" in (step.outputs or {})),
                    {"all_steps_terminal": True},
                )
                await self._finish(task_id, TaskStatus.COMPLETED, None, verification=verification)
                return

            ready: list[TaskStepORM] = []
            for step in pending:
                parents = [by_key.get(key) for key in step.dependencies]
                if any(parent is None for parent in parents):
                    await self._finish(task_id, TaskStatus.FAILED, f"Step {step.key} has an unknown dependency.")
                    return
                if any(
                    parent.status in {TaskStepStatus.FAILED.value, TaskStepStatus.CANCELLED.value} for parent in parents
                ):
                    await self._finish(task_id, TaskStatus.FAILED, f"Dependency failed before step {step.key}.")
                    return
                if all(
                    parent.status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                    for parent in parents
                ):
                    ready.append(step)
            if not ready:
                await self._finish(task_id, TaskStatus.FAILED, "Task graph has a dependency cycle or no runnable step.")
                return

            # Only explicitly marked independent steps may run concurrently. The first normal
            # ready step preserves authored workflow order; ready parallel steps form one batch.
            if ready[0].parallelizable:
                batch = [step for step in ready if step.parallelizable]
            else:
                batch = [ready[0]]
            results = await asyncio.gather(*(self._execute_step(task, step) for step in batch), return_exceptions=True)
            for result in results:
                if isinstance(result, ApprovalRequired):
                    return
                if isinstance(result, TaskBlocked):
                    await self._finish(task_id, TaskStatus.BLOCKED, str(result))
                    return
                if isinstance(result, BaseException):
                    # The individual step runner already persisted its retry/failure state.
                    await self._finish(task_id, TaskStatus.FAILED, str(result))
                    return

    async def _load(self, task_id: str) -> tuple[TaskORM | None, list[TaskStepORM]]:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            return task, await repo.steps_for_task(task_id) if task else []

    async def _execute_step(self, task: TaskORM, step: TaskStepORM) -> dict[str, Any] | ApprovalRequired | TaskBlocked:
        condition_key = (step.condition or {}).get("input_exists")
        if condition_key and not task.inputs.get(condition_key):
            await self._complete_step(
                task.id, step.id, {"skipped": True, "reason": f"input '{condition_key}' was not supplied"}, skipped=True
            )
            return {"skipped": True}

        started = time.perf_counter()
        while True:
            async with async_session_factory() as session:
                repo = TaskRepository(session)
                fresh = await repo.get(task.id)
                current = await session.get(TaskStepORM, step.id)
                if not fresh or fresh.status == TaskStatus.CANCELLED.value:
                    return TaskBlocked("Task was cancelled")
                if current is None:
                    return TaskBlocked("Task step disappeared")
                current.status = TaskStepStatus.RUNNING.value
                current.started_at = current.started_at or utc_now()
                fresh.current_step_id = current.id
                fresh.status = (
                    TaskStatus.VERIFYING.value
                    if step.tool
                    in {
                        "tests.verify",
                        "tests.compare",
                        "browser.verify",
                    }
                    else TaskStatus.RUNNING.value
                )
                fresh.context = {**fresh.context, "tool_calls": int(fresh.context.get("tool_calls", 0)) + 1}
                await repo.add_event(
                    fresh.id,
                    "step.started",
                    {"step_id": current.id, "key": current.key, "tool": current.tool, "input": current.inputs},
                )
                await session.commit()

            try:
                outputs = await self._run_tool(task.id, step.key, step.tool)
            except ApprovalRequired:
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    await repo.update_step(step.id, status=TaskStepStatus.WAITING_FOR_APPROVAL.value)
                    current_task = await repo.update_task(
                        task.id, status=TaskStatus.WAITING.value, current_step_id=step.id
                    )
                    await repo.add_event(
                        task.id,
                        "step.progress",
                        {
                            "step_id": step.id,
                            "status": "WAITING_FOR_APPROVAL",
                            "diff": (current_task.context or {}).get("pending_change_summary", "")
                            if current_task
                            else "",
                        },
                    )
                    await session.commit()
                return ApprovalRequired()
            except TaskBlocked as error:
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    current = await session.get(TaskStepORM, step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        current.status = TaskStepStatus.FAILED.value
                        current.error = str(error)[:4000]
                        current.finished_at = utc_now()
                        await repo.add_event(
                            task.id, "step.failed", {"step_id": step.id, "error": str(error)[:1000], "blocked": True}
                        )
                        await session.commit()
                return error
            except Exception as error:
                elapsed = (time.perf_counter() - started) * 1000
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    current = await session.get(TaskStepORM, step.id)
                    fresh = await repo.get(task.id)
                    if current is None or fresh is None:
                        return error
                    current.retry_count += 1
                    current.error = str(error)[:4000]
                    current.duration_ms = elapsed
                    await repo.add_event(
                        task.id,
                        "step.failed",
                        {"step_id": step.id, "error": str(error)[:1000], "retry": current.retry_count},
                    )
                    if (
                        current.retry_count <= min(current.max_retries, fresh.max_retries)
                        and fresh.retry_count < fresh.max_retries
                    ):
                        fresh.retry_count += 1
                        current.status = TaskStepStatus.PENDING.value
                        fresh.status = TaskStatus.RETRYING.value
                        await repo.add_event(
                            task.id, "task.retrying", {"step_id": step.id, "retry_count": fresh.retry_count}
                        )
                        await session.commit()
                        await asyncio.sleep(min(0.5 * (2 ** (current.retry_count - 1)), 3.0))
                        continue
                    current.status = TaskStepStatus.FAILED.value
                    current.finished_at = utc_now()
                    await session.commit()
                return error

            await self._complete_step(task.id, step.id, outputs, duration_ms=(time.perf_counter() - started) * 1000)
            return outputs

    async def _complete_step(
        self, task_id: str, step_id: str, outputs: dict[str, Any], *, skipped: bool = False, duration_ms: float = 0.0
    ) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await session.get(TaskStepORM, step_id)
            if not row:
                return
            evidence_ids: list[str] = []
            for item in outputs.pop("_evidence", []):
                evidence = await repo.add_evidence(
                    task_id=task_id,
                    step_id=step_id,
                    type=item["type"],
                    source=item["source"],
                    summary=item.get("summary", ""),
                    content=item.get("content"),
                    artifact_id=item.get("artifact_id"),
                    metadata_json=item.get("metadata", {}),
                )
                evidence_ids.append(evidence.id)
                await repo.add_event(
                    task_id, "evidence.created", {"evidence_id": evidence.id, "type": evidence.type, "step_id": step_id}
                )
            for item in outputs.pop("_artifacts", []):
                await repo.add_artifact(task_id=task_id, step_id=step_id, **item)
                await repo.add_event(
                    task_id,
                    "artifact.created",
                    {"artifact_id": item["artifact_id"], "name": item["name"], "step_id": step_id},
                )
            decision = outputs.pop("_decision", None)
            if decision:
                stored = await repo.add_decision(task_id=task_id, step_id=step_id, **decision)
                await repo.add_event(
                    task_id,
                    "decision.created",
                    {
                        "decision_id": stored.id,
                        "name": stored.name,
                        "choice": stored.choice,
                        "provider": stored.provider,
                        "confidence": stored.confidence,
                    },
                )
            await repo.update_step(
                step_id,
                status=TaskStepStatus.SKIPPED.value if skipped else TaskStepStatus.COMPLETED.value,
                outputs=outputs,
                evidence_ids=evidence_ids,
                duration_ms=duration_ms,
                finished_at=utc_now(),
                error=None,
            )
            await repo.add_event(
                task_id,
                "step.completed",
                {"step_id": step_id, "outputs": outputs, "skipped": skipped, "duration_ms": duration_ms},
            )
            await session.commit()

    async def _finish(
        self, task_id: str, status: TaskStatus, reason: str | None, verification: dict[str, Any] | None = None
    ) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task_id)
            if not row or row.status in self.TERMINAL:
                return
            row.status = status.value
            row.failure_reason = reason
            row.finished_at = utc_now()
            row.updated_at = utc_now()
            if verification is not None:
                row.verification = verification
            event = (
                "task.completed"
                if status == TaskStatus.COMPLETED
                else (
                    "task.cancelled"
                    if status == TaskStatus.CANCELLED
                    else "task.blocked"
                    if status == TaskStatus.BLOCKED
                    else "task.failed"
                )
            )
            await repo.add_event(task_id, event, {"reason": reason, "verification": row.verification})
            await session.commit()

    async def _run_tool(self, task_id: str, step_key: str, tool: str) -> dict[str, Any]:
        task, steps = await self._load(task_id)
        if not task:
            raise TaskBlocked("Task not found")
        outputs = {step.key: step.outputs for step in steps if step.status == TaskStepStatus.COMPLETED.value}
        dispatch = {
            "browser.inspect": self._browser_inspect,
            "browser.act": self._browser_act,
            "browser.verify": self._browser_verify,
            "decision.select_candidate": self._decision_select,
            "tests.generate": self._generate_test,
            "source.validate_generated": self._validate_generated,
            "task.request_approval": self._request_approval,
            "source.write_generated": self._write_generated,
            "tests.run_generated": self._run_generated,
            "tests.resolve": self._resolve_tests,
            "tests.run_regression": self._run_regression,
            "tests.register_case": self._register_test_case,
            "failure.collect": self._collect_failure,
            "failure.classify": self._classify_failure,
            "failure.diagnose": self._diagnose_failure,
            "source.inspect_failure": self._inspect_failure_source,
            "failure.prepare_repair": self._prepare_repair,
            "source.apply_repair": self._apply_repair,
            "source.validate_workspace": self._validate_workspace,
            "tests.run_target": self._run_target,
            "failure.classify_run": self._classify_run,
            "tests.verify": self._verify_tests,
            "source.inspect": self._inspect_source,
            "source.review": self._review_source,
            "source.generate_refactor": self._generate_refactor,
            "tests.compare": self._compare_test,
            "source.review_report": self._review_report,
        }
        handler = dispatch.get(tool)
        if not handler:
            raise TaskBlocked(f"No runtime tool is registered for '{tool}'.")
        return await handler(task, outputs)

    @staticmethod
    def _input(task: TaskORM, key: str, default: Any = None) -> Any:
        return (task.inputs or {}).get(key, default)

    async def _recorder_storage_state(self, task: TaskORM) -> dict[str, Any] | None:
        """Reuse the initiating recorder's cookies and local storage without persisting secrets in a task."""
        session_id = self._input(task, "recorder_session_id")
        if not session_id:
            return None
        from app.services.recorder_service import recorder_service

        session = await recorder_service.get(str(session_id), task.owner_id)
        if not session or session.project_id != task.project_id:
            return None
        return await session.context.storage_state()

    async def _artifact(
        self, task: TaskORM, step_key: str, name: str, kind: str, content: bytes, content_type: str
    ) -> dict[str, Any]:
        saved = await ArtifactStorageService().save_artifact(name, content, content_type)
        return {"artifact_id": saved.artifact_id, "name": name, "kind": kind}

    async def _reserve_ai_call(self, task_id: str) -> bool:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                return False
            used = int((task.context or {}).get("ai_calls", 0))
            if used >= task.max_ai_calls:
                return False
            task.context = {**task.context, "ai_calls": used + 1}
            await session.commit()
            return True

    async def _evidence(
        self,
        task: TaskORM,
        step_key: str,
        evidence_type: EvidenceType,
        source: str,
        summary: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "type": evidence_type.value,
            "source": source,
            "summary": summary,
            "content": content[:24000] if content else None,
            "metadata": metadata or {},
            "artifact_id": artifact_id,
        }

    async def _browser_inspect(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        url = str(self._input(task, "url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TaskBlocked("Browser exploration requires an http(s) URL without embedded credentials.")
        from playwright.async_api import async_playwright

        recorder_state = await self._recorder_storage_state(task)

        async with async_playwright() as playwright:
            proxy = browser_proxy_options()
            browser = await playwright.chromium.launch(headless=True, **({"proxy": proxy} if proxy else {}))
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 800}, storage_state=recorder_state)
                page = await context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                title = await page.title()
                aria = await page.locator("body").aria_snapshot()
                candidates = await page.locator(
                    "button,a[href],input:not([type=hidden]),textarea,select,[role=button],[role=link]"
                ).evaluate_all("""els => els.slice(0,100).map((el,index) => {
                  const text=(el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().replace(/\\s+/g,' ').slice(0,120);
                  const tag=el.tagName.toLowerCase(), type=(el.getAttribute('type') || '').toLowerCase();
                  const href=el.getAttribute('href');
                  const risky=/delete|remove|purchase|pay|submit|logout|sign out|unsubscribe/i.test(text) || type==='submit';
                  return {index,tag,role:el.getAttribute('role') || (tag==='a'?'link':tag==='button'?'button':tag==='input'?'textbox':tag),name:text,href,type,safe:!risky};
                })""")
                screenshot = await page.screenshot(full_page=True, type="png")
                artifact = await self._artifact(task, "inspect", "page.png", "SCREENSHOT", screenshot, "image/png")
                body_text = (await page.locator("body").inner_text())[:12000]
                return {
                    "url": page.url,
                    "title": title,
                    "http_status": response.status if response else None,
                    "accessibility_tree": aria[:24000],
                    "candidates": candidates,
                    "screenshot_artifact_id": artifact["artifact_id"],
                    "_artifacts": [artifact],
                    "_evidence": [
                        await self._evidence(
                            task,
                            "inspect",
                            EvidenceType.ACCESSIBILITY_TREE,
                            "playwright.aria_snapshot",
                            f"Page {title!r} at {page.url}; {len(candidates)} interactive candidates.",
                            aria,
                            {"url": page.url, "title": title, "http_status": response.status if response else None,
                             "recorder_state_applied": recorder_state is not None},
                        ),
                        await self._evidence(
                            task,
                            "inspect",
                            EvidenceType.DOM_SNAPSHOT,
                            "playwright.body.inner_text",
                            "Visible page text snapshot.",
                            body_text,
                            {"candidate_count": len(candidates)},
                        ),
                        await self._evidence(
                            task,
                            "inspect",
                            EvidenceType.RUNTIME_METADATA,
                            "playwright.navigation",
                            "Browser navigation completed.",
                            None,
                            {
                                "requested_url": url,
                                "final_url": page.url,
                                "http_status": response.status if response else None,
                            },
                        ),
                    ],
                }
            finally:
                await browser.close()

    async def _decision_select(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        observed = outputs.get("inspect", {})
        candidates = [item for item in observed.get("candidates", []) if item.get("safe")]
        trace_run_id = uuid4().hex
        await self._record_ai_trace(
            task.id,
            make_trace_event(trace_run_id, "run.started", stage="decision", title="Browser decision started",
                             metadata={"feature": "browser_exploration", "decision": "explore_next_action"}),
        )
        await self._record_ai_trace(
            task.id,
            make_trace_event(trace_run_id, "evidence.collected", stage="evidence", title="Page scan complete",
                             message=f"{len(candidates)} safe action candidate(s)",
                             metadata={"candidate_count": len(candidates)}),
        )
        await self._record_ai_trace(
            task.id,
            make_trace_event(trace_run_id, "decision.started", stage="decision", title="Selecting next action",
                             metadata={"candidate_count": len(candidates)}),
        )
        if not candidates:
            await self._record_ai_trace(
                task.id,
                make_trace_event(trace_run_id, "decision.completed", stage="decision", title="Local policy selected",
                                 message="No safe interactive action was observed.",
                                 metadata={"provider": "local-policy", "candidate_count": 0, "fallback_used": False}),
            )
            await self._record_ai_trace(
                task.id,
                make_trace_event(trace_run_id, "run.completed", stage="decision", title="Browser decision complete"),
            )
            return {
                "choice": "none",
                "candidate": None,
                "provider": "local-policy",
                "confidence": 1.0,
                "rationale": "No safe interactive candidate was observed.",
                "_decision": {
                    "name": "explore_next_action",
                    "provider": "local-policy",
                    "choice": "none",
                    "confidence": 1.0,
                    "rationale": "No safe interactive candidate was observed.",
                    "escalated": False,
                },
            }
        options = [
            DecisionOption(key=str(item["index"]), description=f"{item['role']} {item['name']}"[:1000])
            for item in candidates
        ]
        request = DecisionRequest(
            name="explore_next_action",
            state={
                "goal": task.goal,
                "url": observed.get("url"),
                "title": observed.get("title"),
                "candidates": candidates,
            },
            options=options,
            instructions="Choose a safe, relevant page control to inspect. Never select destructive, purchase, submit, or sign-out actions.",
        )
        can_call_provider = await self._reserve_ai_call(task.id)
        result = await DecisionService().choose(request, run_id=trace_run_id) if can_call_provider else None
        if result:
            async with async_session_factory() as session:
                repo = TaskRepository(session)
                fresh = await repo.get(task.id)
                if fresh:
                    is_provider_call = result.provider != "fallback" and not result.fallback_used
                    fresh.context = {
                        **fresh.context,
                        "jev_calls": int(fresh.context.get("jev_calls", 0)) + int(is_provider_call),
                    }
                    await repo.add_event(
                        task.id,
                        "step.progress",
                        {
                            "type": "decision.call",
                            "provider": result.provider,
                            "fallback_used": result.fallback_used,
                            "confidence": result.confidence,
                            "reason": result.reason,
                        },
                    )
                    await session.commit()
        selected = next((item for item in candidates if result and str(item["index"]) == str(result.choice)), None)
        # Jev abstention, low confidence, or invalid choice escalates to a conservative local rule.
        escalated = selected is None or (result is not None and (result.confidence or 0) < 0.6)
        if escalated:
            selected = candidates[0]
            choice = str(selected["index"])
            provider = "local-policy"
            rationale = "Jev was unavailable, abstained, exceeded the task AI-call budget, or confidence was below threshold; selected the first observed safe candidate."
            confidence = 0.5
        else:
            choice = str(selected["index"])
            provider = result.provider if result else "local-policy"
            rationale = (
                (result.reason or "Jev selected an observed candidate.")
                if result
                else "Task AI-call budget exhausted; applied local safe-candidate policy."
            )
            confidence = (result.confidence or 0.0) if result else 0.5
        decision = {
            "name": "explore_next_action",
            "provider": provider,
            "choice": choice,
            "confidence": confidence,
            "rationale": rationale,
            "escalated": escalated,
        }
        await self._record_ai_trace(
            task.id,
            make_trace_event(
                trace_run_id,
                "decision.completed",
                stage="decision",
                title="Jev decision complete" if not escalated else "Local policy fallback",
                message=(
                    f"Selected {selected.get('role', 'control')} {selected.get('name', '')}".strip()
                    if selected
                    else "No candidate selected."
                ),
                metadata={
                    "provider": provider,
                    "candidate_count": len(candidates),
                    "selected_action": {
                        "role": selected.get("role"),
                        "name": selected.get("name"),
                    } if selected else None,
                    "choice": choice,
                    "confidence": confidence,
                    "fallback_used": escalated or bool(result and result.fallback_used),
                    "fallback_reason": result.reason if result and result.fallback_used else None,
                },
            ),
        )
        await self._record_ai_trace(
            task.id,
            make_trace_event(trace_run_id, "run.completed", stage="decision", title="Browser decision complete"),
        )
        return {
            "choice": choice,
            "candidate": selected,
            "provider": provider,
            "confidence": confidence,
            "rationale": rationale,
            "_decision": decision,
            "_evidence": [
                await self._evidence(
                    task,
                    "decide",
                    EvidenceType.LOCATOR_CANDIDATES,
                    "browser.inspect + decision.choose",
                    f"Selected candidate {choice} from {len(candidates)} safe observed controls.",
                    json.dumps(candidates, ensure_ascii=False),
                    {"provider": provider, "escalated": escalated},
                )
            ],
        }

    async def _record_ai_trace(self, task_id: str, event) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            await repo.add_event(task_id, "ai.trace", event.model_dump(mode="json"))
            await session.commit()

    async def _browser_act(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        selected = outputs.get("decide", {}).get("candidate")
        inspected = outputs.get("inspect", {})
        if not selected:
            return {"action": "skipped", "reason": "No safe candidate was available."}
        if not selected.get("safe"):
            raise TaskBlocked("The selected browser action is not classified as safe.")
        from playwright.async_api import async_playwright

        recorder_state = await self._recorder_storage_state(task)

        async with async_playwright() as playwright:
            proxy = browser_proxy_options()
            browser = await playwright.chromium.launch(headless=True, **({"proxy": proxy} if proxy else {}))
            try:
                context = await browser.new_context(storage_state=recorder_state)
                page = await context.new_page()
                await page.goto(inspected["url"], wait_until="domcontentloaded", timeout=20000)
                role, name = selected.get("role"), selected.get("name")
                if role in {"button", "link"} and name:
                    await page.get_by_role(role, name=name, exact=True).first.click(timeout=5000)
                elif selected.get("tag") == "a" and selected.get("href"):
                    await page.goto(
                        urljoin(inspected["url"], selected["href"]), wait_until="domcontentloaded", timeout=15000
                    )
                else:
                    return {
                        "action": "skipped",
                        "reason": "Candidate could not be replayed with an accessible locator.",
                    }
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                title = await page.title()
                text = (await page.locator("body").inner_text())[:6000]
                return {
                    "action": "clicked",
                    "candidate": selected,
                    "url": page.url,
                    "title": title,
                    "_evidence": [
                        await self._evidence(
                            task,
                            "act",
                            EvidenceType.RUNTIME_METADATA,
                            "playwright.safe_click",
                            f"Clicked {selected.get('role')} {selected.get('name')!r}; observed {page.url}.",
                            text,
                            {"from_url": inspected["url"], "to_url": page.url, "title": title},
                        )
                    ],
                }
            finally:
                await browser.close()

    async def _browser_verify(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        before = outputs.get("inspect", {})
        after = outputs.get("act", {})
        verified = bool(before.get("title") and after.get("action") in {"clicked", "skipped"})
        return {
            "verified": verified,
            "kind": "browser_exploration",
            "initial_url": before.get("url"),
            "initial_title": before.get("title"),
            "action_result": after,
            "observations": 2,
            "result": "COMPLETED" if verified else "INCOMPLETE",
        }

    async def _inspect_source(self, task: TaskORM, outputs: dict[str, Any], path: str | None = None) -> dict[str, Any]:
        file_path = path or str(self._input(task, "file_path", ""))
        if not file_path:
            raise TaskBlocked("This task requires a workspace-relative file_path.")
        service = WorkspaceService()
        content = await service.read_file(task.workspace_id or "", file_path)
        if len(content) > 60000:
            raise TaskBlocked("Source file exceeds the review context limit (60,000 characters).")
        tree = ast.parse(content, filename=file_path)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return {
            "file_path": file_path,
            "source": content,
            "functions": functions,
            "_evidence": [
                await self._evidence(
                    task,
                    "inspect",
                    EvidenceType.SOURCE_CODE,
                    "workspace.read_file",
                    f"Read {file_path} ({len(content)} characters; {len(functions)} functions).",
                    content,
                    {"file_path": file_path, "functions": functions},
                )
            ],
        }

    async def _review_source(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        source_info = outputs.get("inspect") or outputs.get("inspect_source") or outputs.get("inspect_failure", {})
        source = source_info.get("source", "")
        path = source_info.get("file_path", self._input(task, "file_path", ""))
        if not source:
            raise TaskBlocked("Source review requires a completed source inspection step.")
        tree = ast.parse(source, filename=path or "source.py")
        findings: list[dict[str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True:
                findings.append(
                    {
                        "severity": "HIGH",
                        "code": "ASSERT_ALWAYS_TRUE",
                        "line": str(node.lineno),
                        "message": "Assertion always passes.",
                    }
                )
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name == "sleep":
                    findings.append(
                        {
                            "severity": "MEDIUM",
                            "code": "FIXED_SLEEP",
                            "line": str(node.lineno),
                            "message": "Fixed sleeps increase test flakiness; wait for a specific condition.",
                        }
                    )
                if (
                    name == "locator"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    selector = node.args[0].value
                    if selector.startswith("//") or selector.startswith("xpath="):
                        findings.append(
                            {
                                "severity": "MEDIUM",
                                "code": "FRAGILE_XPATH",
                                "line": str(node.lineno),
                                "message": "XPath locator may be structurally fragile.",
                            }
                        )
        tests = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not tests:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "NO_TEST_FUNCTION",
                    "line": "1",
                    "message": "No pytest test function was found.",
                }
            )
        result = {
            "file_path": path,
            "findings": findings,
            "test_functions": [test.name for test in tests],
            "locators": sum(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "locator"
                for node in ast.walk(tree)
            ),
            "waits": sum(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"wait_for", "wait_for_timeout", "wait_for_selector"}
                for node in ast.walk(tree)
            ),
            "assertions": sum(
                isinstance(node, ast.Assert)
                or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "assert")
                for node in ast.walk(tree)
            ),
        }
        result["_evidence"] = [
            await self._evidence(
                task,
                "review",
                EvidenceType.ANALYSIS,
                "python.ast",
                f"Static review found {len(findings)} issue(s) in {path}.",
                json.dumps(result, ensure_ascii=False),
                result,
            )
        ]
        return result

    async def _review_report(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        review = outputs.get("review", {})
        browser = outputs.get("browser", {})
        findings = review.get("findings", [])
        return {
            "file_path": review.get("file_path"),
            "findings": findings,
            "finding_count": len(findings),
            "metrics": review.get("metrics", {}),
            "browser_observation": browser or None,
            "evidence_backed": bool(review.get("findings") is not None),
        }

    async def _call_code_ai(self, task: TaskORM, prompt: str) -> CodeAssistantResponse:
        if not await self._reserve_ai_call(task.id):
            raise TaskBlocked("Task AI-call budget exhausted.")
        replan_instructions = self._input(task, "replan_instructions", "")
        provider = AIProviderRegistry.get_provider()
        response = await provider.complete(
            AICompletionRequest(
                prompt=(f"Replan instructions: {replan_instructions}\n\n{prompt}" if replan_instructions else prompt),
                system_instruction="You are a QA code agent. Use only supplied source and browser evidence. Return structured code and never claim to have executed it.",
                response_schema=CodeAssistantResponse,
                prompt_id="code_assistant",
            )
        )
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            fresh = await repo.get(task.id)
            if fresh:
                await repo.add_event(
                    task.id,
                    "step.progress",
                    {
                        "type": "ai.call",
                        "provider": response.provider,
                        "model": response.model,
                        "fallback_used": response.fallback_used,
                        "duration_ms": response.duration_ms,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
                await session.commit()
        if response.fallback_used or response.provider == "fake":
            raise TaskBlocked(
                "The configured AI provider is unavailable; refusing to use an offline fake response for code changes."
            )
        if not response.structured_data:
            raise TaskBlocked("AI returned no structured code proposal.")
        result = CodeAssistantResponse.model_validate(response.structured_data)
        if not result.suggested_code:
            raise TaskBlocked("AI did not return executable source code.")
        return result

    async def _generate_test(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        recorded_steps = self._input(task, "recorded_steps")
        default_name = str(self._input(task, "test_name", "test_goal_flow"))
        file_path = str(self._input(task, "file_path", f"tests/{default_name}.py"))
        if recorded_steps:
            from app.services.recorder_service import RecorderGenerateRequest, RecorderStep, generate_python_case

            request = RecorderGenerateRequest(
                case_name=str(self._input(task, "case_name", task.goal[:120])),
                file_path=file_path,
                test_name=default_name,
                steps=[RecorderStep.model_validate(step) for step in recorded_steps],
            )
            code = generate_python_case(request)
            source = {"suggested_code": code, "target_file": file_path, "action_type": "generated_from_recording"}
        else:
            page = outputs.get("inspect", {})
            prompt = (
                "Create one complete pytest Playwright test for this QA goal. Use only the observed page details, "
                "goal, requirement and supplied acceptance criteria. Do not invent selectors or APIs. "
                "Return the complete Python test file in suggested_code and a workspace-relative tests/*.py target_file.\n"
                f"Goal: {task.goal}\nRequirement: {self._input(task, 'requirement', '')}\n"
                f"Acceptance criteria: {json.dumps(self._input(task, 'acceptance_criteria', []), ensure_ascii=False)}\n"
                f"Observed page: {json.dumps({k: page.get(k) for k in ('url', 'title', 'accessibility_tree', 'candidates')}, ensure_ascii=False)[:18000]}"
            )
            source = (await self._call_code_ai(task, prompt)).model_dump()
            file_path = source.get("target_file") or file_path
        code = str(source.get("suggested_code", ""))
        self._validate_python_test(code, file_path)
        artifact = await self._artifact(
            task, "generate", Path(file_path).name, "GENERATED_TEST", code.encode("utf-8"), "text/x-python"
        )
        return {
            "target_file": file_path,
            "suggested_code": code,
            "action_type": source.get("action_type", "ai_generated"),
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self._evidence(
                    task,
                    "generate",
                    EvidenceType.SOURCE_CODE,
                    "recorder.generate" if recorded_steps else "ai.code_assistant",
                    f"Generated test source for {task.goal!r}.",
                    code,
                    {"target_file": file_path, "provider": "recorder" if recorded_steps else "openai-compatible"},
                    artifact["artifact_id"],
                )
            ],
        }

    @staticmethod
    def _validate_python_test(code: str, file_path: str) -> None:
        path = Path(file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.suffix != ".py"
            or not file_path.replace("\\", "/").startswith("tests/")
        ):
            raise TaskBlocked("Generated test path must stay under the workspace tests/ directory.")
        tree = ast.parse(code, filename=file_path)
        test_functions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not test_functions:
            raise TaskBlocked("Generated source contains no top-level pytest test function.")
        forbidden_imports = {
            "subprocess",
            "socket",
            "ctypes",
            "winreg",
            "sys",
            "pathlib",
            "shutil",
            "tempfile",
            "importlib",
            "multiprocessing",
            "threading",
            "http",
            "requests",
            "httpx",
            "ftplib",
            "telnetlib",
            "ssl",
            "builtins",
        }
        allowed_environment_variables = {
            "PLAYWRIGHT_CHANNEL",
            "BROWSER_PROXY_URL",
            "HTTPS_PROXY",
            "https_proxy",
            "HTTP_PROXY",
            "http_proxy",
            "BROWSER_PROXY_BYPASS",
            "NO_PROXY",
            "no_proxy",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "urllib" for alias in node.names):
                if any(alias.name != "urllib.parse" for alias in node.names):
                    raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "urllib":
                safe_url_parser = (
                    node.level == 0
                    and node.module == "urllib.parse"
                    and all(alias.name in {"unquote", "urlsplit"} and alias.asname is None for alias in node.names)
                )
                if not safe_url_parser:
                    raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] in forbidden_imports for alias in node.names
            ):
                raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.Import) and any(
                alias.name != "os" for alias in node.names if alias.name.split(".")[0] == "os"
            ):
                raise TaskBlocked("Generated test may use os.getenv only; refusing other operating-system imports.")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in forbidden_imports:
                raise TaskBlocked("Generated test imports a process/network/system-control module; refusing execution.")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "os":
                raise TaskBlocked("Generated test may use os.getenv only; refusing other operating-system imports.")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in {
                    "eval",
                    "exec",
                    "compile",
                    "open",
                    "__import__",
                    "breakpoint",
                    "input",
                    "getattr",
                    "setattr",
                    "delattr",
                    "vars",
                    "globals",
                    "locals",
                }
            ):
                raise TaskBlocked(
                    "Generated test uses a prohibited dynamic-code or system-access operation; refusing execution."
                )
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id
                in {
                    "__builtins__",
                    "globals",
                    "locals",
                }
            ):
                raise TaskBlocked("Generated test accesses Python internals; refusing execution.")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr != "getenv"
            ):
                raise TaskBlocked("Generated test may only read approved browser environment settings.")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            ):
                args = node.args
                if (
                    node.func.attr != "getenv"
                    or not args
                    or not isinstance(args[0], ast.Constant)
                    or args[0].value not in allowed_environment_variables
                ):
                    raise TaskBlocked("Generated test may only read approved browser environment settings.")

    async def _validate_generated(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        source = outputs.get("generate") or outputs.get("refactor") or outputs.get("repair", {})
        code, file_path = source.get("suggested_code", ""), source.get("target_file", source.get("file_path", ""))
        self._validate_python_test(code, file_path)
        return {
            "valid": True,
            "file_path": file_path,
            "line_count": len(code.splitlines()),
            "_evidence": [
                await self._evidence(
                    task,
                    "validate",
                    EvidenceType.ANALYSIS,
                    "ast.parse + task source policy",
                    f"{file_path} parses and passed static generated-code policy checks.",
                    json.dumps({"file_path": file_path, "line_count": len(code.splitlines())}),
                    {"valid": True},
                )
            ],
        }

    async def _request_approval(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        change = outputs.get("generate") or outputs.get("refactor") or outputs.get("repair", {})
        summary = {
            "file_path": change.get("target_file", change.get("file_path")),
            "change_kind": task.type,
            "preview": str(change.get("suggested_code", change.get("new_code", "")))[:12000],
        }
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task.id)
            if row:
                row.context = {**row.context, "pending_change_summary": summary}
                await repo.add_event(task.id, "step.progress", {"type": "approval.requested", **summary})
                await session.commit()
        raise ApprovalRequired()

    async def _write_generated(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        change = outputs.get("generate") or outputs.get("refactor")
        if not change:
            raise TaskBlocked("No approved generated source is available.")
        await WorkspaceService().write_file(task.workspace_id or "", change["target_file"], change["suggested_code"])
        return {
            "written": True,
            "file_path": change["target_file"],
            "characters": len(change["suggested_code"]),
            "_evidence": [
                await self._evidence(
                    task,
                    "write",
                    EvidenceType.SOURCE_CODE,
                    "workspace.write_file",
                    f"Approved source written to {change['target_file']}.",
                    change["suggested_code"],
                    {"approved": True, "file_path": change["target_file"]},
                )
            ],
        }

    async def _generate_refactor(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        current = outputs.get("inspect", {})
        path, source = current.get("file_path"), current.get("source", "")
        review = outputs.get("review", {})
        supplied_code = self._input(task, "proposed_code")
        if supplied_code:
            updated = str(supplied_code)
            proposal_source = "user-provided-refactor"
        else:
            result = await self._call_code_ai(
                task,
                "Propose a focused refactor for this test file. Preserve test intent and public fixtures. "
                "Address only evidence-backed review findings. Return the complete replacement Python test module.\n"
                f"Goal: {task.goal}\nFindings: {json.dumps(review.get('findings', []), ensure_ascii=False)}\n"
                f"Path: {path}\nCurrent source:\n{source}",
            )
            updated = result.suggested_code or ""
            proposal_source = "ai.code_assistant"
        self._validate_python_test(updated, path)
        artifact = await self._artifact(
            task, "refactor", Path(path).name, "PATCH_PROPOSAL", updated.encode(), "text/x-python"
        )
        return {
            "target_file": path,
            "suggested_code": updated,
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self._evidence(
                    task,
                    "refactor",
                    EvidenceType.SOURCE_CODE,
                    proposal_source,
                    "Proposed full-file refactor, not yet applied.",
                    updated,
                    {"based_on_findings": review.get("findings", []), "proposal_source": proposal_source},
                    artifact["artifact_id"],
                )
            ],
        }

    async def _inspect_failure_source(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        failure = outputs.get("collect", {})
        path = failure.get("test_nodeid", "").split("::", 1)[0] or str(self._input(task, "file_path", ""))
        return await self._inspect_source(task, outputs, path)

    async def _collect_failure(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        failure_id = str(self._input(task, "failure_id", ""))
        if not failure_id:
            raise TaskBlocked("FixFailureTask requires failure_id.")
        async with async_session_factory() as session:
            query = select(FailureRecordORM).where(FailureRecordORM.id == failure_id)
            if task.project_id:
                query = query.join(TestRunORM, TestRunORM.id == FailureRecordORM.run_id).where(
                    TestRunORM.project_id == task.project_id
                )
            failure = (await session.execute(query)).scalar_one_or_none()
            if failure is None:
                raise TaskBlocked("Failure record was not found.")
            result = {
                "id": failure.id,
                "test_nodeid": failure.test_nodeid,
                "classification": failure.classification,
                "exception_type": failure.exception_type,
                "error_message": failure.error_message,
                "stack_trace": failure.stack_trace[-12000:],
                "failing_locator": failure.failing_locator,
                "screenshot_path": failure.screenshot_path,
                "trace_path": failure.trace_path,
                "dom_snapshot_path": failure.dom_snapshot_path,
                "repair_proposal": failure.repair_proposal,
            }
        evidence = [
            await self._evidence(
                task,
                "collect",
                EvidenceType.PYTEST_TRACEBACK,
                "failure_records + test_executions",
                f"Collected {result['exception_type']} for {result['test_nodeid']}.",
                result["stack_trace"],
                {"failure_id": failure_id, "stored_classification": result["classification"]},
            )
        ]
        if result["screenshot_path"]:
            evidence.append(
                await self._evidence(
                    task,
                    "collect",
                    EvidenceType.SCREENSHOT,
                    "failure_records",
                    "Screenshot path captured by the run.",
                    None,
                    {"path": result["screenshot_path"]},
                )
            )
        if result["trace_path"]:
            evidence.append(
                await self._evidence(
                    task,
                    "collect",
                    EvidenceType.PLAYWRIGHT_TRACE,
                    "failure_records",
                    "Playwright trace path captured by the run.",
                    None,
                    {"path": result["trace_path"]},
                )
            )
        result["_evidence"] = evidence
        return result

    async def _classify_failure(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        failure = outputs.get("collect", {})
        category, explanation, locator = FailureClassifier.classify(
            failure.get("error_message", ""), failure.get("stack_trace", "")
        )
        return {
            "classification": category.value,
            "root_cause": explanation,
            "failing_locator": locator or failure.get("failing_locator"),
            "evidence": [failure.get("error_message", ""), *failure.get("stack_trace", "").splitlines()[-8:]],
            "_evidence": [
                await self._evidence(
                    task,
                    "classify",
                    EvidenceType.ANALYSIS,
                    "FailureClassifier",
                    f"Rule-based classification: {category.value}.",
                    json.dumps(
                        {"error_message": failure.get("error_message"), "classification": category.value},
                        ensure_ascii=False,
                    ),
                    {"confidence": "heuristic", "locator_observed": bool(locator)},
                )
            ],
        }

    async def _diagnose_failure(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

        failure = outputs.get("collect", {})
        rules = outputs.get("classify", {})
        if not await self._reserve_ai_call(task.id):
            result = {
                "classification": rules.get("classification", "UNKNOWN"),
                "root_cause": rules.get(
                    "root_cause", "Task AI-call budget exhausted; no model diagnosis was performed."
                ),
                "evidence": rules.get("evidence", []),
                "hypotheses": [],
                "recommended_actions": [
                    "Review the captured traceback and inspected source before proposing a change."
                ],
                "confidence": 0.0,
                "provider": "FailureClassifier",
                "fallback_used": True,
            }
            return {
                **result,
                "_evidence": [
                    await self._evidence(
                        task,
                        "diagnose",
                        EvidenceType.ANALYSIS,
                        "FailureClassifier",
                        "AI-call budget exhausted; returned the observed rule-based diagnosis.",
                        json.dumps(result, ensure_ascii=False),
                        {"ai_call_skipped": True},
                    )
                ],
            }
        orchestrator = ProductionQAOrchestrator()
        analysis = await orchestrator.diagnose_failure_ai(
            error_message=failure.get("error_message", ""),
            stack_trace=failure.get("stack_trace", ""),
            test_nodeid=failure.get("test_nodeid", ""),
            failing_locator=failure.get("failing_locator"),
        )
        completion = orchestrator.last_completion
        ai_fallback = (not completion) or completion.fallback_used or completion.provider.lower() == "fake"
        # Treat direct traceback classification as the evidence boundary. AI can enrich the
        # explanation, but cannot overwrite a clearly observed assertion/timeout category. If
        # the provider fell back to a local/fake completion, report the rule explanation instead
        # of presenting fallback prose as an AI root-cause finding.
        classification = rules.get("classification", "UNKNOWN")
        result = {
            "classification": classification,
            "root_cause": rules.get("root_cause") if ai_fallback else analysis.root_cause,
            "evidence": analysis.evidence,
            "hypotheses": analysis.hypotheses,
            "recommended_actions": analysis.recommended_actions,
            "confidence": analysis.confidence,
            "provider": "FailureClassifier" if ai_fallback else completion.provider,
            "fallback_used": ai_fallback,
        }
        return {
            **result,
            "_evidence": [
                await self._evidence(
                    task,
                    "diagnose",
                    EvidenceType.ANALYSIS,
                    result["provider"],
                    f"Root cause analysis for evidence-backed category {classification}.",
                    json.dumps(result, ensure_ascii=False),
                    {"fallback_used": result["fallback_used"]},
                )
            ],
        }

    async def _prepare_repair(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        diagnosis = outputs.get("diagnose", {})
        failure = outputs.get("collect", {})
        source_info = outputs.get("inspect", {})
        path, source = source_info.get("file_path"), source_info.get("source", "")
        proposed = str(self._input(task, "proposed_text", "") or self._input(task, "proposed_locator", "")).strip()
        old_locator = str(
            failure.get("failing_locator")
            or outputs.get("classify", {}).get("failing_locator")
            or self._input(task, "old_text", "")
            or self._input(task, "old_locator", "")
        ).strip()
        stored_proposal = failure.get("repair_proposal") or {}
        proposed = proposed or str(stored_proposal.get("proposed_locator", "")).strip()
        old_locator = old_locator or str(stored_proposal.get("old_locator", "")).strip()

        if proposed and old_locator and old_locator in source:
            updated = source.replace(old_locator, proposed, 1)
        else:
            if (
                diagnosis.get("classification") == "LOCATOR_CHANGED"
                and not failure.get("dom_snapshot_path")
                and not self._input(task, "url")
            ):
                raise TaskBlocked(
                    "Locator repair needs a current DOM/browser observation or a user-supplied proposed_locator; no source was changed."
                )
            result = await self._call_code_ai(
                task,
                "Repair the failing test based on the exact failure evidence and inspected source. "
                "Keep the change minimal. Return the complete replacement test module in suggested_code; "
                "do not claim a repair if the evidence is insufficient.\n"
                f"Goal: {task.goal}\nClassification: {diagnosis.get('classification')}\n"
                f"Failure: {failure.get('error_message')}\nTraceback:\n{failure.get('stack_trace')}\n"
                f"Source path: {path}\nSource:\n{source}\n"
                f"Browser evidence: {outputs.get('browser', {}).get('accessibility_tree', '')[:8000]}",
            )
            updated = result.suggested_code or ""
        self._validate_python_test(updated, path)
        if updated == source:
            raise TaskBlocked("The proposed repair does not change the inspected source.")
        artifact = await self._artifact(
            task, "repair", Path(path).name, "PATCH_PROPOSAL", updated.encode(), "text/x-python"
        )
        return {
            "file_path": path,
            "target_file": path,
            "suggested_code": updated,
            "old_code": source,
            "classification": diagnosis.get("classification"),
            "artifact_id": artifact["artifact_id"],
            "_artifacts": [artifact],
            "_evidence": [
                await self._evidence(
                    task,
                    "repair",
                    EvidenceType.GIT_DIFF,
                    "task.repair.proposal",
                    f"Proposed a reviewed replacement for {path}; it has not been applied.",
                    updated,
                    {"base_source_length": len(source), "classification": diagnosis.get("classification")},
                    artifact["artifact_id"],
                )
            ],
        }

    async def _apply_repair(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        proposal = outputs.get("repair", {})
        if not proposal.get("suggested_code") or not proposal.get("file_path"):
            raise TaskBlocked("No repair proposal is available to apply.")
        if not self._approval_granted(outputs):
            raise TaskBlocked("Repair cannot be applied without an explicit approval step.")
        await WorkspaceService().write_file(task.workspace_id or "", proposal["file_path"], proposal["suggested_code"])
        return {
            "written": True,
            "file_path": proposal["file_path"],
            "characters": len(proposal["suggested_code"]),
            "_evidence": [
                await self._evidence(
                    task,
                    "apply",
                    EvidenceType.SOURCE_CODE,
                    "workspace.write_file",
                    f"User-approved repair applied to {proposal['file_path']}.",
                    proposal["suggested_code"],
                    {"approved": True, "file_path": proposal["file_path"]},
                )
            ],
        }

    @staticmethod
    def _approval_granted(outputs: dict[str, Any]) -> bool:
        approval = outputs.get("approval", {})
        return approval.get("approved") is True

    async def _validate_workspace(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        report = await WorkspaceService().validate_workspace(task.workspace_id or "")
        summary = {"valid": report.valid, "issues": [issue.model_dump(mode="json") for issue in report.issues[:100]]}
        if not report.valid:
            raise TaskBlocked(
                f"Workspace validation failed with {len(report.issues)} issue(s); inspect evidence before another edit."
            )
        return {
            **summary,
            "_evidence": [
                await self._evidence(
                    task,
                    "validate",
                    EvidenceType.ANALYSIS,
                    "workspace.validate",
                    "Workspace syntax and collection validation passed.",
                    json.dumps(summary, ensure_ascii=False),
                    {"valid": report.valid},
                )
            ],
        }

    async def _resolve_tests(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        requested = self._input(task, "nodeids", [])
        if isinstance(requested, str):
            requested = [line.strip() for line in requested.splitlines() if line.strip()]
        if not requested:
            report = await WorkspaceService().collect_tests(task.workspace_id or "")
            requested = [item.nodeid for item in report.tests]
        if not requested:
            raise TaskBlocked("No pytest node IDs were supplied or collected from the workspace.")
        if len(requested) > 100:
            raise TaskBlocked("Regression scope exceeds the 100-test safety limit.")
        return {
            "nodeids": requested,
            "total": len(requested),
            "_evidence": [
                await self._evidence(
                    task,
                    "resolve",
                    EvidenceType.RUNTIME_METADATA,
                    "workspace.collect_tests",
                    f"Resolved {len(requested)} pytest node ID(s).",
                    "\n".join(requested),
                    {"nodeids": requested},
                )
            ],
        }

    async def _run_generated(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        generated = outputs.get("generate", {})
        code = generated.get("suggested_code", "")
        tree = ast.parse(code)
        tests = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if not tests:
            raise TaskBlocked("Generated test has no pytest test function.")
        nodeids = [f"{generated['target_file']}::{name}" for name in tests]
        return await self._execute_pytest(task, nodeids)

    async def _register_test_case(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        """Publish a verified generated test into the existing Test Case catalog."""
        generated = outputs.get("generate", {})
        run = outputs.get("run", {})
        if not task.project_id or not task.workspace_id or run.get("status") != RunStatus.PASSED.value:
            raise TaskBlocked("Only a verified generated test can be registered as a Test Case.")
        nodeids = run.get("nodeids") or []
        if not nodeids or not generated.get("target_file"):
            raise TaskBlocked("Generated test has no bindable pytest node ID or file.")
        recorded_steps = self._input(task, "recorded_steps", []) or []
        title = str(self._input(task, "case_name", task.goal))[:250]
        async with async_session_factory() as session:
            existing = (await session.execute(select(TestCaseORM).where(
                TestCaseORM.project_id == task.project_id,
                TestCaseORM.external_system == "AGENT_TASK",
                TestCaseORM.external_case_id == task.id,
            ))).scalar_one_or_none()
            if existing is None:
                existing = await TestCaseRepository(session).create(TestCaseCreate(
                    project_id=task.project_id,
                    title=title,
                    steps=[str(step.get("description", "")) for step in recorded_steps if isinstance(step, dict) and step.get("description")],
                    expected_result=str(self._input(task, "requirement", ""))[:2000],
                    automation_status=AutomationStatus.AUTOMATED,
                    tags=["ai-generated"],
                    external_system="AGENT_TASK",
                    external_case_id=task.id,
                ))
            await AutomationBindingRepository(session).create_or_update(AutomationBindingCreate(
                test_case_id=existing.id,
                workspace_id=task.workspace_id,
                nodeid=str(nodeids[0]),
                file_path=str(generated["target_file"]),
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.ACTIVE,
            ))
            await session.commit()
        return {"test_case_id": existing.id, "file_path": generated["target_file"], "nodeid": nodeids[0]}

    async def _run_target(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        nodeids = self._input(task, "nodeids", [])
        if isinstance(nodeids, str):
            nodeids = [item.strip() for item in nodeids.splitlines() if item.strip()]
        if not nodeids:
            failure = outputs.get("collect", {})
            nodeid = failure.get("test_nodeid") or self._input(task, "test_nodeid")
            if nodeid:
                nodeids = [nodeid]
        if not nodeids:
            raise TaskBlocked("Targeted verification requires nodeids or failure_id.")
        return await self._execute_pytest(task, nodeids[:100])

    async def _run_regression(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        nodeids = self._input(task, "regression_nodeids", []) or self._input(task, "nodeids", [])
        if not nodeids and task.type == TaskType.RUN_REGRESSION.value:
            nodeids = outputs.get("resolve", {}).get("nodeids", [])
        if isinstance(nodeids, str):
            nodeids = [item.strip() for item in nodeids.splitlines() if item.strip()]
        if not nodeids:
            raise TaskBlocked("Regression node IDs were not resolved.")
        return await self._execute_pytest(task, nodeids[:100])

    async def _execute_pytest(self, task: TaskORM, nodeids: list[str]) -> dict[str, Any]:
        if not task.project_id or not task.workspace_id:
            raise TaskBlocked("Test execution requires project_id and workspace_id.")
        from app.api.runs import open_run_service

        environment = dict(self._input(task, "environment", {}) or {})
        region = self._input(task, "region")
        if region:
            environment.setdefault("QA_REGION", str(region))
        run_data = TestRunCreate(
            project_id=task.project_id,
            workspace_id=task.workspace_id,
            nodeids=nodeids,
            browser=str(self._input(task, "browser", "chromium")),
            markers=self._input(task, "markers", []),
            runner_type=str(self._input(task, "runner_type", "LOCAL")),
            runner_profile_id=self._input(task, "runner_profile_id"),
            environment=environment,
            requested_by=task.owner_id,
        )
        async with open_run_service() as service:
            create_task = asyncio.create_task(service.create_and_execute_run(run_data))
            try:
                child_run = await asyncio.shield(create_task)
            except asyncio.CancelledError:
                # create_and_execute_run may already have committed and started its worker.
                # Finish registration before propagating cancellation so the child is stoppable.
                child_run = await create_task
                self._child_runs[task.id] = child_run.id
                await service.cancel_run(child_run.id)
                raise
            self._child_runs[task.id] = child_run.id
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task.id)
            if row:
                row.context = {**row.context, "run_id": child_run.id}
                await repo.add_event(
                    task.id, "step.progress", {"type": "child_run.started", "run_id": child_run.id, "nodeids": nodeids}
                )
                await session.commit()

        deadline = time.monotonic() + min(task.max_duration_seconds, 900)
        while time.monotonic() < deadline:
            async with open_run_service() as service:
                current = await service.get_run(child_run.id)
            if current is None:
                raise TaskBlocked(f"Child TestRun {child_run.id} disappeared.")
            if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                result = {
                    "run_id": child_run.id,
                    "status": current.status.value,
                    "total": current.total,
                    "passed": current.passed,
                    "failed": current.failed,
                    "skipped": current.skipped,
                    "duration_ms": current.duration_ms,
                    "nodeids": nodeids,
                    "executions": [item.model_dump(mode="json") for item in current.executions],
                }
                return {
                    **result,
                    "_evidence": [
                        await self._evidence(
                            task,
                            "run",
                            EvidenceType.TEST_RESULT,
                            "TestRunService + PytestRunner",
                            f"Child run {child_run.id} finished with {current.status.value}: {current.passed}/{current.total} passed.",
                            json.dumps(result, ensure_ascii=False),
                            {"run_id": child_run.id, "status": current.status.value},
                        )
                    ],
                }
            active_task, _ = await self._load(task.id)
            if active_task is None or active_task.status == TaskStatus.CANCELLED.value:
                async with open_run_service() as service:
                    await service.cancel_run(child_run.id)
                raise TaskBlocked("Task was cancelled while its TestRun was executing.")
            await asyncio.sleep(0.35)
        async with open_run_service() as service:
            await service.cancel_run(child_run.id)
        raise TaskBlocked(f"Child TestRun {child_run.id} exceeded the Task verification timeout.")

    async def _classify_run(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        run = outputs.get("run", {})
        failures = []
        for execution in run.get("executions", []):
            if execution.get("status") == "FAILED":
                category, explanation, _ = FailureClassifier.classify(
                    execution.get("error_message") or "", execution.get("stack_trace") or ""
                )
                failures.append(
                    {
                        "nodeid": execution.get("nodeid"),
                        "classification": category.value,
                        "root_cause": explanation,
                        "error_message": execution.get("error_message"),
                    }
                )
        return {
            "failure_count": len(failures),
            "failures": failures,
            "_evidence": [
                await self._evidence(
                    task,
                    "classify",
                    EvidenceType.ANALYSIS,
                    "FailureClassifier",
                    f"Classified {len(failures)} failure(s) from child run output.",
                    json.dumps(failures, ensure_ascii=False),
                    {"run_id": run.get("run_id")},
                )
            ],
        }

    async def _verify_tests(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        candidate = outputs.get("run") or outputs.get("target_run")
        if candidate is None:
            # ExplorePageTask uses page observation rather than pytest verification.
            browser = outputs.get("act", {})
            verified = bool(outputs.get("inspect", {}).get("title") and browser.get("action") in {"clicked", "skipped"})
            if not verified:
                raise TaskBlocked("Browser exploration did not produce enough evidence to verify its result.")
            return {
                "verified": True,
                "kind": "browser_exploration",
                "url": browser.get("url") or outputs["inspect"].get("url"),
            }
        verified = candidate.get("status") == RunStatus.PASSED.value
        result = {
            "verified": verified,
            "kind": "pytest",
            "run_id": candidate.get("run_id"),
            "status": candidate.get("status"),
            "passed": candidate.get("passed"),
            "failed": candidate.get("failed"),
            "total": candidate.get("total"),
        }
        if not verified:
            raise TaskBlocked(f"Verification did not pass: child run status is {candidate.get('status')}.")
        return {
            **result,
            "_evidence": [
                await self._evidence(
                    task,
                    "verify",
                    EvidenceType.TEST_RESULT,
                    "Task verification policy",
                    f"Verified child run {candidate.get('run_id')} passed.",
                    json.dumps(result, ensure_ascii=False),
                    result,
                )
            ],
        }

    async def _compare_test(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        before = outputs.get("review", {})
        after = outputs.get("run", {})
        verified = after.get("status") == RunStatus.PASSED.value
        if not verified:
            raise TaskBlocked(f"Optimized test verification did not pass: child run status is {after.get('status')}.")
        return {
            "verified": True,
            "kind": "pytest_optimization",
            "before_findings": len(before.get("findings", [])),
            "after_status": after.get("status"),
            "run_id": after.get("run_id"),
            "comparison": "source review findings compared with execution verdict",
        }
