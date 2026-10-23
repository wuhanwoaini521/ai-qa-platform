from __future__ import annotations

import ast
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from project_model.task_models import (
    Task,
    TaskApprovalRequest,
    TaskCreate,
    TaskDetail,
    TaskGoalPreview,
    TaskStatus,
    TaskStep,
    TaskStepStatus,
    TaskType,
)

from app.persistence.models import utc_now
from app.ports.task_unit_of_work import TaskUnitOfWorkFactory
from app.services.task_goal_service import TaskGoalService
from app.services.task_workflows import build_plan
from app.services.task_workspace import workspace_source_snapshot
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger("app.task_runtime")


#: Statuses after which a task can never produce another result; shared so that a domain service can tell
#: whether a task it scheduled is still in flight without importing this class at runtime.
TASK_TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.CANCELLED.value,
    }
)


class TaskCommandService:
    """Own task creation, lifecycle commands, approval and goal refresh use cases."""

    EFFECTFUL_TOOLS = {
        "goal.materialize_cases",
        "task.request_approval",
        "source.write_generated",
        "source.apply_repair",
        "tests.register_case",
    }

    WORKSPACE_STALE_TOOLS = {
        "browser.inspect",
        "browser.act",
        "browser.agent",
        "browser.verify",
        "decision.select_candidate",
        "failure.classify",
        "failure.classify_run",
        "failure.collect",
        "failure.diagnose",
        "failure.prepare_repair",
        "goal.coverage",
        "goal.review_project",
        "goal.summary",
        "tests.generate",
        "requirement.analyze",
        "source.generate_refactor",
        "source.inspect",
        "source.inspect_failure",
        "source.review",
        "source.review_report",
        "source.validate_generated",
        "source.validate_workspace",
        "tests.compare",
        "tests.resolve",
        "tests.resolve_requirement",
        "tests.run_generated",
        "tests.run_regression",
        "tests.run_target",
        "tests.verify",
    }

    TERMINAL = TASK_TERMINAL_STATUSES

    def __init__(
        self,
        *,
        goal_service: TaskGoalService,
        max_task_calls: int | Callable[[], int],
        cancel_execution,
        repository_scope: TaskUnitOfWorkFactory,
        runtime_instance_id: str | None = None,
        recorder_session_resolver: Callable[[str, str], Awaitable[Any | None]] | None = None,
    ) -> None:
        self.goal_service = goal_service
        self.max_task_calls = max_task_calls
        self.cancel_execution = cancel_execution
        self.repository_scope = repository_scope
        self.runtime_instance_id = runtime_instance_id
        self.recorder_session_resolver = recorder_session_resolver
        self._create_lock = asyncio.Lock()

    async def preview_goal(self, data: TaskCreate) -> TaskGoalPreview:
        return await self.goal_service.preview_goal(TaskGoalService.apply_runtime_limits(data))

    @staticmethod
    def _goal_step_title(key: str, fallback: str) -> str:
        return TaskGoalService._goal_step_title(key, fallback)

    @staticmethod
    def _goal_request_inputs_hash(inputs: dict[str, Any]) -> str:
        return TaskGoalService._goal_request_inputs_hash(inputs)

    @staticmethod
    def _goal_preview_token(
        data: TaskCreate,
        contract: dict[str, Any],
        facts: dict[str, Any],
        plan: list[Any],
        *,
        request_inputs_hash: str | None = None,
    ) -> str:
        return TaskGoalService._goal_preview_token(data, contract, facts, plan, request_inputs_hash=request_inputs_hash)

    async def _compile_goal(self, data: TaskCreate):
        return await self.goal_service._compile_goal(data)

    async def create(self, data: TaskCreate, owner_id: str) -> Task:
        data = TaskGoalService.apply_runtime_limits(data)
        if data.type != TaskType.QA_GOAL or not data.idempotency_key:
            return await self._create(data, owner_id)
        async with self._create_lock:
            data.inputs = {**data.inputs, "_idempotency_key": data.idempotency_key}
            async with self.repository_scope() as repositories:
                rows = await repositories.tasks.recent_qa_goals(owner_id, data.project_id, limit=100)
                existing = next(
                    (row for row in rows if (row.inputs or {}).get("_idempotency_key") == data.idempotency_key),
                    None,
                )
                if existing:
                    return Task(**repositories.tasks.task_values(existing))
            return await self._create(data, owner_id)

    async def _create(self, data: TaskCreate, owner_id: str) -> Task:
        recorder_runtime_id = await self._recorder_runtime_id(data, owner_id)
        workspace_required = {
            TaskType.QA_GOAL,
            TaskType.CREATE_TEST,
            TaskType.FIX_FAILURE,
            TaskType.OPTIMIZE_TEST,
            TaskType.REVIEW_TEST,
            TaskType.RUN_REGRESSION,
        }
        project_required = {
            TaskType.QA_GOAL,
            TaskType.ANALYZE_REQUIREMENT,
            TaskType.CREATE_TEST,
            TaskType.RUN_REGRESSION,
        }
        if data.type in workspace_required and not data.workspace_id:
            raise ValueError(f"{data.type.value} requires workspace_id")
        if data.type in project_required and not data.project_id:
            raise ValueError(f"{data.type.value} requires project_id")
        if data.type == TaskType.EXPLORE_PAGE or data.type == TaskType.CREATE_TEST and data.inputs.get("url"):
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
            async with self.repository_scope() as repositories:
                workspace_repository = repositories.workspaces
                workspace_row = await workspace_repository.get_by_id(data.workspace_id)
                if workspace_row is None:
                    workspace_row = await workspace_repository.get_by_project_id(data.workspace_id)
                if workspace_row is None:
                    raise ValueError("Workspace not found")
                if data.project_id and workspace_row.project_id != data.project_id:
                    raise ValueError("Workspace does not belong to the selected project")
                project_id = data.project_id or workspace_row.project_id
                if await repositories.projects.get_by_id(project_id) is None:
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
            async with self.repository_scope() as repositories:
                if await repositories.projects.get_by_id(data.project_id) is None:
                    raise ValueError("Project not found")
        if data.type == TaskType.ANALYZE_REQUIREMENT:
            requirement_id = str(data.inputs.get("requirement_id") or "").strip()
            if not requirement_id:
                raise ValueError("ANALYZE_REQUIREMENT requires inputs.requirement_id")
            async with self.repository_scope() as repositories:
                requirement = await repositories.requirements.get_by_id(requirement_id)
                if requirement is None:
                    raise ValueError("Requirement not found")
                if requirement.project_id != data.project_id:
                    raise ValueError("Requirement does not belong to the selected project")
        goal_request_inputs_hash = (
            self._goal_request_inputs_hash(data.inputs) if data.type == TaskType.QA_GOAL else None
        )
        if data.inputs.get("test_case_id"):
            async with self.repository_scope() as repositories:
                case = await repositories.test_cases.get_by_id(str(data.inputs["test_case_id"]))
                if not case or case.project_id != data.project_id:
                    raise ValueError("Test case does not belong to the selected project")
                data.inputs = {
                    **data.inputs,
                    "case_context": {
                        "title": case.title,
                        "preconditions": case.preconditions,
                        "steps": case.steps,
                        "expected_result": case.expected_result,
                        "test_model": case.test_model or {},
                        "requirement_id": case.requirement_id,
                    },
                }
        if data.type == TaskType.QA_GOAL:
            contract, facts, plan = await self._compile_goal(data)
            plan_token = self._goal_preview_token(
                data, contract, facts, plan, request_inputs_hash=goal_request_inputs_hash
            )
            if not data.plan_token or data.plan_token != plan_token:
                raise ValueError("Project context or plan changed. Preview the goal again before starting it.")
            data.inputs = {
                **data.inputs,
                "_goal_contract": contract,
                "_goal_plan_token": plan_token,
                "_goal_request_inputs_hash": goal_request_inputs_hash,
            }
        else:
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
            "context": {
                "ai_calls": 0,
                "tool_calls": 0,
                **({"_recorder_runtime_id": recorder_runtime_id} if recorder_runtime_id else {}),
            },
            "verification": {},
            "retry_count": 0,
            "replan_count": 0,
            "max_steps": data.max_steps,
            "max_retries": data.max_retries,
            "max_replans": data.max_replans,
            "max_ai_calls": min(data.max_ai_calls, self._max_task_call_limit()),
            "max_duration_seconds": data.max_duration_seconds,
            "current_step_id": None,
            "failure_reason": None,
        }
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            row = await repo.create(values, steps)
            await repositories.commit()
            return Task(**repo.task_values(row))

    async def _recorder_runtime_id(self, data: TaskCreate, owner_id: str) -> str | None:
        session_id = str(data.inputs.get("recorder_session_id") or "").strip()
        if not session_id:
            return None

        if self.recorder_session_resolver is not None:
            session = await self.recorder_session_resolver(session_id, owner_id)
            if session is None:
                raise ValueError("浏览器录制会话不在当前 API 实例中。请重新启动录制器会话后，再发起 AI 流程。")
            if session.project_id != data.project_id:
                raise ValueError("浏览器录制会话与当前任务不属于同一项目。")

        return self.runtime_instance_id

    def _max_task_call_limit(self) -> int:
        value = self.max_task_calls() if callable(self.max_task_calls) else self.max_task_calls
        return max(0, int(value))

    async def get(self, task_id: str, owner_id: str | None = None) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            row = await repo.get(task_id, owner_id)
            return await repo.get_detail(row) if row else None

    async def list(self, owner_id: str, project_id: str | None = None, limit: int = 50) -> list[Task]:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            rows = await repo.list(owner_id, project_id=project_id, limit=limit)
            steps = await repo.get_steps_for_tasks([row.id for row in rows])
            return [
                Task(
                    **repo.task_values(row),
                    plan=[TaskStep.model_validate(step, from_attributes=True) for step in steps.get(row.id, [])],
                )
                for row in rows
            ]

    async def approve(self, task_id: str, owner_id: str, request: TaskApprovalRequest) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id, owner_id)
            if not task or task.status != TaskStatus.WAITING.value or not task.current_step_id:
                return None
            step = await repo.get_step(task.current_step_id)
            if not step or step.status != TaskStepStatus.WAITING_FOR_APPROVAL.value:
                return None
            next_status = TaskStatus.PENDING.value if request.approved else TaskStatus.BLOCKED.value
            now = utc_now()
            if not await repo.claim_approval(task.id, owner_id, step.id):
                await repositories.rollback()
                return None
            await repo.update_task(
                task.id,
                status=next_status,
                failure_reason=None if request.approved else "User rejected the proposed workspace change.",
                finished_at=None if request.approved else now,
            )
            if request.approved:
                step_status = TaskStepStatus.COMPLETED.value
                event_type = "decision.created"
            else:
                step_status = TaskStepStatus.SKIPPED.value
                event_type = "task.blocked"
            await repo.update_step(
                step.id,
                status=step_status,
                outputs={"approved": request.approved, "comment": request.comment},
                finished_at=utc_now(),
            )
            await repo.add_decision(
                task_id=task.id,
                step_id=step.id,
                name="source_change_approval",
                provider="user",
                choice="approved" if request.approved else "rejected",
                rationale=request.comment,
                escalated=False,
            )
            await repo.add_event(
                task.id, event_type, {"step_id": step.id, "approved": request.approved, "comment": request.comment}
            )
            await repositories.commit()
        return await self.get(task_id, owner_id)

    async def cancel(self, task_id: str, owner_id: str) -> TaskDetail | None:
        """Ask the task to stop.

        A replica that does not own the lease may record the request but must not write a terminal
        status it did not produce; the owner ends its own task under its lease, and a task nobody
        holds a live lease on can be closed here atomically (see `finish_fenced`).
        """
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id, owner_id)
            if not task or task.status in self.TERMINAL:
                return None
            requested = await repo.request_cancel(task.id, owner_id)
            if requested is None:
                await repositories.commit()
                return await repo.get_detail(task)
            if requested.cancel_requested_at is not None and task.cancel_requested_at is None:
                await repo.add_event(task.id, "task.cancel_requested", {"actor": owner_id})
            finalized = await repo.finish_fenced(
                task.id,
                TaskStatus.CANCELLED.value,
                require_no_live_lease=True,
                failure_reason=None,
            )
            if finalized:
                if task.current_step_id:
                    step = await repo.get_step(task.current_step_id)
                    if step and step.status in {
                        TaskStepStatus.RUNNING.value,
                        TaskStepStatus.WAITING_FOR_APPROVAL.value,
                    }:
                        await repo.update_step(
                            step.id,
                            status=TaskStepStatus.CANCELLED.value,
                            error="Cancelled by user.",
                            finished_at=utc_now(),
                        )
                await repo.add_event(task.id, "task.cancelled", {"via": "request"})
            await repositories.commit()
            detail = await repo.get_detail(task)
        await self.cancel_execution(task_id, (task.context or {}).get("run_id"))
        return detail

    async def pause(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id, owner_id)
            if not task:
                return None
            if task.status in {TaskStatus.PAUSED.value, TaskStatus.PAUSING.value}:
                return await repo.get_detail(task)
            if task.status not in {
                TaskStatus.PENDING.value,
                TaskStatus.PLANNING.value,
                TaskStatus.RUNNING.value,
                TaskStatus.VERIFYING.value,
                TaskStatus.RETRYING.value,
                TaskStatus.REPLANNING.value,
            }:
                return None
            if task.status == TaskStatus.PENDING.value:
                next_context = {
                    **(task.context or {}),
                    "pause_workspace_snapshot": workspace_source_snapshot(task.workspace_id),
                }
                next_status = TaskStatus.PAUSED.value
                await repo.add_event(task.id, "task.paused", {"boundary": "before_start"})
            else:
                next_context = task.context or {}
                next_status = TaskStatus.PAUSING.value
                await repo.add_event(task.id, "task.pause_requested", {"boundary": "after_current_step"})
            await repo.update_task(
                task.id,
                context=next_context,
                status=next_status,
                finished_at=None if next_status == TaskStatus.PAUSED.value else task.finished_at,
            )
            await repositories.commit()
        return await self.get(task_id, owner_id)

    async def resume(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            if not await repo.claim_resume(task_id, owner_id):
                return None
            await repositories.commit()
        try:
            return await self._resume_claimed(task_id, owner_id)
        except BaseException:
            async with self.repository_scope() as repositories:
                await repositories.tasks.restore_paused_after_resume_failure(task_id, owner_id)
                await repositories.commit()
            raise

    async def _resume_claimed(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id, owner_id)
            if not task or task.status != TaskStatus.RESUMING.value:
                return None

            before = (task.context or {}).get("pause_workspace_snapshot", {})
            current = workspace_source_snapshot(task.workspace_id)
            changed = sorted(path for path in set(before) | set(current) if before.get(path) != current.get(path))
            workspace = WorkspaceService()
            for path in changed:
                if path not in current or not path.endswith(".py"):
                    continue
                try:
                    ast.parse(await workspace.read_file(task.workspace_id or "", path), filename=path)
                except SyntaxError as error:
                    raise ValueError(
                        f"Studio 修改后的 {path} 有语法错误（第 {error.lineno or 1} 行），修复后再恢复。"
                    ) from error

            plan_refreshed = False
            if task.type == TaskType.QA_GOAL.value:
                data = TaskCreate(
                    type=TaskType.QA_GOAL,
                    goal=task.goal,
                    project_id=task.project_id,
                    workspace_id=task.workspace_id,
                    inputs=task.inputs or {},
                    max_steps=task.max_steps,
                    max_retries=task.max_retries,
                    max_replans=task.max_replans,
                    max_ai_calls=task.max_ai_calls,
                    max_duration_seconds=task.max_duration_seconds,
                )
                contract, facts, fresh_plan = await self._compile_goal(data)
                request_inputs_hash = (task.inputs or {}).get("_goal_request_inputs_hash")
                fresh_token = self._goal_preview_token(
                    data, contract, facts, fresh_plan, request_inputs_hash=request_inputs_hash
                )
                rows = await repo.steps_for_task(task.id)
                existing_keys = {row.key for row in rows}
                new_step_count = sum(spec.key not in existing_keys for spec in fresh_plan)
                if len(rows) + new_step_count > task.max_steps:
                    raise ValueError(
                        "Updated plan exceeds the task step limit. Create a new goal with a narrower scope."
                    )
                existing = {row.key: row for row in rows}
                fresh_by_key = {spec.key: spec for spec in fresh_plan}
                stale_context = bool(changed) or (task.inputs or {}).get("_goal_plan_token") != fresh_token
                tainted = {
                    row.key
                    for row in rows
                    if row.key in fresh_by_key
                    and (
                        row.status == TaskStepStatus.SKIPPED.value
                        or stale_context
                        and row.tool in self.WORKSPACE_STALE_TOOLS
                    )
                }
                invalidated = {key for key in tainted if existing[key].tool not in self.EFFECTFUL_TOOLS}
                while True:
                    dependents = {
                        spec.key
                        for spec in fresh_plan
                        if spec.key not in tainted and any(key in tainted for key in spec.depends_on)
                    }
                    if not dependents:
                        break
                    tainted.update(dependents)
                    invalidated.update(
                        spec.key
                        for spec in fresh_plan
                        if spec.key in dependents and spec.tool not in self.EFFECTFUL_TOOLS
                    )
                invalidated_steps = sorted(invalidated)
                step_statuses = {row.id: row.status for row in rows}
                for key in invalidated_steps:
                    row = existing[key]
                    await repo.update_step(
                        row.id,
                        status=TaskStepStatus.PENDING.value,
                        outputs={},
                        evidence_ids=[],
                        error=None,
                        started_at=None,
                        finished_at=None,
                        duration_ms=0,
                        retry_count=0,
                    )
                    step_statuses[row.id] = TaskStepStatus.PENDING.value
                for row in rows:
                    if step_statuses[row.id] == TaskStepStatus.PENDING.value and row.key not in fresh_by_key:
                        await repo.update_step(
                            row.id,
                            status=TaskStepStatus.SKIPPED.value,
                            outputs={"skipped": True, "reason": "Plan refreshed from current project state."},
                            finished_at=utc_now(),
                        )
                        step_statuses[row.id] = TaskStepStatus.SKIPPED.value
                completed_positions = [
                    row.position
                    for row in rows
                    if step_statuses[row.id] in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                ]
                next_position = max(completed_positions, default=-1) + 1
                for spec in fresh_plan:
                    row = existing.get(spec.key)
                    if row and step_statuses[row.id] != TaskStepStatus.PENDING.value:
                        continue
                    values = {
                        "name": spec.name,
                        "tool": spec.tool,
                        "dependencies": spec.depends_on,
                        "condition": spec.when,
                        "inputs": spec.inputs,
                    }
                    if row:
                        await repo.update_step(row.id, **values, position=next_position)
                    else:
                        row = await repo.add_step(
                            task_id=task.id,
                            key=spec.key,
                            status=TaskStepStatus.PENDING.value,
                            outputs={},
                            evidence_ids=[],
                            retry_count=0,
                            max_retries=spec.max_retries,
                            parallelizable=spec.parallelizable,
                            position=next_position,
                            **values,
                        )
                        existing[spec.key] = row
                    next_position += 1
                refreshed_inputs = {
                    **(task.inputs or {}),
                    "_goal_contract": contract,
                    "_goal_plan_token": fresh_token,
                    "_goal_request_inputs_hash": request_inputs_hash or self._goal_request_inputs_hash(data.inputs),
                }
                await repo.update_task(task.id, inputs=refreshed_inputs)
                plan_refreshed = True
                await repo.add_event(
                    task.id,
                    "task.plan_refreshed",
                    {
                        "step_keys": [spec.key for spec in fresh_plan],
                        "changed_files": changed,
                        "invalidated_steps": invalidated_steps,
                    },
                )
            elif changed:
                rows = await repo.steps_for_task(task.id)
                by_key = {row.key: row for row in rows}
                tainted = {
                    row.key
                    for row in rows
                    if row.tool in self.WORKSPACE_STALE_TOOLS
                    and row.status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                }
                while True:
                    dependents = {
                        row.key
                        for row in rows
                        if row.key not in tainted and any(key in tainted for key in row.dependencies)
                    }
                    if not dependents:
                        break
                    tainted.update(dependents)
                invalidated_steps = sorted(
                    key
                    for key in tainted
                    if by_key[key].status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                    and by_key[key].tool not in self.EFFECTFUL_TOOLS
                )
                step_statuses = {row.id: row.status for row in rows}
                for key in invalidated_steps:
                    row = by_key[key]
                    await repo.update_step(
                        row.id,
                        status=TaskStepStatus.PENDING.value,
                        outputs={},
                        evidence_ids=[],
                        error=None,
                        started_at=None,
                        finished_at=None,
                        duration_ms=0,
                        retry_count=0,
                    )
                    step_statuses[row.id] = TaskStepStatus.PENDING.value
                if invalidated_steps:
                    plan_refreshed = True
                    await repo.add_event(
                        task.id,
                        "task.context_refreshed",
                        {"changed_files": changed, "invalidated_steps": invalidated_steps},
                    )

            current_step = await repo.get_step(task.current_step_id) if task.current_step_id else None
            resumed_status = (
                TaskStatus.WAITING.value
                if current_step and current_step.status == TaskStepStatus.WAITING_FOR_APPROVAL.value
                else TaskStatus.PENDING.value
            )
            resumed_context = {
                **(task.context or {}),
                "pause_workspace_snapshot": current,
                "workspace_changes_on_resume": changed,
            }
            await repo.add_event(
                task.id,
                "task.resumed",
                {"changed_files": changed, "workspace_files": len(current), "plan_refreshed": plan_refreshed},
            )
            if not await repo.finish_resume(task.id, owner_id, resumed_status, resumed_context):
                await repositories.rollback()
                return await self.get(task_id, owner_id)
            await repositories.commit()
        return await self.get(task_id, owner_id)

    async def replan(self, task_id: str, owner_id: str, instructions: str) -> TaskDetail | None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id, owner_id)
            if not task or task.status not in {TaskStatus.BLOCKED.value, TaskStatus.FAILED.value}:
                return None
            if task.replan_count >= task.max_replans:
                raise ValueError("Task replan limit reached")
            next_replan_count = task.replan_count + 1

            if not await repo.claim_replan(task.id, owner_id, task.replan_count, instructions, task.inputs or {}):
                await repositories.rollback()
                latest = await repo.get(task_id, owner_id)
                if (
                    latest
                    and latest.status in {TaskStatus.BLOCKED.value, TaskStatus.FAILED.value}
                    and latest.replan_count >= latest.max_replans
                ):
                    raise ValueError("Task replan limit reached")
                return None

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
            for step in rows:
                if step.status == TaskStepStatus.FAILED.value:
                    # The column is non-null; without a started/finished timestamp the
                    # runtime projection treats this stored placeholder as unavailable.
                    await repo.update_step(
                        step.id,
                        status=TaskStepStatus.PENDING.value,
                        error=None,
                        outputs={},
                        finished_at=None,
                        started_at=None,
                        duration_ms=0,
                        retry_count=(step.retry_count or 0) + 1,
                    )
            await repo.add_event(
                task.id, "task.replanning", {"instructions": instructions[:4000], "replan_count": next_replan_count}
            )
            await repositories.commit()
        return await self.get(task_id, owner_id)
