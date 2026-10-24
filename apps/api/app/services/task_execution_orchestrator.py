from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar
from dataclasses import replace
from typing import Any

from project_model.task_models import (
    TaskStatus,
    TaskStep,
    TaskStepStatus,
)
from qa_core.ai.models import CodeAssistantResponse
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.persistence.models import utc_now
from app.ports.browser_runtime import BrowserRuntime
from app.ports.task_unit_of_work import TaskUnitOfWorkFactory
from app.services.ai_step_context import ai_step_scope, reset_ai_step
from app.services.task_ai_service import TaskAIService
from app.services.task_browser_executor import TaskBrowserExecutor
from app.services.task_code_generation_service import TaskCodeGenerationService
from app.services.task_decision_service import TaskDecisionService
from app.services.task_discovery_intelligence import TaskDiscoveryIntelligenceService
from app.services.task_errors import ApprovalRequired, TaskBlocked, TaskCancelled
from app.services.task_evidence_service import TaskEvidenceService
from app.services.task_execution_ports import TaskExecutionPorts
from app.services.task_failure_repair_service import TaskFailureRepairService
from app.services.task_goal_service import TaskGoalService
from app.services.task_lease_context import current_lease
from app.services.task_test_execution_service import TaskTestExecutionService
from app.services.task_workspace import workspace_source_digest

active_runtime_step: ContextVar[str | None] = ContextVar("active_runtime_step", default=None)
active_task_deadline: ContextVar[float | None] = ContextVar("active_task_deadline", default=None)

logger = logging.getLogger("app.task_runtime")


class TaskExecutionOrchestrator:
    """Run persisted task DAG steps and delegate each capability to its owner."""

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

    TERMINAL = {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.CANCELLED.value,
    }

    def __init__(
        self,
        *,
        browser_runtime: BrowserRuntime | None = None,
        child_runs: dict[str, str] | None = None,
        repository_scope: TaskUnitOfWorkFactory,
    ) -> None:
        self._child_runs = child_runs if child_runs is not None else {}
        self.repository_scope = repository_scope
        if browser_runtime is None:
            from app.container import get_browser_runtime

            browser_runtime = get_browser_runtime()
        self.browser_runtime = browser_runtime
        self.active_runtime_step = active_runtime_step
        self.active_task_deadline = active_task_deadline
        self.TaskBlocked = TaskBlocked
        self.execution_ports = TaskExecutionPorts(
            browser_runtime=self.browser_runtime,
            active_runtime_step=self.active_runtime_step,
            active_task_deadline=self.active_task_deadline,
            child_runs=self._child_runs,
            repository_scope=self.repository_scope,
            input=self._input,
            load_task=self._load_execution_context,
            record_ai_trace=self._record_ai_trace,
            browser_agent_event=self._browser_agent_event,
            persist_browser_agent_state=self._persist_browser_agent_state,
            persist_browser_agent_artifact=self._persist_browser_agent_artifact,
            persist_browser_agent_evidence=self._persist_browser_agent_evidence,
            artifact=self._artifact,
            evidence=self._evidence,
            execute_browser_candidate=lambda session_id, candidate: self.browser_executor._execute_browser_candidate(
                session_id, candidate
            ),
            recorder_storage_state=self._recorder_storage_state,
            call_code_ai=lambda task, prompt: self.ai_service.call_code_ai(task, prompt),
            inspect_source=self._inspect_source,
            review_source=self._review_source,
            validate_python_test=TaskCodeGenerationService._validate_python_test,
            workspace_source_digest=workspace_source_digest,
            write_approved_source=self._write_approved_source,
            persist_artifact=lambda *args, **kwargs: self.evidence_service.persist_artifact(*args, **kwargs),
        )
        self.ai_service = TaskAIService(self.execution_ports)
        self.decision_service = TaskDecisionService(
            repository_scope=repository_scope,
            reserve_ai_call=self.ai_service.reserve_ai_call,
        )
        self.browser_executor = TaskBrowserExecutor(
            self.execution_ports, ai_service=self.ai_service, decision_service=self.decision_service
        )
        self.test_execution = TaskTestExecutionService(self.execution_ports)
        self.failure_repair = TaskFailureRepairService(self.execution_ports, ai_service=self.ai_service)
        self.evidence_service = TaskEvidenceService(self.execution_ports)
        self.code_generation = TaskCodeGenerationService(self.execution_ports)
        self.goal_service = TaskGoalService(self.execution_ports)
        self.discovery_intelligence = TaskDiscoveryIntelligenceService(
            self.execution_ports, ai_service=self.ai_service, decision_service=self.decision_service
        )

    async def _load(self, task_id: str) -> tuple[TaskExecutionRecord | None, list[TaskStep]]:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            task = await repo.get(task_id)
            if task is None:
                return None, []
            steps = await repo.steps_for_task(task_id)
            return (
                TaskExecutionRecord.from_record(task),
                [TaskStep.model_validate(step, from_attributes=True) for step in steps],
            )

    async def _load_execution_context(self, task_id: str):
        return await self._load(task_id)

    async def _execute_step(
        self, task: TaskExecutionRecord, step: TaskStep, *, deadline: float | None = None
    ) -> dict[str, Any] | ApprovalRequired | TaskBlocked | TaskCancelled:
        condition = step.condition or {}
        skip = False
        condition_key = condition.get("input_exists")
        if condition_key and not task.inputs.get(condition_key):
            skip = True
        output_condition = condition.get("output_truthy")
        if output_condition:
            _, condition_steps = await self._load(task.id)
            completed_outputs = {
                row.key: row.outputs or {}
                for row in condition_steps
                if row.status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
            }
            source = completed_outputs.get(str(output_condition.get("step") or ""), {})
            field = str(output_condition.get("field") or "")
            value: Any = source
            for part in field.split(".") if field else []:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                    value = value[int(part)]
                else:
                    value = None
                    break
            skip = skip or not bool(value)
        if skip:
            if output_condition:
                field = str(output_condition.get("field") or "")
                reason = {
                    "unbound_case_ids": "No uncovered cases remained after checking current automation bindings.",
                    "first_failure_id": "The selected tests passed; failure analysis was skipped.",
                    "repairable_failure_id": "Failure evidence did not meet the safe repair policy.",
                }.get(field, f"Condition not met: {field or output_condition}.")
            else:
                reason = f"Condition not met: {condition_key or output_condition}."
            await self._complete_step(
                task.id,
                step.id,
                {"skipped": True, "reason": reason},
                skipped=True,
            )
            async with self.repository_scope() as repositories:
                await repositories.tasks.add_event(
                    task.id,
                    "task.plan_changed",
                    {"step_id": step.id, "step_key": step.key, "reason": reason},
                )
                await repositories.commit()
            return {"skipped": True}

        started = time.perf_counter()
        while True:
            async with self.repository_scope() as repositories:
                repo = repositories.tasks
                fresh = await repo.get(task.id)
                current = await repo.get_step(step.id)
                if not fresh:
                    return TaskBlocked("Task disappeared before the step could start")
                if fresh.status == TaskStatus.CANCELLED.value:
                    return TaskCancelled("Task was cancelled")
                if fresh.cancel_requested_at is not None:
                    # Someone asked for this task to stop; only this owner may end it, here at a boundary.
                    return TaskCancelled("Cancelled by user.")
                if current is None:
                    return TaskBlocked("Task step disappeared")
                if fresh.status == TaskStatus.PAUSING.value:
                    return {"deferred_for_pause": True}
                running_status = (
                    TaskStatus.VERIFYING.value
                    if step.tool
                    in {
                        "tests.verify",
                        "tests.compare",
                        "browser.verify",
                    }
                    else TaskStatus.RUNNING.value
                )
                current = await repo.claim_running_step(task.id, step.id, running_status)
                if current is None:
                    await repositories.rollback()
                    return TaskBlocked("Task step could not be claimed")
                await repo.add_event(
                    fresh.id,
                    "step.started",
                    {"step_id": current.id, "key": current.key, "tool": current.tool, "input": current.inputs},
                )
                await repositories.commit()

            try:
                async with self.repository_scope() as repositories:
                    await repositories.tasks._assert_current_lease(task.id)
                outputs = await self._run_step_tool(task.id, step, deadline=deadline)
            except ApprovalRequired:
                async with self.repository_scope() as repositories:
                    repo = repositories.tasks
                    current_task = await repo.get(task.id)
                    if (
                        not current_task
                        or current_task.status not in {TaskStatus.RUNNING.value, TaskStatus.PAUSING.value}
                        or current_task.current_step_id != step.id
                    ):
                        await repositories.rollback()
                        return ApprovalRequired()
                    next_status = (
                        TaskStatus.PAUSING.value
                        if current_task.status == TaskStatus.PAUSING.value
                        else TaskStatus.WAITING.value
                    )
                    if not await repo.await_step_approval(
                        task.id, current_task.owner_id, current_task.status, step.id, next_status
                    ):
                        await repositories.rollback()
                        return ApprovalRequired()
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
                    await repositories.commit()
                return ApprovalRequired()
            except TaskCancelled as error:
                elapsed = (time.perf_counter() - started) * 1000
                async with self.repository_scope() as repositories:
                    repo = repositories.tasks
                    current = await repo.get_step(step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        await repo.update_step(
                            current.id,
                            status=TaskStepStatus.CANCELLED.value,
                            error=SensitiveRedactor.redact_text(str(error))[:4000],
                            duration_ms=elapsed,
                            finished_at=utc_now(),
                        )
                        await repo.add_event(
                            task.id,
                            "step.progress",
                            {"step_id": step.id, "status": "CANCELLED", "duration_ms": elapsed},
                        )
                        await repositories.commit()
                return error
            except TaskBlocked as error:
                elapsed = (time.perf_counter() - started) * 1000
                async with self.repository_scope() as repositories:
                    repo = repositories.tasks
                    current = await repo.get_step(step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        await repo.update_step(
                            current.id,
                            status=TaskStepStatus.FAILED.value,
                            error=SensitiveRedactor.redact_text(str(error))[:4000],
                            duration_ms=elapsed,
                            finished_at=utc_now(),
                            outputs=SensitiveRedactor.redact_value(
                                {"failure_type": error.failure_type, **error.details}
                            ),
                        )
                        await repo.add_event(
                            task.id,
                            "step.failed",
                            {
                                "step_id": step.id,
                                "error": SensitiveRedactor.redact_text(str(error))[:1000],
                                "blocked": True,
                                "duration_ms": elapsed,
                                "failure_type": error.failure_type,
                                **error.details,
                            },
                        )
                        await repositories.commit()
                return error
            except Exception as error:
                elapsed = (time.perf_counter() - started) * 1000
                async with self.repository_scope() as repositories:
                    repo = repositories.tasks
                    current = await repo.get_step(step.id)
                    fresh = await repo.get(task.id)
                    if current is None or fresh is None:
                        return error
                    if fresh.cancel_requested_at is not None:
                        # The user asked to stop before this step failed; a retry would ignore that.
                        await repo.update_step(
                            current.id,
                            status=TaskStepStatus.CANCELLED.value,
                            error=SensitiveRedactor.redact_text(str(error))[:4000],
                            duration_ms=elapsed,
                            finished_at=utc_now(),
                        )
                        await repo.add_event(
                            task.id,
                            "step.progress",
                            {"step_id": step.id, "status": "CANCELLED", "duration_ms": elapsed},
                        )
                        await repositories.commit()
                        return TaskCancelled("Cancelled by user.")
                    next_step_retry_count = current.retry_count + 1
                    next_task_retry_count = fresh.retry_count
                    retryable = (
                        getattr(error, "code", None) != "output_limit"
                        and step.tool
                        in {
                            "browser.inspect",
                            "source.inspect",
                            "source.validate_generated",
                            "source.validate_workspace",
                            "browser.verify",
                            "requirement.analyze",
                            "goal.coverage",
                            "goal.materialize_cases",
                            "tests.generate",
                            "failure.diagnose",
                            "tests.resolve_requirement",
                        }
                        and next_step_retry_count <= min(current.max_retries, fresh.max_retries)
                        and fresh.retry_count < fresh.max_retries
                    )
                    if retryable:
                        next_task_retry_count += 1
                    await repo.update_step(
                        current.id,
                        status=(TaskStepStatus.PENDING.value if retryable else TaskStepStatus.FAILED.value),
                        retry_count=next_step_retry_count,
                        error=SensitiveRedactor.redact_text(str(error))[:4000],
                        duration_ms=elapsed,
                        finished_at=None if retryable else utc_now(),
                    )
                    await repo.add_event(
                        task.id,
                        "step.failed",
                        {
                            "step_id": step.id,
                            "error": SensitiveRedactor.redact_text(str(error))[:1000],
                            "retry": next_step_retry_count,
                        },
                    )
                    if retryable:
                        if fresh.status != TaskStatus.PAUSING.value:
                            await repo.update_task(
                                task.id,
                                status=TaskStatus.RETRYING.value,
                                retry_count=next_task_retry_count,
                            )
                        await repo.add_event(
                            task.id, "task.retrying", {"step_id": step.id, "retry_count": next_task_retry_count}
                        )
                        await repositories.commit()
                        await asyncio.sleep(min(0.5 * (2 ** (next_step_retry_count - 1)), 3.0))
                        continue
                    await repositories.commit()
                return error

            if outputs.pop("_pause_after_step", False):
                async with self.repository_scope() as repositories:
                    repo = repositories.tasks
                    current = await repo.get_step(step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        await repo.update_step(
                            current.id,
                            status=TaskStepStatus.PENDING.value,
                            finished_at=None,
                            outputs={},
                        )
                        await repo.add_event(
                            task.id,
                            "browser.agent_paused",
                            {
                                "step_id": step.id,
                                "title": "浏览器已暂停，可手动操作后恢复 Agent",
                                "summary": str(outputs.get("current_url") or "已保存当前页面；恢复时会重新观察。")[
                                    :500
                                ],
                                "status": "PAUSED",
                            },
                        )
                        await repositories.commit()
                return {"deferred_for_pause": True}

            async with self.repository_scope() as repositories:
                await repositories.tasks._assert_current_lease(task.id)
            await self._complete_step(task.id, step.id, outputs, duration_ms=(time.perf_counter() - started) * 1000)
            return outputs

    async def _complete_step(
        self, task_id: str, step_id: str, outputs: dict[str, Any], *, skipped: bool = False, duration_ms: float = 0.0
    ) -> None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            row = await repo.get_step(step_id)
            if not row:
                return
            evidence_ids = await self.evidence_service.persist_step_outputs(
                repositories.evidence, task_id, step_id, outputs
            )
            decision = outputs.pop("_decision", None)
            if decision:
                decision_values = {
                    key: value for key, value in decision.items() if key != "confidence" or value is not None
                }
                stored = await repo.add_decision(task_id=task_id, step_id=step_id, **decision_values)
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
            await repositories.commit()

    async def _finish(
        self, task_id: str, status: TaskStatus, reason: str | None, verification: dict[str, Any] | None = None
    ) -> None:
        async with self.repository_scope() as repositories:
            repo = repositories.tasks
            lease = current_lease()
            if lease is not None and not await repo.holds_lease(task_id, lease[0], lease[1]):
                # Another instance owns this task now; this worker must not write anything further.
                logger.warning("Task %s lost its lease before terminal persistence", task_id)
                return
            row = await repo.get(task_id)
            if not row or row.status in self.TERMINAL:
                return
            verification_result = row.verification if verification is None else verification
            requested_cancel = row.cancel_requested_at is not None and status in {
                TaskStatus.FAILED,
                TaskStatus.BLOCKED,
            }
            if requested_cancel:
                # The user asked to stop; anything that happened afterwards is a consequence of the stop,
                # not a product failure the next reader should chase. The outcome stays in the event.
                verification_result = {
                    **(verification_result or {}),
                    "interrupted_outcome": status.value,
                    "interrupted_reason": reason,
                }
                status = TaskStatus.CANCELLED
                reason = "Cancelled by user."
            written = await repo.finish_fenced(
                task_id,
                status.value,
                owner=lease[0] if lease else None,
                token=lease[1] if lease else None,
                require_no_live_lease=lease is None,
                failure_reason=reason,
                verification=verification_result,
            )
            if not written:
                # The lease moved (or expired and was re-claimed) between deciding and writing.
                logger.warning("Task %s lost its lease during terminal persistence", task_id)
                return
            if status == TaskStatus.CANCELLED and row.current_step_id:
                step = await repo.get_step(row.current_step_id)
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
            await repo.add_event(task_id, event, {"reason": reason, "verification": verification_result})
            await repositories.commit()

    async def _run_tool(self, task_id: str, step_key: str, tool: str) -> dict[str, Any]:
        task, steps = await self.execution_ports.load_task(task_id)
        if not task:
            raise TaskBlocked("Task not found")
        outputs = {step.key: step.outputs for step in steps if step.status == TaskStepStatus.COMPLETED.value}
        if getattr(task, "type", None) == "WORKFLOW_EXECUTION":
            node_keys = (task.context or {}).get("workflow_node_keys_by_kind") or {}
            collector_key = node_keys.get("failure.collect")
            if collector_key and collector_key in outputs:
                outputs["collect"] = outputs[collector_key]
        for step in steps:
            if step.status != TaskStepStatus.COMPLETED.value:
                continue
            for prefix in ("failure_", "repair_"):
                if step.key.startswith(prefix):
                    outputs.setdefault(step.key.removeprefix(prefix), step.outputs)
        if step_key.startswith("repair_"):
            for step in steps:
                if step.status == TaskStepStatus.COMPLETED.value and step.key.startswith(("failure_", "repair_")):
                    outputs[step.key.split("_", 1)[1]] = step.outputs
        active = next((step for step in steps if step.key == step_key), None)
        if active and active.inputs:
            task = replace(
                task,
                inputs={**task.inputs, **self._resolve_step_inputs(active.inputs, outputs)},
            )
        dispatch = {
            "requirement.analyze": self.ai_service._analyze_requirement,
            "goal.materialize_cases": self.goal_service._materialize_goal_cases,
            "goal.coverage": self.goal_service._inspect_goal_coverage,
            "goal.summary": self.goal_service._summarize_goal,
            "goal.review_project": self.goal_service._review_project_tests,
            "browser.inspect": self.browser_executor._browser_inspect,
            "browser.act": self.browser_executor._browser_act,
            "browser.agent": self.browser_executor._browser_agent,
            "browser.verify": self.browser_executor._browser_verify,
            "discovery.run": self._run_discovery_loop,
            "discovery.collect_gaps": self.discovery_intelligence._collect_gaps,
            "discovery.analyze_gaps": self.discovery_intelligence._analyze_gaps,
            "discovery.grade_gaps": self.discovery_intelligence._grade_suggestions,
            "discovery.summarize_gaps": self.discovery_intelligence._summarize_task,
            "decision.select_candidate": self.browser_executor._decision_select,
            "tests.generate": self.code_generation._generate_test,
            "source.validate_generated": self.code_generation._validate_generated,
            "task.request_approval": self.code_generation._request_approval,
            "source.write_generated": self.code_generation._write_generated,
            "tests.run_generated": self.test_execution._run_generated,
            "tests.resolve": self.test_execution._resolve_tests,
            "tests.resolve_requirement": self.goal_service._resolve_requirement_tests,
            "tests.run_regression": self.test_execution._run_regression,
            "tests.register_case": self.test_execution._register_test_case,
            "failure.collect": self.failure_repair._collect_failure,
            "failure.classify": self.failure_repair._classify_failure,
            "failure.diagnose": self.failure_repair._diagnose_failure,
            "source.inspect_failure": self.failure_repair._inspect_failure_source,
            "failure.prepare_repair": self.failure_repair._prepare_repair,
            "source.apply_repair": self.failure_repair._apply_repair,
            "source.validate_workspace": self.failure_repair._validate_workspace,
            "tests.run_target": self.test_execution._run_target,
            "failure.classify_run": self.test_execution._classify_run,
            "tests.verify": self.test_execution._verify_tests,
            "source.inspect": self.code_generation._inspect_source,
            "source.review": self.code_generation._review_source,
            "source.generate_refactor": self.code_generation._generate_refactor,
            "tests.compare": self.test_execution._compare_test,
            "source.review_report": self.code_generation._review_report,
        }
        handler = dispatch.get(tool)
        if not handler:
            raise TaskBlocked(f"No runtime tool is registered for '{tool}'.")
        return await handler(task, outputs)

    async def _run_discovery_loop(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        """Run one bounded Quality Discovery loop under this runtime's ownership."""
        run_id = str(task.inputs.get("discovery_run_id") or "").strip()
        if not run_id:
            raise TaskBlocked("A Quality Discovery run id is required.")
        # Imported lazily: the container builds the discovery service with this runtime's commands.
        from app.container import get_quality_discovery_service

        return await get_quality_discovery_service().execute_run(run_id)

    @staticmethod
    def _resolve_step_inputs(value: Any, outputs: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            if set(value) == {"$output"}:
                parts = str(value["$output"]).split(".")
                resolved: Any = outputs.get(parts.pop(0), {})
                for part in parts:
                    if isinstance(resolved, dict):
                        resolved = resolved.get(part)
                    elif isinstance(resolved, list) and part.isdigit() and int(part) < len(resolved):
                        resolved = resolved[int(part)]
                    else:
                        return None
                return resolved
            return {key: TaskExecutionOrchestrator._resolve_step_inputs(item, outputs) for key, item in value.items()}
        if isinstance(value, list):
            return [TaskExecutionOrchestrator._resolve_step_inputs(item, outputs) for item in value]
        return value

    @staticmethod
    def _input(task: TaskExecutionRecord, key: str, default: Any = None) -> Any:
        return (task.inputs or {}).get(key, default)

    async def _recorder_storage_state(self, task: TaskExecutionRecord) -> dict[str, Any] | None:
        """Reuse the initiating recorder's cookies and local storage without persisting secrets in a task."""
        session_id = self._input(task, "recorder_session_id")
        if not session_id:
            return None
        from app.container import recorder_service

        session = await recorder_service.get(str(session_id), task.owner_id)
        if not session or session.project_id != task.project_id:
            return None
        return await self.browser_runtime.storage_state(session.browser_session_id)

    async def _artifact(self, task, step_key, name, kind, content, content_type):
        return await self.evidence_service.create_artifact(task, step_key, name, kind, content, content_type)

    async def _evidence(
        self, task, step_key, evidence_type, source, summary, content=None, metadata=None, artifact_id=None
    ):
        return await self.evidence_service.build_evidence(
            task, step_key, evidence_type, source, summary, content, metadata, artifact_id
        )

    async def _browser_agent_event(self, task_id, event_type, title, summary="", **kwargs):
        return await self.evidence_service.emit_browser_event(task_id, event_type, title, summary, **kwargs)

    async def _persist_browser_agent_state(self, task_id, state, **kwargs):
        return await self.evidence_service.persist_browser_state(task_id, state, **kwargs)

    async def _persist_browser_agent_artifact(self, task_id, artifact):
        return await self.evidence_service.persist_browser_artifact(task_id, artifact)

    async def _persist_browser_agent_evidence(
        self, task_id, evidence_type, source, summary, content, metadata, artifact_id=None
    ):
        return await self.evidence_service.persist_browser_evidence(
            task_id, evidence_type, source, summary, content, metadata, artifact_id
        )

    async def _record_ai_trace(self, task_id, event):
        return await self.evidence_service.record_ai_trace(task_id, event)

    async def _reserve_ai_call(self, task_id: str) -> bool:
        return await self.ai_service.reserve_ai_call(task_id)

    async def _analyze_requirement(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.ai_service._analyze_requirement(task, outputs)

    async def _call_code_ai(self, task: TaskExecutionRecord, prompt: str) -> CodeAssistantResponse:
        return await self.ai_service.call_code_ai(task, prompt)

    async def _inspect_source(self, task, outputs, path=None):
        return await self.code_generation._inspect_source(task, outputs, path)

    async def _review_source(self, task, outputs):
        return await self.code_generation._review_source(task, outputs)

    async def _review_report(self, task, outputs):
        return await self.code_generation._review_report(task, outputs)

    async def _generate_test(self, task, outputs):
        return await self.code_generation._generate_test(task, outputs)

    async def _validate_generated(self, task, outputs):
        return await self.code_generation._validate_generated(task, outputs)

    async def _request_approval(self, task, outputs):
        return await self.code_generation._request_approval(task, outputs)

    async def _write_approved_source(self, task, outputs, path, code):
        return await self.code_generation._write_approved_source(task, outputs, path, code)

    async def _write_generated(self, task, outputs):
        return await self.code_generation._write_generated(task, outputs)

    async def _generate_refactor(self, task, outputs):
        return await self.code_generation._generate_refactor(task, outputs)

    async def _materialize_goal_cases(self, task, outputs):
        return await self.goal_service._materialize_goal_cases(task, outputs)

    async def _inspect_goal_coverage(self, task, outputs):
        return await self.goal_service._inspect_goal_coverage(task, outputs)

    async def _resolve_requirement_tests(self, task, outputs):
        return await self.goal_service._resolve_requirement_tests(task, outputs)

    async def _review_project_tests(self, task, outputs):
        return await self.goal_service._review_project_tests(task, outputs)

    async def _summarize_goal(self, task, outputs):
        return await self.goal_service._summarize_goal(task, outputs)

    async def _inspect_failure_source(self, task, outputs):
        return await self.failure_repair._inspect_failure_source(task, outputs)

    async def _collect_failure(self, task, outputs):
        return await self.failure_repair._collect_failure(task, outputs)

    async def _classify_failure(self, task, outputs):
        return await self.failure_repair._classify_failure(task, outputs)

    async def _diagnose_failure(self, task, outputs):
        return await self.failure_repair._diagnose_failure(task, outputs)

    async def _prepare_repair(self, task, outputs):
        return await self.failure_repair._prepare_repair(task, outputs)

    async def _apply_repair(self, task, outputs):
        return await self.failure_repair._apply_repair(task, outputs)

    async def _validate_workspace(self, task, outputs):
        return await self.failure_repair._validate_workspace(task, outputs)

    async def _run_generated(self, task, outputs):
        return await self.test_execution._run_generated(task, outputs)

    async def _resolve_tests(self, task, outputs):
        return await self.test_execution._resolve_tests(task, outputs)

    async def _register_test_case(self, task, outputs):
        return await self.test_execution._register_test_case(task, outputs)

    async def _run_target(self, task, outputs):
        return await self.test_execution._run_target(task, outputs)

    async def _run_regression(self, task, outputs):
        return await self.test_execution._run_regression(task, outputs)

    async def _execute_pytest(self, task, nodeids, **kwargs):
        return await self.test_execution._execute_pytest(task, nodeids, **kwargs)

    async def _classify_run(self, task, outputs):
        return await self.test_execution._classify_run(task, outputs)

    async def _verify_tests(self, task, outputs):
        return await self.test_execution._verify_tests(task, outputs)

    async def _compare_test(self, task, outputs):
        return await self.test_execution._compare_test(task, outputs)

    async def _browser_agent(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.browser_executor._browser_agent(task, outputs)

    async def _browser_agent_candidates(self, task, observation, state):
        return await self.browser_executor._browser_agent_candidates(task, observation, state)

    async def _browser_inspect(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.browser_executor._browser_inspect(task, outputs)

    async def _decision_select(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.browser_executor._decision_select(task, outputs)

    async def _run_locator_decision(self, task, observed, event, candidates, pipeline, trace_run_id):
        return await self.browser_executor._run_locator_decision(
            task, observed, event, candidates, pipeline, trace_run_id
        )

    async def _browser_act(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.browser_executor._browser_act(task, outputs)

    async def _browser_verify(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        return await self.browser_executor._browser_verify(task, outputs)

    async def _execute_browser_candidate(self, browser_session_id: str, candidate: dict[str, Any]) -> None:
        return await self.browser_executor._execute_browser_candidate(browser_session_id, candidate)

    async def _run_step_tool(self, task_id: str, step: TaskStep, *, deadline: float | None = None):
        token = active_runtime_step.set(step.id)
        step_token = ai_step_scope(step.id)
        deadline_token = active_task_deadline.set(deadline)
        try:
            return await self._run_tool(task_id, step.key, step.tool)
        finally:
            active_task_deadline.reset(deadline_token)
            reset_ai_step(step_token)
            active_runtime_step.reset(token)
