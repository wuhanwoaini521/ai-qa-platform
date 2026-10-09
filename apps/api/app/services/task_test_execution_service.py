from __future__ import annotations

import ast
import asyncio
import json
import time
from typing import Any

from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    AutomationStatus,
    FrameworkType,
    RunStatus,
    TestCaseCreate,
    TestRunCreate,
)
from project_model.task_models import EvidenceType, TaskStatus, TaskType
from qa_core.failure.classifier import FailureClassifier

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts
from app.services.workspace_service import WorkspaceService


class TaskTestExecutionService:
    """Own task-driven test discovery, child runs, registration and verification."""

    def __init__(self, context: TaskExecutionPorts) -> None:
        self.context = context

    async def _resolve_tests(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        requested = self.context.input(task, "nodeids", [])
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
                await self.context.evidence(
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

    async def _run_generated(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
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
        contract = self.context.input(task, "_goal_contract", {}) or {}
        if task.type == TaskType.QA_GOAL.value and not contract.get("allow_browser", True):
            runnable, blocked = self._without_browser(task, nodeids)
            if not runnable:
                return {"status": "BLOCKED", "nodeids": [], "blocked_nodeids": blocked, "total": 0}
            result = await self._execute_pytest(task, runnable)
            return {**result, "blocked_nodeids": blocked}
        return await self._execute_pytest(task, nodeids)

    async def _register_test_case(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        """Publish a verified generated test into the existing Test Case catalog."""
        generated = outputs.get("generate", {})
        run = outputs.get("generated_run") or outputs.get("run", {})
        case_bindings = generated.get("case_bindings", [])
        if case_bindings:
            if run.get("status") != RunStatus.PASSED.value:
                return {
                    "registered": False,
                    "case_ids": [item["case_id"] for item in case_bindings],
                    "reason": "Generated tests did not all pass; no automation bindings were published.",
                    "run_id": run.get("run_id"),
                }
            nodeids = set(run.get("nodeids") or [])
            registrations = []
            blocked_case_ids = []
            async with self.context.repository_scope() as repositories:
                cases_repository = repositories.test_cases
                for item in case_bindings:
                    nodeid = f"{generated['target_file']}::{item['test_name']}"
                    if nodeid not in nodeids:
                        blocked_case_ids.append(item["case_id"])
                        continue
                    case = await cases_repository.get_by_id(item["case_id"])
                    if (
                        case is None
                        or case.project_id != task.project_id
                        or case.requirement_id != self.context.input(task, "requirement_id")
                    ):
                        raise TaskBlocked("Generated test evidence does not match its requirement case.")
                    await repositories.automation_bindings.create_or_update(
                        AutomationBindingCreate(
                            test_case_id=case.id,
                            workspace_id=task.workspace_id,
                            nodeid=nodeid,
                            file_path=generated["target_file"],
                            framework=FrameworkType.PLAYWRIGHT_PYTHON,
                            status=AutomationBindingStatus.ACTIVE,
                        )
                    )
                    await cases_repository.update_automation_status(case.id, AutomationStatus.AUTOMATED.value)
                    registrations.append({"case_id": case.id, "nodeid": nodeid})
                await repositories.commit()
            return {
                "registered": True,
                "registrations": registrations,
                "unresolved_case_ids": blocked_case_ids,
                "run_id": run.get("run_id"),
            }
        if not task.project_id or not task.workspace_id or run.get("status") != RunStatus.PASSED.value:
            raise TaskBlocked("Only a verified generated test can be registered as a Test Case.")
        nodeids = run.get("nodeids") or []
        if not nodeids or not generated.get("target_file"):
            raise TaskBlocked("Generated test has no bindable pytest node ID or file.")
        recorded_steps = self.context.input(task, "recorded_steps", []) or []
        title = str(self.context.input(task, "case_name", task.goal))[:250]
        async with self.context.repository_scope() as repositories:
            cases_repository = repositories.test_cases
            existing = (
                await cases_repository.get_by_id(str(self.context.input(task, "test_case_id")))
                if self.context.input(task, "test_case_id")
                else None
            )
            existing = existing or await cases_repository.get_by_external_case(task.project_id, "AGENT_TASK", task.id)
            if existing is None:
                existing = await cases_repository.create(
                    TestCaseCreate(
                        project_id=task.project_id,
                        title=title,
                        steps=[
                            str(step.get("description", ""))
                            for step in recorded_steps
                            if isinstance(step, dict) and step.get("description")
                        ],
                        expected_result=str(self.context.input(task, "requirement", ""))[:2000],
                        automation_status=AutomationStatus.AUTOMATED,
                        tags=["ai-generated"],
                        external_system="AGENT_TASK",
                        external_case_id=task.id,
                    )
                )
            await repositories.automation_bindings.create_or_update(
                AutomationBindingCreate(
                    test_case_id=existing.id,
                    workspace_id=task.workspace_id,
                    nodeid=str(nodeids[0]),
                    file_path=str(generated["target_file"]),
                    framework=FrameworkType.PLAYWRIGHT_PYTHON,
                    status=AutomationBindingStatus.ACTIVE,
                )
            )
            await cases_repository.update_automation_status(existing.id, AutomationStatus.AUTOMATED.value)
            await repositories.commit()
        return {"test_case_id": existing.id, "file_path": generated["target_file"], "nodeid": nodeids[0]}

    async def _run_target(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        nodeids = self.context.input(task, "nodeids", [])
        if isinstance(nodeids, str):
            nodeids = [item.strip() for item in nodeids.splitlines() if item.strip()]
        if not nodeids:
            failure = outputs.get("collect", {})
            nodeid = failure.get("test_nodeid") or self.context.input(task, "test_nodeid")
            if nodeid:
                nodeids = [nodeid]
        if not nodeids:
            raise TaskBlocked("Targeted verification requires nodeids or failure_id.")
        return await self._execute_pytest(
            task,
            nodeids[:100],
            parent_run_id=outputs.get("collect", {}).get("run_id"),
            origin_failure_id=outputs.get("collect", {}).get("id"),
        )

    async def _run_regression(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        nodeids = self.context.input(task, "regression_nodeids", []) or self.context.input(task, "nodeids", [])
        if not nodeids and task.type == TaskType.QA_GOAL.value:
            nodeids = outputs.get("resolve_tests", {}).get("nodeids", []) or outputs.get("resolve", {}).get(
                "nodeids", []
            )
        if not nodeids and task.type == TaskType.RUN_REGRESSION.value:
            nodeids = outputs.get("resolve", {}).get("nodeids", [])
        if isinstance(nodeids, str):
            nodeids = [item.strip() for item in nodeids.splitlines() if item.strip()]
        if not nodeids:
            raise TaskBlocked("Regression node IDs were not resolved.")
        nodeids = nodeids[:100]
        contract = self.context.input(task, "_goal_contract", {}) or {}
        if task.type == TaskType.QA_GOAL.value and not contract.get("allow_browser", True):
            nodeids, blocked = self._without_browser(task, nodeids)
            if not nodeids:
                return {"status": "BLOCKED", "nodeids": [], "blocked_nodeids": blocked, "total": 0}
        else:
            blocked = []
        result = await self._execute_pytest(
            task,
            nodeids,
            parent_run_id=outputs.get("collect", {}).get("run_id") or outputs.get("generated_run", {}).get("run_id"),
            origin_failure_id=outputs.get("collect", {}).get("id"),
        )
        return {**result, "blocked_nodeids": blocked}

    @staticmethod
    def _without_browser(task: TaskExecutionRecord, nodeids: list[str]) -> tuple[list[str], list[str]]:
        from qa_core.onboarding.safety import BROWSER_FIXTURES, SafetyPolicy

        policy = SafetyPolicy()
        workspace = WorkspaceService().get_workspace_dir(task.workspace_id or "")
        runnable: list[str] = []
        blocked: list[str] = []
        for nodeid in nodeids:
            reasons = policy.verdict(nodeid, workspace).reasons
            browser_dependent = any(
                "browser action" in reason
                or "module imports playwright" in reason.casefold()
                or "module imports selenium" in reason.casefold()
                or any(f"'{fixture}'" in reason for fixture in BROWSER_FIXTURES)
                for reason in reasons
            )
            (blocked if browser_dependent else runnable).append(nodeid)
        return runnable, blocked

    async def _execute_pytest(
        self,
        task: TaskExecutionRecord,
        nodeids: list[str],
        *,
        parent_run_id: str | None = None,
        origin_failure_id: str | None = None,
    ) -> dict[str, Any]:
        if not task.project_id or not task.workspace_id:
            raise TaskBlocked("Test execution requires project_id and workspace_id.")
        from app.container import open_run_service

        environment = dict(self.context.input(task, "environment", {}) or {})
        region = self.context.input(task, "region")
        if region:
            environment.setdefault("QA_REGION", str(region))
        run_data = TestRunCreate(
            project_id=task.project_id,
            workspace_id=task.workspace_id,
            nodeids=nodeids,
            browser=str(self.context.input(task, "browser", "chromium")),
            markers=self.context.input(task, "markers", []),
            runner_type=str(self.context.input(task, "runner_type", "LOCAL")),
            runner_profile_id=self.context.input(task, "runner_profile_id"),
            parallel_workers=int(self.context.input(task, "parallel_workers", 1) or 1),
            environment=environment,
            requested_by=task.owner_id,
            parent_run_id=(parent_run_id or self.context.input(task, "run_id"))
            if task.type in {TaskType.FIX_FAILURE.value, TaskType.QA_GOAL.value}
            else None,
            origin_failure_id=origin_failure_id or self.context.input(task, "failure_id")
            if task.type in {TaskType.FIX_FAILURE.value, TaskType.QA_GOAL.value}
            else None,
        )
        deadline = self.context.active_task_deadline.get() or time.monotonic() + task.max_duration_seconds
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise TaskBlocked("Task duration limit reached before starting its TestRun.")
        async with open_run_service() as service:
            create_task = asyncio.create_task(
                service.create_and_execute_run(run_data, task_id=task.id, execution_deadline=deadline)
            )
            try:
                child_run = await asyncio.shield(create_task)
            except asyncio.CancelledError:
                # create_and_execute_run may already have committed and started its worker.
                # Finish registration before propagating cancellation so the child is stoppable.
                child_run = await create_task
                self.context.child_runs[task.id] = child_run.id
                await service.cancel_run(child_run.id)
                raise
            self.context.child_runs[task.id] = child_run.id
        async with self.context.repository_scope() as repositories:
            repo = repositories.tasks
            row = await repo.get(task.id)
            if row:
                await repo.update_context(task.id, run_id=child_run.id)
                await repo.add_event(
                    task.id,
                    "step.progress",
                    {
                        "type": "child_run.started",
                        "run_id": child_run.id,
                        "nodeids": nodeids,
                        "step_id": self.context.active_runtime_step.get(),
                    },
                )
                await repositories.commit()

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
                        await self.context.evidence(
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
            active_task, _ = await self.context.load_task(task.id)
            if active_task is None or active_task.status == TaskStatus.CANCELLED.value:
                async with open_run_service() as service:
                    await service.cancel_run(child_run.id)
                raise TaskBlocked("Task was cancelled while its TestRun was executing.")
            await asyncio.sleep(0.35)
        async with open_run_service() as service:
            await service.cancel_run(child_run.id)
        raise TaskBlocked(f"Child TestRun {child_run.id} exceeded the Task verification timeout.")

    async def _classify_run(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        run = outputs.get("run", {})
        run_id = run.get("run_id")
        async with self.context.repository_scope() as repositories:
            records = await repositories.test_runs.list_failures_by_run(run_id) if run_id else []
        records_by_node = {item.test_nodeid: item for item in records}
        failures = []
        for execution in run.get("executions", []):
            if execution.get("status") == "FAILED":
                category, explanation, _ = FailureClassifier.classify(
                    execution.get("error_message") or "", execution.get("stack_trace") or ""
                )
                failures.append(
                    {
                        "nodeid": execution.get("nodeid"),
                        "failure_id": records_by_node.get(execution.get("nodeid")).id
                        if records_by_node.get(execution.get("nodeid"))
                        else None,
                        "classification": records_by_node.get(execution.get("nodeid")).classification
                        if records_by_node.get(execution.get("nodeid"))
                        and records_by_node[execution.get("nodeid")].classification
                        else category.value,
                        "root_cause": explanation,
                        "error_message": execution.get("error_message"),
                    }
                )
        first = failures[0] if failures else {}
        repairable = next(
            (item for item in failures if item.get("classification") == "LOCATOR_CHANGED" and item.get("failure_id")),
            {},
        )
        return {
            "failure_count": len(failures),
            "failures": failures,
            "first_failure_id": first.get("failure_id"),
            "repairable_failure_id": repairable.get("failure_id"),
            "_evidence": [
                await self.context.evidence(
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

    async def _verify_tests(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        verification_runs = (
            [outputs[key] for key in ("target_run", "regression") if outputs.get(key)]
            if outputs.get("target_run")
            else [outputs[key] for key in ("run", "generated_run", "regression") if outputs.get(key)]
        )
        candidate = verification_runs[-1] if verification_runs else None
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
        verified = bool(verification_runs) and all(
            run.get("status") == RunStatus.PASSED.value for run in verification_runs
        )
        result = {
            "verified": verified,
            "kind": "pytest",
            "run_id": candidate.get("run_id"),
            "status": candidate.get("status"),
            "run_ids": [run.get("run_id") for run in verification_runs if run.get("run_id")],
            "passed": sum(int(run.get("passed") or 0) for run in verification_runs),
            "failed": sum(int(run.get("failed") or 0) for run in verification_runs),
            "total": sum(int(run.get("total") or 0) for run in verification_runs),
            "runs": [
                {
                    "run_id": run.get("run_id"),
                    "status": run.get("status"),
                    "total": run.get("total"),
                    "passed": run.get("passed"),
                    "failed": run.get("failed"),
                }
                for run in verification_runs
            ],
        }
        if not verified and task.type != TaskType.QA_GOAL.value:
            statuses = ", ".join(str(run.get("status")) for run in verification_runs)
            raise TaskBlocked(f"Verification did not pass: child run status is {statuses}.")
        return {
            **result,
            "_evidence": [
                await self.context.evidence(
                    task,
                    "verify",
                    EvidenceType.TEST_RESULT,
                    "Task verification policy",
                    (
                        f"Verified child run {candidate.get('run_id')} passed."
                        if verified
                        else f"One or more child runs did not pass verification (status: {result['status']})."
                    ),
                    json.dumps(result, ensure_ascii=False),
                    result,
                )
            ],
        }

    async def _compare_test(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
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
