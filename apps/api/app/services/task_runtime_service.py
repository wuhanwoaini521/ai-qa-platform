from __future__ import annotations

import ast
import asyncio
import difflib
import hashlib
import json
import logging
import os
import re
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
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
    TaskGoalPreview,
    TaskGoalPreviewStep,
    TaskStatus,
    TaskStep,
    TaskStepStatus,
    TaskType,
)
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.context import ContextSelector
from qa_core.ai.models import AICompletionRequest, BrowserAgentPlan, CodeAssistantResponse
from qa_core.ai.registry import AIProviderRegistry
from qa_core.ai.trace import make_trace_event
from qa_core.failure.classifier import FailureClassifier
from qa_core.failure.redactor import SensitiveRedactor
from qa_core.prompts import TASK_CODE_PROMPT
from sqlalchemy import select, update

from app.persistence.database import async_session_factory
from app.persistence.models import (
    AIInvocationORM,
    AutomationBindingORM,
    FailureRecordORM,
    ProjectORM,
    RequirementORM,
    TaskArtifactORM,
    TaskORM,
    TaskStepORM,
    TestCaseORM,
    TestDesignORM,
    TestRunORM,
    WorkspaceORM,
    utc_now,
)
from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services.artifact_storage_service import ArtifactStorageService
from app.services.browser_proxy import browser_proxy_options, launch_chromium
from app.services.decision_service import DecisionService
from app.services.task_workflows import build_plan, build_qa_goal_plan, parse_qa_goal
from app.services.workspace_service import SecurityException, WorkspaceService

active_runtime_step: ContextVar[str | None] = ContextVar("active_runtime_step", default=None)
active_task_deadline: ContextVar[float | None] = ContextVar("active_task_deadline", default=None)

logger = logging.getLogger("app.task_runtime")


class TaskBlocked(RuntimeError):
    """The goal cannot continue safely without a user decision or unavailable dependency."""

    def __init__(self, message: str, *, failure_type: str = "STEP_BLOCKED", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.failure_type = failure_type
        self.details = details or {}


class ApprovalRequired(Exception):
    pass


class TaskRuntimeService:
    """Persisted, bounded DAG executor. Existing runs, browser, AI and Jev remain its tools."""

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

    def __init__(self, concurrency: int = 2, poll_interval: float = 0.5) -> None:
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self._scheduler: asyncio.Task | None = None
        self._active: dict[str, asyncio.Task] = {}
        self._child_runs: dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._create_lock = asyncio.Lock()
        self._stopping = False

    @staticmethod
    def _goal_step_title(key: str, fallback: str) -> str:
        return {
            "analyze": "理解当前需求并记录分析",
            "materialize_cases": "补充缺失测试用例",
            "coverage": "检查用例与自动化覆盖",
            "generate": "为未覆盖用例生成自动化",
            "validate": "静态验证生成的测试代码",
            "approval": "等待你确认源码修改",
            "write": "写入已批准的测试代码",
            "generated_run": "执行新生成的测试",
            "register": "关联通过的自动化与用例",
            "resolve_tests": "筛选当前需求的现有自动化",
            "resolve": "定位当前范围内的自动化测试",
            "run": "执行目标测试",
            "run_classify": "归类测试失败与环境问题",
            "collect": "收集失败与运行证据",
            "classify": "判断失败类型",
            "inspect": "检查相关测试代码",
            "diagnose": "基于证据分析失败原因",
            "repair": "准备最小修复方案",
            "apply": "应用已批准的修复",
            "target_run": "重跑失败的目标测试",
            "regression": "执行指定回归范围",
            "verify": "验证最终测试结果",
            "review": "检查测试结构与断言质量",
            "report": "整理代码审查发现",
            "review_project": "检查项目测试质量",
            "goal_summary": "汇总工作、发现和证据",
            "browser_agent": "理解页面并执行浏览目标",
        }.get(key, fallback)

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

    async def preview_goal(self, data: TaskCreate) -> TaskGoalPreview:
        if data.type != TaskType.QA_GOAL:
            raise ValueError("Goal preview requires type=QA_GOAL.")
        if not data.project_id or not data.workspace_id:
            raise ValueError("Choose a project workspace before planning a QA goal.")
        request_inputs_hash = self._goal_request_inputs_hash(data.inputs)
        contract, facts, plan = await self._compile_goal(data)
        plan_token = self._goal_preview_token(data, contract, facts, plan, request_inputs_hash=request_inputs_hash)
        effects = []
        if any(step.tool == "goal.materialize_cases" for step in plan):
            effects.append("创建缺失的 Test Design / Test Case 记录")
        if any(step.tool == "tests.generate" for step in plan):
            effects.append("生成自动化测试草案")
        if any(step.tool in {"source.write_generated", "source.apply_repair"} for step in plan):
            effects.append("写入测试源码（执行前需要你批准）")
        if any(step.tool.startswith("tests.run") for step in plan):
            effects.append("运行目标 pytest 用例")
        if any(step.tool.startswith("browser.") for step in plan):
            effects.append("读取页面并执行受限浏览器操作")
        constraints = []
        if not contract["allow_source_changes"]:
            constraints.append("不修改源码")
        if not contract["run_tests"]:
            constraints.append("不运行测试")
        if not contract["allow_browser"]:
            constraints.append("不使用浏览器")
        if contract.get("no_full_regression"):
            constraints.append("不跑全量回归")
        return TaskGoalPreview(
            goal=data.goal,
            plan_token=plan_token,
            context=facts["context_label"],
            steps=[
                TaskGoalPreviewStep(
                    title=self._goal_step_title(step.key, step.name),
                    conditional=bool(step.when),
                    risk=(
                        "HIGH"
                        if step.tool in {"source.write_generated", "source.apply_repair"}
                        else "MEDIUM"
                        if step.tool.startswith("tests.run")
                        or step.tool == "tests.generate"
                        or step.tool == "goal.materialize_cases"
                        or step.tool == "browser.act"
                        else "LOW"
                    ),
                )
                for step in plan
            ],
            effects=effects,
            approval_required=any(step.tool == "task.request_approval" for step in plan),
            constraints=constraints,
        )

    @staticmethod
    def _goal_request_inputs_hash(inputs: dict[str, Any]) -> str:
        request_inputs = {key: value for key, value in inputs.items() if not key.startswith("_")}
        encoded = json.dumps(request_inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _goal_preview_token(
        data: TaskCreate,
        contract: dict[str, Any],
        facts: dict[str, Any],
        plan: list[Any],
        *,
        request_inputs_hash: str | None = None,
    ) -> str:
        payload = {
            "goal": data.goal,
            "project_id": data.project_id,
            "execution_limits": {
                "max_steps": data.max_steps,
                "max_retries": data.max_retries,
                "max_replans": data.max_replans,
                "max_ai_calls": data.max_ai_calls,
                "max_duration_seconds": data.max_duration_seconds,
            },
            "inputs_hash": request_inputs_hash or TaskRuntimeService._goal_request_inputs_hash(data.inputs),
            "contract": contract,
            "facts": facts,
            "plan": [step.model_dump(mode="json") for step in plan],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _compile_goal(self, data: TaskCreate):
        contract = parse_qa_goal(data.goal, data.inputs)
        async with async_session_factory() as session:
            project = await session.get(ProjectORM, data.project_id)
            if project is None:
                raise ValueError("Project not found.")
            workspace_row = await session.get(WorkspaceORM, data.workspace_id)
            if workspace_row is None:
                workspace_row = await session.scalar(
                    select(WorkspaceORM).where(WorkspaceORM.project_id == data.workspace_id)
                )
            if workspace_row is None or workspace_row.project_id != data.project_id:
                raise ValueError("Workspace does not belong to the selected project.")

            facts: dict[str, Any] = {
                "analysis_ready": False,
                "case_count": 0,
                "unbound_case_count": 0,
                "unbound_case_ids": [],
                "nodeids": [],
                "regression_nodeids": data.inputs.get("regression_nodeids", []),
                "context_label": project.name or data.project_id,
                "workspace_snapshot_hash": self._workspace_source_digest(workspace_row.project_id),
            }
            if contract["target"] == "requirement" and contract["requirement_id"]:
                requirement = await session.get(RequirementORM, contract["requirement_id"])
                if requirement is None or requirement.project_id != data.project_id:
                    raise ValueError("Requirement not found in the selected project.")
                raw = requirement.qa_model or {}
                history = raw.get("history") or []
                facts.update(
                    {
                        "context_label": f"{requirement.external_id or requirement.id[:8]} · {requirement.title}",
                        "requirement_title": requirement.title,
                        "analysis_ready": bool(
                            raw.get("analysis") and history and history[-1].get("status") == "SUCCESS"
                        ),
                    }
                )
                designs = list(
                    (
                        await session.scalars(
                            select(TestDesignORM).where(TestDesignORM.requirement_id == requirement.id)
                        )
                    ).all()
                )
                cases = list(
                    (
                        await session.scalars(
                            select(TestCaseORM).where(
                                TestCaseORM.requirement_id == requirement.id,
                                TestCaseORM.project_id == data.project_id,
                            )
                        )
                    ).all()
                )
                case_ids = [case.id for case in cases]
                bindings = list(
                    (
                        await session.scalars(
                            select(AutomationBindingORM).where(
                                AutomationBindingORM.test_case_id.in_(case_ids or [""]),
                                AutomationBindingORM.status == AutomationBindingStatus.ACTIVE.value,
                            )
                        )
                    ).all()
                )
                bound_ids = {item.test_case_id for item in bindings}
                facts.update(
                    {
                        "design_count": len(designs),
                        "case_count": len(cases),
                        "unbound_case_ids": [case.id for case in cases if case.id not in bound_ids],
                        "unbound_case_count": sum(case.id not in bound_ids for case in cases),
                        "nodeids": [item.nodeid for item in bindings],
                        "context_hash": self._goal_request_inputs_hash(
                            {
                                "requirement": {
                                    "title": requirement.title,
                                    "description": requirement.description,
                                    "acceptance_criteria": requirement.acceptance_criteria,
                                    "qa_model": raw,
                                },
                                "designs": [
                                    {
                                        "id": item.id,
                                        "title": item.title,
                                        "category": item.category,
                                        "description": item.description,
                                        "risk": item.risk,
                                        "scenario_model": item.scenario_model,
                                        "status": item.status,
                                    }
                                    for item in designs
                                ],
                                "cases": [
                                    {
                                        "id": item.id,
                                        "title": item.title,
                                        "preconditions": item.preconditions,
                                        "steps": item.steps,
                                        "expected_result": item.expected_result,
                                        "test_model": item.test_model,
                                        "priority": item.priority,
                                        "automation_status": item.automation_status,
                                    }
                                    for item in cases
                                ],
                                "bindings": [
                                    {"case_id": item.test_case_id, "nodeid": item.nodeid, "file_path": item.file_path}
                                    for item in bindings
                                ],
                            }
                        ),
                    }
                )
                if contract["test_case_id"]:
                    case = next((item for item in cases if item.id == contract["test_case_id"]), None)
                    if case is None:
                        raise ValueError("Selected case does not belong to the selected requirement.")
            elif contract["target"] == "case" and contract["test_case_id"]:
                case = await session.get(TestCaseORM, contract["test_case_id"])
                if case is None or case.project_id != data.project_id:
                    raise ValueError("Selected test case not found in the selected project.")
                if (
                    case.requirement_id
                    and contract["requirement_id"]
                    and contract["requirement_id"] != case.requirement_id
                ):
                    raise ValueError("Selected test case belongs to a different requirement.")
                binding = await session.scalar(
                    select(AutomationBindingORM).where(
                        AutomationBindingORM.test_case_id == case.id,
                        AutomationBindingORM.status == AutomationBindingStatus.ACTIVE.value,
                    )
                )
                facts["context_label"] = case.title
                facts["case_count"] = 1
                facts["nodeids"] = [binding.nodeid] if binding else []
                facts["context_hash"] = self._goal_request_inputs_hash(
                    {
                        "title": case.title,
                        "preconditions": case.preconditions,
                        "steps": case.steps,
                        "expected_result": case.expected_result,
                        "test_model": case.test_model or {},
                        "requirement_id": case.requirement_id,
                        "binding": {"nodeid": binding.nodeid, "file_path": binding.file_path} if binding else None,
                    }
                )
                data.inputs = {
                    **data.inputs,
                    "file_path": data.inputs.get("file_path") or (binding.file_path if binding else None),
                    "nodeids": data.inputs.get("nodeids") or ([binding.nodeid] if binding else []),
                    "case_context": {
                        "title": case.title,
                        "preconditions": case.preconditions,
                        "steps": case.steps,
                        "expected_result": case.expected_result,
                        "test_model": case.test_model or {},
                        "requirement_id": case.requirement_id,
                    },
                }
            elif contract["target"] == "failure" and contract["failure_id"]:
                failure = await session.get(FailureRecordORM, contract["failure_id"])
                run = await session.get(TestRunORM, failure.run_id) if failure else None
                if failure is None or run is None or run.project_id != data.project_id:
                    raise ValueError("Selected failure not found in the selected project.")
                facts["context_label"] = f"{failure.test_name or failure.test_nodeid} · {failure.id[:8]}"
            elif contract["target"] == "project":
                facts["context_label"] = project.name or data.project_id

        plan = build_qa_goal_plan(contract, facts)
        if not plan:
            raise ValueError("This goal has no safe, registered capability for the selected context.")
        return contract, facts, plan

    async def create(self, data: TaskCreate, owner_id: str) -> Task:
        if data.type != TaskType.QA_GOAL or not data.idempotency_key:
            return await self._create(data, owner_id)
        async with self._create_lock:
            data.inputs = {**data.inputs, "_idempotency_key": data.idempotency_key}
            async with async_session_factory() as session:
                rows = list(
                    (
                        await session.scalars(
                            select(TaskORM)
                            .where(
                                TaskORM.owner_id == owner_id,
                                TaskORM.project_id == data.project_id,
                                TaskORM.type == TaskType.QA_GOAL.value,
                            )
                            .order_by(TaskORM.created_at.desc())
                            .limit(100)
                        )
                    ).all()
                )
                existing = next(
                    (row for row in rows if (row.inputs or {}).get("_idempotency_key") == data.idempotency_key),
                    None,
                )
                if existing:
                    return Task(**TaskRepository(session).task_values(existing))
            return await self._create(data, owner_id)

    async def _create(self, data: TaskCreate, owner_id: str) -> Task:
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
        if data.type == TaskType.ANALYZE_REQUIREMENT:
            requirement_id = str(data.inputs.get("requirement_id") or "").strip()
            if not requirement_id:
                raise ValueError("ANALYZE_REQUIREMENT requires inputs.requirement_id")
            async with async_session_factory() as session:
                requirement = await session.get(RequirementORM, requirement_id)
                if requirement is None:
                    raise ValueError("Requirement not found")
                if requirement.project_id != data.project_id:
                    raise ValueError("Requirement does not belong to the selected project")
        goal_request_inputs_hash = (
            self._goal_request_inputs_hash(data.inputs) if data.type == TaskType.QA_GOAL else None
        )
        if data.inputs.get("test_case_id"):
            async with async_session_factory() as session:
                case = await session.get(TestCaseORM, str(data.inputs["test_case_id"]))
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
            "context": {"ai_calls": 0, "tool_calls": 0},
            "verification": {},
            "retry_count": 0,
            "replan_count": 0,
            "max_steps": data.max_steps,
            "max_retries": data.max_retries,
            "max_replans": data.max_replans,
            "max_ai_calls": min(
                data.max_ai_calls, int((AIProviderRegistry._runtime_config or {}).get("max_task_calls", "8"))
            ),
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
            steps = await repo.get_steps_for_tasks([row.id for row in rows])
            return [
                Task(
                    **repo.task_values(row),
                    plan=[TaskStep.model_validate(step, from_attributes=True) for step in steps.get(row.id, [])],
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
            next_status = TaskStatus.PENDING.value if request.approved else TaskStatus.BLOCKED.value
            now = utc_now()
            claimed = await session.execute(
                update(TaskORM)
                .where(
                    TaskORM.id == task.id,
                    TaskORM.owner_id == owner_id,
                    TaskORM.status == TaskStatus.WAITING.value,
                    TaskORM.current_step_id == step.id,
                )
                .values(
                    status=next_status,
                    failure_reason=None if request.approved else "User rejected the proposed workspace change.",
                    finished_at=None if request.approved else now,
                    updated_at=now,
                )
            )
            if claimed.rowcount != 1:
                await session.rollback()
                return None
            if request.approved:
                step.status = TaskStepStatus.COMPLETED.value
                step.outputs = {"approved": True, "comment": request.comment}
                event_type = "decision.created"
            else:
                step.status = TaskStepStatus.SKIPPED.value
                step.outputs = {"approved": False, "comment": request.comment}
                event_type = "task.blocked"
            step.finished_at = utc_now()
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

    @staticmethod
    def _workspace_source_snapshot(workspace_id: str | None) -> dict[str, str]:
        if not workspace_id:
            return {}
        workspace = WorkspaceService()
        root = workspace.get_workspace_dir(workspace_id)
        snapshot: dict[str, str] = {}
        for directory, names, files in os.walk(root, followlinks=False):
            names[:] = [
                name
                for name in names
                if name
                not in {
                    ".git",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".mypy_cache",
                    ".venv",
                    "venv",
                    "node_modules",
                    "dist",
                    "build",
                    "coverage",
                    ".cache",
                    "runtime",
                    "artifacts",
                }
                and not name.startswith(".tmp")
            ]
            for name in files:
                relative_path = (Path(directory) / name).relative_to(root).as_posix()
                try:
                    path = workspace._resolve_safe_file_path(workspace_id, relative_path)
                except (FileNotFoundError, OSError, SecurityException, ValueError):
                    continue
                digest = hashlib.sha256()
                try:
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(chunk)
                except OSError:
                    continue
                snapshot[relative_path] = digest.hexdigest()
        return snapshot

    @staticmethod
    def _workspace_source_digest(workspace_id: str | None) -> str:
        snapshot = TaskRuntimeService._workspace_source_snapshot(workspace_id)
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def pause(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
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
                task.context = {
                    **(task.context or {}),
                    "pause_workspace_snapshot": self._workspace_source_snapshot(task.workspace_id),
                }
                task.status = TaskStatus.PAUSED.value
                task.finished_at = None
                await repo.add_event(task.id, "task.paused", {"boundary": "before_start"})
            else:
                task.status = TaskStatus.PAUSING.value
                await repo.add_event(task.id, "task.pause_requested", {"boundary": "after_current_step"})
            task.updated_at = utc_now()
            await session.commit()
        return await self.get(task_id, owner_id)

    async def resume(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with async_session_factory() as session:
            claimed = await session.execute(
                update(TaskORM)
                .where(
                    TaskORM.id == task_id,
                    TaskORM.owner_id == owner_id,
                    TaskORM.status == TaskStatus.PAUSED.value,
                )
                .values(status=TaskStatus.RESUMING.value, updated_at=utc_now())
            )
            if claimed.rowcount != 1:
                return None
            await session.commit()
        try:
            return await self._resume_claimed(task_id, owner_id)
        except BaseException:
            async with async_session_factory() as session:
                await session.execute(
                    update(TaskORM)
                    .where(
                        TaskORM.id == task_id,
                        TaskORM.owner_id == owner_id,
                        TaskORM.status == TaskStatus.RESUMING.value,
                    )
                    .values(status=TaskStatus.PAUSED.value, updated_at=utc_now())
                )
                await session.commit()
            raise

    async def _resume_claimed(self, task_id: str, owner_id: str) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id, owner_id)
            if not task or task.status != TaskStatus.RESUMING.value:
                return None

            before = (task.context or {}).get("pause_workspace_snapshot", {})
            current = self._workspace_source_snapshot(task.workspace_id)
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
                for key in invalidated_steps:
                    row = existing[key]
                    row.status = TaskStepStatus.PENDING.value
                    row.outputs = {}
                    row.evidence_ids = []
                    row.error = None
                    row.started_at = None
                    row.finished_at = None
                    row.duration_ms = 0
                    row.retry_count = 0
                for row in rows:
                    if row.status == TaskStepStatus.PENDING.value and row.key not in fresh_by_key:
                        row.status = TaskStepStatus.SKIPPED.value
                        row.outputs = {"skipped": True, "reason": "Plan refreshed from current project state."}
                        row.finished_at = utc_now()
                completed_positions = [
                    row.position
                    for row in rows
                    if row.status in {TaskStepStatus.COMPLETED.value, TaskStepStatus.SKIPPED.value}
                ]
                next_position = max(completed_positions, default=-1) + 1
                for spec in fresh_plan:
                    row = existing.get(spec.key)
                    if row and row.status != TaskStepStatus.PENDING.value:
                        continue
                    values = {
                        "name": spec.name,
                        "tool": spec.tool,
                        "dependencies": spec.depends_on,
                        "condition": spec.when,
                        "inputs": spec.inputs,
                    }
                    if row:
                        for key, value in values.items():
                            setattr(row, key, value)
                        row.position = next_position
                    else:
                        row = TaskStepORM(
                            id=uuid4().hex,
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
                        session.add(row)
                        existing[spec.key] = row
                    next_position += 1
                task.inputs = {
                    **(task.inputs or {}),
                    "_goal_contract": contract,
                    "_goal_plan_token": fresh_token,
                    "_goal_request_inputs_hash": request_inputs_hash or self._goal_request_inputs_hash(data.inputs),
                }
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
                for key in invalidated_steps:
                    row = by_key[key]
                    row.status = TaskStepStatus.PENDING.value
                    row.outputs = {}
                    row.evidence_ids = []
                    row.error = None
                    row.started_at = None
                    row.finished_at = None
                    row.duration_ms = 0
                    row.retry_count = 0
                if invalidated_steps:
                    plan_refreshed = True
                    await repo.add_event(
                        task.id,
                        "task.context_refreshed",
                        {"changed_files": changed, "invalidated_steps": invalidated_steps},
                    )

            current_step = await session.get(TaskStepORM, task.current_step_id) if task.current_step_id else None
            resumed_status = (
                TaskStatus.WAITING.value
                if current_step and current_step.status == TaskStepStatus.WAITING_FOR_APPROVAL.value
                else TaskStatus.PENDING.value
            )
            task.context = {
                **(task.context or {}),
                "pause_workspace_snapshot": current,
                "workspace_changes_on_resume": changed,
            }
            await repo.add_event(
                task.id,
                "task.resumed",
                {"changed_files": changed, "workspace_files": len(current), "plan_refreshed": plan_refreshed},
            )
            transition = await session.execute(
                update(TaskORM)
                .where(
                    TaskORM.id == task.id,
                    TaskORM.owner_id == owner_id,
                    TaskORM.status == TaskStatus.RESUMING.value,
                )
                .values(
                    status=resumed_status,
                    context=task.context,
                    failure_reason=None,
                    finished_at=None,
                    updated_at=utc_now(),
                )
            )
            if transition.rowcount != 1:
                await session.rollback()
                return await self.get(task_id, owner_id)
            await session.commit()
        return await self.get(task_id, owner_id)

    async def replan(self, task_id: str, owner_id: str, instructions: str) -> TaskDetail | None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id, owner_id)
            if not task or task.status not in {TaskStatus.BLOCKED.value, TaskStatus.FAILED.value}:
                return None
            if task.replan_count >= task.max_replans:
                raise ValueError("Task replan limit reached")
            next_replan_count = task.replan_count + 1

            claimed = await session.execute(
                update(TaskORM)
                .where(
                    TaskORM.id == task.id,
                    TaskORM.owner_id == owner_id,
                    TaskORM.status.in_([TaskStatus.BLOCKED.value, TaskStatus.FAILED.value]),
                    TaskORM.replan_count == task.replan_count,
                    TaskORM.replan_count < TaskORM.max_replans,
                )
                .values(
                    status=TaskStatus.REPLANNING.value,
                    replan_count=TaskORM.replan_count + 1,
                    retry_count=TaskORM.retry_count + 1,
                    inputs={**task.inputs, "replan_instructions": instructions[:4000]},
                    failure_reason=None,
                    finished_at=None,
                    current_step_id=None,
                    updated_at=utc_now(),
                )
            )
            if claimed.rowcount != 1:
                await session.rollback()
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
                    step.status = TaskStepStatus.PENDING.value
                    step.error = None
                    step.outputs = {}
                    step.finished_at = None
                    step.started_at = None
                    # The column is non-null; without a started/finished timestamp the
                    # runtime projection treats this stored placeholder as unavailable.
                    step.duration_ms = 0
                    step.retry_count = (step.retry_count or 0) + 1
            await repo.add_event(
                task.id, "task.replanning", {"instructions": instructions[:4000], "replan_count": next_replan_count}
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
            task, _ = await self._load(task_id)
            if not task:
                return
            worker_started = time.monotonic()
            elapsed_before = max(0.0, float((task.context or {}).get("_execution_elapsed_seconds", 0)))
            execution_started = worker_started - elapsed_before
            try:
                await self._execute_dag(task_id, execution_started)
            except asyncio.CancelledError:
                # The API lifespan owns process-level cancellation; recover_interrupted will
                # mark the task BLOCKED on the next start if it was not user-cancelled.
                raise
            except Exception as error:
                await self._finish(task_id, TaskStatus.FAILED, str(error))
            finally:
                await self._persist_execution_elapsed(task_id, time.monotonic() - execution_started)

    async def _persist_execution_elapsed(self, task_id: str, elapsed: float) -> None:
        async with async_session_factory() as session:
            task = await TaskRepository(session).get(task_id)
            if not task:
                return
            context = task.context or {}
            task.context = {
                **context,
                "_execution_elapsed_seconds": max(
                    max(0.0, float(context.get("_execution_elapsed_seconds", 0))),
                    max(0.0, elapsed),
                ),
            }
            await session.commit()

    async def _execute_dag(self, task_id: str, started: float) -> None:
        while True:
            task, steps = await self._load(task_id)
            if (
                not task
                or task.status in self.TERMINAL
                or task.status in {TaskStatus.WAITING.value, TaskStatus.PAUSED.value}
            ):
                return
            if task.status == TaskStatus.PAUSING.value:
                await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started)
                return
            deadline = started + task.max_duration_seconds
            if time.monotonic() >= deadline:
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
                if await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started):
                    return
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
            results = await asyncio.gather(
                *(self._execute_step(task, step, deadline=deadline) for step in batch), return_exceptions=True
            )
            failed = any(
                isinstance(result, TaskBlocked)
                or isinstance(result, BaseException)
                and not isinstance(result, ApprovalRequired)
                for result in results
            )
            if not failed and await self._pause_at_boundary(task_id, elapsed_seconds=time.monotonic() - started):
                return
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

    async def _pause_at_boundary(self, task_id: str, *, elapsed_seconds: float = 0.0) -> bool:
        task, _ = await self._load(task_id)
        if not task or task.status != TaskStatus.PAUSING.value:
            return False
        snapshot = self._workspace_source_snapshot(task.workspace_id)
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            current = await repo.get(task_id)
            if not current or current.status in self.TERMINAL or current.status != TaskStatus.PAUSING.value:
                return False
            current.context = {
                **(current.context or {}),
                "pause_workspace_snapshot": snapshot,
                "_execution_elapsed_seconds": max(
                    max(0.0, float((current.context or {}).get("_execution_elapsed_seconds", 0))),
                    max(0.0, elapsed_seconds),
                ),
            }
            current.status = TaskStatus.PAUSED.value
            current.finished_at = None
            current.updated_at = utc_now()
            await repo.add_event(
                task_id,
                "task.paused",
                {
                    "boundary": "after_current_step",
                    "step_id": current.current_step_id,
                    "workspace_files": len(snapshot),
                },
            )
            await session.commit()
        return True

    async def _load(self, task_id: str) -> tuple[TaskORM | None, list[TaskStepORM]]:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            return task, await repo.steps_for_task(task_id) if task else []

    async def _execute_step(
        self, task: TaskORM, step: TaskStepORM, *, deadline: float | None = None
    ) -> dict[str, Any] | ApprovalRequired | TaskBlocked:
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
            async with async_session_factory() as session:
                await TaskRepository(session).add_event(
                    task.id,
                    "task.plan_changed",
                    {"step_id": step.id, "step_key": step.key, "reason": reason},
                )
                await session.commit()
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
                if fresh.status == TaskStatus.PAUSING.value:
                    return {"deferred_for_pause": True}
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
                outputs = await self._run_step_tool(task.id, step, deadline=deadline)
            except ApprovalRequired:
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    current_task = await repo.get(task.id)
                    if (
                        not current_task
                        or current_task.status not in {TaskStatus.RUNNING.value, TaskStatus.PAUSING.value}
                        or current_task.current_step_id != step.id
                    ):
                        await session.rollback()
                        return ApprovalRequired()
                    next_status = (
                        TaskStatus.PAUSING.value
                        if current_task.status == TaskStatus.PAUSING.value
                        else TaskStatus.WAITING.value
                    )
                    task_claim = await session.execute(
                        update(TaskORM)
                        .where(
                            TaskORM.id == task.id,
                            TaskORM.owner_id == current_task.owner_id,
                            TaskORM.status == current_task.status,
                            TaskORM.current_step_id == step.id,
                        )
                        .values(status=next_status, current_step_id=step.id, updated_at=utc_now())
                    )
                    step_claim = await session.execute(
                        update(TaskStepORM)
                        .where(TaskStepORM.id == step.id, TaskStepORM.status == TaskStepStatus.RUNNING.value)
                        .values(status=TaskStepStatus.WAITING_FOR_APPROVAL.value)
                    )
                    if task_claim.rowcount != 1 or step_claim.rowcount != 1:
                        await session.rollback()
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
                    await session.commit()
                return ApprovalRequired()
            except TaskBlocked as error:
                elapsed = (time.perf_counter() - started) * 1000
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    current = await session.get(TaskStepORM, step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        current.status = TaskStepStatus.FAILED.value
                        current.error = SensitiveRedactor.redact_text(str(error))[:4000]
                        current.duration_ms = elapsed
                        current.finished_at = utc_now()
                        current.outputs = SensitiveRedactor.redact_value(
                            {"failure_type": error.failure_type, **error.details}
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
                    current.error = SensitiveRedactor.redact_text(str(error))[:4000]
                    current.duration_ms = elapsed
                    await repo.add_event(
                        task.id,
                        "step.failed",
                        {
                            "step_id": step.id,
                            "error": SensitiveRedactor.redact_text(str(error))[:1000],
                            "retry": current.retry_count,
                        },
                    )
                    if (
                        step.tool
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
                        and current.retry_count <= min(current.max_retries, fresh.max_retries)
                        and fresh.retry_count < fresh.max_retries
                    ):
                        fresh.retry_count += 1
                        current.status = TaskStepStatus.PENDING.value
                        if fresh.status != TaskStatus.PAUSING.value:
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

            if outputs.pop("_pause_after_step", False):
                async with async_session_factory() as session:
                    repo = TaskRepository(session)
                    current = await session.get(TaskStepORM, step.id)
                    if current and current.status == TaskStepStatus.RUNNING.value:
                        current.status = TaskStepStatus.PENDING.value
                        current.finished_at = None
                        current.outputs = {}
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
                        await session.commit()
                return {"deferred_for_pause": True}

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
            task.inputs = {**(task.inputs or {}), **self._resolve_step_inputs(active.inputs, outputs)}
        dispatch = {
            "requirement.analyze": self._analyze_requirement,
            "goal.materialize_cases": self._materialize_goal_cases,
            "goal.coverage": self._inspect_goal_coverage,
            "goal.summary": self._summarize_goal,
            "goal.review_project": self._review_project_tests,
            "browser.inspect": self._browser_inspect,
            "browser.act": self._browser_act,
            "browser.agent": self._browser_agent,
            "browser.verify": self._browser_verify,
            "decision.select_candidate": self._decision_select,
            "tests.generate": self._generate_test,
            "source.validate_generated": self._validate_generated,
            "task.request_approval": self._request_approval,
            "source.write_generated": self._write_generated,
            "tests.run_generated": self._run_generated,
            "tests.resolve": self._resolve_tests,
            "tests.resolve_requirement": self._resolve_requirement_tests,
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
            return {key: TaskRuntimeService._resolve_step_inputs(item, outputs) for key, item in value.items()}
        if isinstance(value, list):
            return [TaskRuntimeService._resolve_step_inputs(item, outputs) for item in value]
        return value

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
            "content": SensitiveRedactor.redact_text(content[:24000]) if content else None,
            "metadata": SensitiveRedactor.redact_value(metadata or {}),
            "artifact_id": artifact_id,
        }

    async def _browser_agent_event(
        self,
        task_id: str,
        event_type: str,
        title: str,
        summary: str = "",
        *,
        status: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "step_id": active_runtime_step.get(),
            "title": SensitiveRedactor.redact_text(title)[:200],
            "summary": SensitiveRedactor.redact_text(summary)[:500],
            "status": status,
            "duration_ms": duration_ms,
            **SensitiveRedactor.redact_value(metadata or {}),
        }
        async with async_session_factory() as session:
            await TaskRepository(session).add_event(task_id, event_type, payload)
            await session.commit()

    async def _persist_browser_agent_state(
        self,
        task_id: str,
        state: dict[str, Any],
        *,
        title: str,
        summary: str,
        status: str = "RUNNING",
        event_type: str = "browser.agent_progress",
    ) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get(task_id)
            if task is None:
                raise TaskBlocked("Browser task no longer exists.")
            task.context = {
                **(task.context or {}),
                "browser_agent": SensitiveRedactor.redact_value(state),
            }
            await repo.add_event(
                task_id,
                event_type,
                {
                    "step_id": active_runtime_step.get(),
                    "title": SensitiveRedactor.redact_text(title)[:200],
                    "summary": SensitiveRedactor.redact_text(summary)[:500],
                    "status": status,
                    "current_url": SensitiveRedactor.redact_url(str(state.get("current_url") or ""))[:500],
                    "action_count": len(state.get("history") or []),
                    "goal_completed": bool((state.get("metrics") or {}).get("goal_completion")),
                },
            )
            await session.commit()

    async def _persist_browser_agent_artifact(self, task_id: str, artifact: dict[str, Any]) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            await repo.add_artifact(
                task_id=task_id,
                step_id=active_runtime_step.get(),
                artifact_id=artifact["artifact_id"],
                name=artifact["name"],
                kind=artifact["kind"],
            )
            await repo.add_event(
                task_id,
                "artifact.created",
                {
                    "step_id": active_runtime_step.get(),
                    "artifact_id": artifact["artifact_id"],
                    "name": artifact["name"],
                },
            )
            await session.commit()

    async def _persist_browser_agent_evidence(
        self,
        task_id: str,
        evidence_type: EvidenceType,
        source: str,
        summary: str,
        content: str,
        metadata: dict[str, Any],
        artifact_id: str | None = None,
    ) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.add_evidence(
                task_id=task_id,
                step_id=active_runtime_step.get(),
                type=evidence_type.value,
                source=source,
                summary=SensitiveRedactor.redact_text(summary)[:500],
                content=SensitiveRedactor.redact_text(content[:24000]) if content else None,
                metadata_json=SensitiveRedactor.redact_value(metadata),
                artifact_id=artifact_id,
            )
            await repo.add_event(
                task_id,
                "evidence.created",
                {"step_id": active_runtime_step.get(), "evidence_id": row.id, "type": evidence_type.value},
            )
            await session.commit()

    @staticmethod
    async def _observe_browser_page(
        page: Any,
        network: dict[str, int],
        *,
        waited_loading_states: set[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        try:
            statuses = page.locator('[role="status"]')
            for index in range(min(await statuses.count(), 5)):
                status = statuses.nth(index)
                status_text = await status.inner_text(timeout=500)
                state_key = (page.url, status_text.casefold())
                if re.search(r"\bloading\b|正在加载|加载中", status_text, re.I) and (
                    waited_loading_states is None or state_key not in waited_loading_states
                ):
                    if waited_loading_states is not None:
                        waited_loading_states.add(state_key)
                    await status.wait_for(state="hidden", timeout=2000)
                    break
        except PlaywrightTimeoutError:
            pass

        title = await page.title()
        url = page.url
        try:
            body = (await page.locator("body").inner_text(timeout=3000))[:8000]
        except PlaywrightTimeoutError:
            body = ""
        try:
            accessibility_tree = (await page.locator("body").aria_snapshot(timeout=3000))[:16000]
        except Exception:
            accessibility_tree = ""
        scroll_state = await page.evaluate(
            """() => ({
              scroll_y: Math.round(window.scrollY),
              scroll_height: document.documentElement.scrollHeight,
              viewport_height: window.innerHeight
            })"""
        )
        elements = await page.locator(
            "a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=link],[role=combobox],[role=option]"
        ).evaluate_all(
            r"""els => els.slice(0,100).map((el,index) => {
              const tag=el.tagName.toLowerCase(), type=(el.getAttribute('type') || (tag==='input' || (tag==='button' && el.form) ? el.type : '') || '').toLowerCase();
              const style=getComputedStyle(el), rect=el.getBoundingClientRect();
              const visible=style.visibility!=='hidden' && style.display!=='none' && rect.width>0 && rect.height>0;
              const role=el.getAttribute('role') || (tag==='a'?'link':tag==='button'?'button':tag==='select'?'combobox':['input','textarea'].includes(tag)?'textbox':null);
              const label=(el.labels?.length ? Array.from(el.labels).map(x=>x.innerText).join(' ') : '').trim().replace(/\s+/g,' ').slice(0,120);
              const name=(el.getAttribute('aria-label') || label || el.getAttribute('alt') || el.innerText || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().replace(/\s+/g,' ').slice(0,160);
              const safeInput=['search','text','number'].includes(type) || tag==='textarea';
              const value=tag==='select' ? (el.selectedOptions[0]?.textContent || '').trim().slice(0,100) : safeInput ? String(el.value || '').slice(0,120) : '';
              const options=tag==='select' ? Array.from(el.options).slice(0,30).map(o=>({value:o.value,label:(o.textContent||'').trim().slice(0,100),enabled:!o.disabled})) : [];
              return {
                id:`el_${index}`, tag, role, name, label, type,
                href:el instanceof HTMLAnchorElement ? el.href : (el.getAttribute('href') || ''),
                href_selector:(el.getAttribute('href') || ''),
                placeholder:(el.getAttribute('placeholder') || '').slice(0,120),
                test_id:(el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-qa') || '').slice(0,120),
                stable_id:(el.id || '').slice(0,120), value, options,
                visible, enabled:!el.disabled && el.getAttribute('aria-disabled')!=='true',
                selected:el.checked===true || el.getAttribute('aria-pressed')==='true' || el.getAttribute('aria-selected')==='true',
                expanded:el.getAttribute('aria-expanded'),
              };
            }).filter(el => el.visible)"""
        )
        safe_controls = [
            {
                **{key: value for key, value in item.items() if key != "href_selector"},
                "_href": item.get("href") or "",
                "_href_selector": item.get("href_selector") or "",
                "href": SensitiveRedactor.redact_url(str(item.get("href") or ""))[:500],
            }
            for item in elements
        ]
        state = {
            "url": SensitiveRedactor.redact_url(url)[:500],
            "title": title[:200],
            "text": body,
            "accessibility_tree": accessibility_tree,
            "elements": safe_controls,
            "network": dict(network),
            "scroll": scroll_state,
        }
        fingerprint = {
            "url": state["url"],
            "title": state["title"],
            "text": body[:1600],
            "scroll": scroll_state,
            "elements": [
                {key: item.get(key) for key in ("role", "name", "href", "value", "selected", "expanded")}
                for item in safe_controls[:50]
            ],
        }
        state["state_hash"] = hashlib.sha256(
            json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        state["cart"] = TaskRuntimeService._browser_cart_state(state)
        return state

    @staticmethod
    def _browser_cart_state(observation: dict[str, Any]) -> dict[str, Any]:
        text = str(observation.get("text") or "")
        controls = observation.get("elements") or []
        badge = next(
            (
                str(item.get("name") or "")
                for item in controls
                if re.search(r"cart|bag|basket|购物车|购物袋", str(item.get("name") or ""), re.I)
            ),
            "",
        )
        count_match = re.search(r"\b(\d{1,3})\b", badge)
        return {
            "badge_text": badge[:120],
            "count": int(count_match.group(1)) if count_match else None,
            "confirmation": bool(
                re.search(
                    r"added to (?:your )?(?:cart|bag|basket)|added successfully|已(?:加入|添加到)购物车|已(?:加入|添加到)购物袋",
                    text,
                    re.I,
                )
            ),
        }

    @staticmethod
    def _browser_cart_verified(before: dict[str, Any], after: dict[str, Any]) -> bool:
        return bool(
            after.get("confirmation")
            and not before.get("confirmation")
            or before.get("count") is not None
            and after.get("count") is not None
            and after["count"] > before["count"]
        )

    @staticmethod
    def _browser_cart_intent(goal: str) -> bool:
        return bool(
            re.search(
                r"(?:add.{0,32}(?:to.{0,4})?(?:cart|bag|basket)|put.{0,24}(?:in|into).{0,8}(?:cart|bag|basket)|"
                r"(?:加入|放入|添加|加到|加进).{0,8}(?:购物车|购物袋|cart|bag|basket))",
                goal,
                re.I,
            )
        )

    @staticmethod
    def _browser_locator_variants(element: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        if element.get("role") and element.get("name"):
            values.append({"kind": "role", "value": element["role"], "name": element["name"], "exact": True})
        if element.get("test_id"):
            values.append({"kind": "test_id", "value": element["test_id"]})
        if element.get("label"):
            values.append({"kind": "label", "value": element["label"], "exact": True})
        if element.get("placeholder"):
            values.append({"kind": "placeholder", "value": element["placeholder"], "exact": True})
        if element.get("stable_id"):
            values.append({"kind": "id", "value": element["stable_id"]})
        if element.get("name"):
            values.append({"kind": "text", "value": element["name"], "exact": True})
        if (element.get("_href_selector") or element.get("href")) and element.get("tag") == "a":
            values.append(
                {"kind": "css", "value": f"a[href={json.dumps(element.get('_href_selector') or element['href'])}]"}
            )
        return values

    async def _browser_agent_candidates(
        self,
        task: TaskORM,
        observation: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[BrowserAgentPlan, dict[str, Any]]:
        if not await self._reserve_ai_call(task.id):
            raise TaskBlocked(
                "AI 候选生成额度已用完，浏览器已停止。",
                failure_type="AI_BUDGET_EXHAUSTED",
                details={"current_url": observation.get("url"), "action_count": len(state.get("history") or [])},
            )
        from qa_core.ai.registry import AIProviderRegistry

        trace_id = uuid4().hex
        subgoals = state.get("subgoals") or []
        await self._record_ai_trace(
            task.id,
            make_trace_event(
                trace_id,
                "analysis_started",
                stage="page_understanding",
                title="AI 正在理解页面并生成下一步候选",
                message=(state.get("current_subgoal") or task.goal)[:240],
                metadata={"url": observation.get("url"), "title": observation.get("title")},
            ),
        )
        prompt_data = {
            "goal": task.goal[:1500],
            "high_level_subgoals": subgoals,
            "previous_subgoal": state.get("current_subgoal"),
            "previous_actions_and_results": (state.get("history") or [])[-8:],
            "previous_result": (state.get("history") or [{}])[-1],
            "current_page": {
                "url": observation.get("url"),
                "title": observation.get("title"),
                "visible_text": (observation.get("text") or "")[:5000],
                "accessibility_tree": (observation.get("accessibility_tree") or "")[:10000],
                "interactive_elements": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in observation.get("elements", [])[:40]
                ],
                "network_status": observation.get("network"),
                "state_hash": observation.get("state_hash"),
            },
            "required_behavior": [
                "Decompose the user goal into a short ordered list of high-level subgoals on the first observation.",
                "Generate 2-5 candidate actions only from current interactive element IDs; use no invented selectors.",
                "Return a preferred_candidate_id as the AI-only ranking fallback.",
                "After every action use the newly observed page; never reuse the previous observation as current state.",
                "Never choose checkout, purchase, payment, account mutation, destructive, or form-submit actions.",
                "Add-to-cart is allowed only when the user goal explicitly asks to add the product to cart.",
                "Claim completion only when the current page provides visible evidence; list the exact evidence.",
                "If the current state is unexpected, propose one bounded recovery action such as back, then re-observe.",
            ],
        }
        started = time.perf_counter()
        try:
            response = await AIProviderRegistry.get_provider().complete(
                AICompletionRequest(
                    task_id=task.id,
                    prompt=json.dumps(prompt_data, ensure_ascii=False, separators=(",", ":")),
                    system_instruction=(
                        "You are a cautious web QA agent. Read only the supplied current-page observation. "
                        "Return a structured BrowserAgentPlan. Each candidate must cite an observed target_id, "
                        "must use one of the supplied element IDs, and must explain a visible expected effect. "
                        "Do not write selectors or claim that an action happened. Never buy, checkout, pay, submit, "
                        "change account data, or perform destructive actions."
                    ),
                    response_schema=BrowserAgentPlan,
                    prompt_id="browser_action_candidates",
                    prompt_version="1",
                    temperature=0.1,
                    max_tokens=2200,
                    timeout_seconds=20,
                    max_retries=0,
                )
            )
        except Exception as error:
            await self._record_ai_trace(
                task.id,
                make_trace_event(
                    trace_id,
                    "failed",
                    stage="page_understanding",
                    title="AI 页面分析失败",
                    message=type(error).__name__,
                    status="FAILED",
                ),
            )
            raise TaskBlocked(
                "AI 当前无法分析页面；没有执行未经验证的浏览操作。",
                failure_type="AI_PROVIDER_BLOCKED",
                details={"provider_error": type(error).__name__, "current_url": observation.get("url")},
            ) from error

        state["metrics"]["ai_calls"] = int(state["metrics"].get("ai_calls", 0)) + 1
        latency = round((time.perf_counter() - started) * 1000, 1)
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            await repo.add_event(
                task.id,
                "step.progress",
                {
                    "step_id": active_runtime_step.get(),
                    "type": "ai.call",
                    "ai_run_id": response.invocation_id,
                    "provider": response.provider,
                    "model": response.model,
                    "fallback_used": response.fallback_used,
                    "duration_ms": response.duration_ms,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "operation": "browser_action_candidates",
                },
            )
            await session.commit()
        if response.provider == "fake" or response.fallback_used:
            raise TaskBlocked(
                "当前 AI Provider 只返回模拟结果；浏览 Agent 已停止，没有把模拟输出当成真实页面理解。",
                failure_type="AI_PROVIDER_BLOCKED",
                details={"provider": response.provider, "model": response.model},
            )
        try:
            plan = BrowserAgentPlan.model_validate(
                response.structured_data if response.structured_data is not None else json.loads(response.content)
            )
        except Exception as error:
            raise TaskBlocked(
                "AI 返回的浏览候选格式无效，未执行浏览器动作。",
                failure_type="AI_OUTPUT_INVALID",
                details={"provider": response.provider, "model": response.model},
            ) from error
        state["metrics"]["ai_latency_ms"] = latency
        if plan.subgoals and not state.get("subgoals"):
            state["subgoals"] = plan.subgoals[:12]
            await self._record_ai_trace(
                task.id,
                make_trace_event(
                    trace_id,
                    "workflow.plan",
                    stage="planning",
                    title="AI 拆分浏览目标",
                    message=" → ".join(state["subgoals"][:8])[:500],
                    metadata={"subgoal_count": len(state["subgoals"])},
                ),
            )
        state["current_subgoal"] = (plan.current_subgoal or task.goal)[:300]
        state["current_subgoal_index"] = plan.current_subgoal_index
        return plan, {
            "provider": response.provider,
            "model": response.model,
            "latency_ms": latency,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }

    async def _browser_agent(self, task: TaskORM, _outputs: dict[str, Any]) -> dict[str, Any]:
        requested_url = str(self._input(task, "url", "")).strip()
        parsed = urlparse(requested_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TaskBlocked("浏览器 Agent 需要不含用户名或密码的 http(s) URL。", failure_type="NAVIGATION_FAILED")

        from playwright.async_api import async_playwright

        from app.services.recorder_service import RecorderSessionCreate, recorder_service

        task, _ = await self._load(task.id)
        if task is None:
            raise TaskBlocked("Browser task no longer exists.")
        persisted = (task.context or {}).get("browser_agent") or {}
        state = {
            "current_url": persisted.get("current_url") or SensitiveRedactor.redact_url(requested_url),
            "subgoals": persisted.get("subgoals") or [],
            "current_subgoal": persisted.get("current_subgoal") or task.goal[:300],
            "current_subgoal_index": int(persisted.get("current_subgoal_index") or 0),
            "history": list(persisted.get("history") or [])[-20:],
            "decision_samples": list(persisted.get("decision_samples") or [])[-20:],
            "state_hashes": list(persisted.get("state_hashes") or [])[-20:],
            "url_history": list(persisted.get("url_history") or [])[-20:],
            "metrics": {
                "ai_calls": 0,
                "jev_decisions": 0,
                "jev_correct": 0,
                "jev_failed": 0,
                "jev_abstain": 0,
                "fallbacks": 0,
                "browser_actions": 0,
                "browser_action_success": 0,
                "failed_actions": 0,
                "recovery_count": 0,
                "human_takeovers": int((persisted.get("metrics") or {}).get("human_takeovers", 0)),
                "loop_detected": False,
                "goal_completion": False,
                "total_duration_ms": 0,
                "ai_latency_ms": 0,
                "jev_latency_ms": 0,
                "browser_latency_ms": 0,
                **(persisted.get("metrics") or {}),
            },
        }
        session = None
        owns_browser = False
        browser = context = page = None
        playwright = None
        recorder_session_id = str(self._input(task, "recorder_session_id", "") or "").strip()
        if recorder_session_id:
            session = await recorder_service.get(recorder_session_id, str(task.owner_id))
            if not session or session.project_id != task.project_id:
                raise TaskBlocked("浏览器录制会话已关闭或不属于当前项目。", failure_type="HUMAN_TAKEOVER_UNAVAILABLE")
        elif task.project_id:
            try:
                session = await recorder_service.create_session(
                    str(task.owner_id), RecorderSessionCreate(project_id=task.project_id, start_url=requested_url)
                )
            except Exception as error:
                raise TaskBlocked(
                    "无法启动实时浏览器；请检查 Chromium/Edge 权限。",
                    failure_type="BROWSER_UNAVAILABLE",
                    details={"error_type": type(error).__name__},
                ) from error
            recorder_session_id = session.id
            async with async_session_factory() as db_session:
                current = await TaskRepository(db_session).get(task.id)
                if current:
                    current.inputs = {**(current.inputs or {}), "recorder_session_id": session.id}
                    await db_session.commit()
        if session:
            page, context = session.page, session.context
            if page.url == "about:blank":
                try:
                    await page.goto(requested_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as error:
                    raise TaskBlocked(
                        "浏览器无法打开目标页面。",
                        failure_type="NAVIGATION_FAILED",
                        details={
                            "error_type": type(error).__name__,
                            "requested_url": SensitiveRedactor.redact_url(requested_url),
                        },
                    ) from error
        else:
            try:
                playwright = await async_playwright().start()
                proxy = browser_proxy_options()
                browser = await launch_chromium(playwright, headless=True, **({"proxy": proxy} if proxy else {}))
                owns_browser = True
                context = await browser.new_context(viewport={"width": 1280, "height": 720})
                page = await context.new_page()
                resume_url = str(state.get("current_url") or requested_url)
                await page.goto(resume_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as error:
                if playwright:
                    await playwright.stop()
                raise TaskBlocked(
                    "无法启动实时浏览器或访问目标页面。",
                    failure_type="BROWSER_UNAVAILABLE" if "launch" in str(error).lower() else "NAVIGATION_FAILED",
                    details={"error_type": type(error).__name__},
                ) from error

        started = time.perf_counter()
        network = {"requests": 0, "failed": 0, "responses": 0}
        page.on("request", lambda _request: network.__setitem__("requests", network["requests"] + 1))
        page.on("requestfailed", lambda _request: network.__setitem__("failed", network["failed"] + 1))
        page.on("response", lambda _response: network.__setitem__("responses", network["responses"] + 1))
        max_actions = max(1, min(12, int(self._input(task, "max_browser_actions", 12))))
        max_recoveries = max(0, min(5, int(self._input(task, "max_recovery_attempts", 2))))
        criteria = self._input(task, "observable_text_criteria", [])
        criteria = [str(value)[:200] for value in criteria[:10]] if isinstance(criteria, list) else []
        goal_text = task.goal.casefold()
        cart_intent = self._browser_cart_intent(goal_text)
        initial_hash = persisted.get("pause_state_hash")
        stop_reason = "ACTION_LIMIT_REACHED"
        goal_completed = False
        latest_observation: dict[str, Any] = {}
        recovered_pause = bool(persisted.get("pause_count"))
        waited_loading_states: set[tuple[str, str]] = set()

        try:
            if recovered_pause and session:
                latest_observation = await self._observe_browser_page(
                    page, network, waited_loading_states=waited_loading_states
                )
                if initial_hash and latest_observation["state_hash"] != initial_hash:
                    state["metrics"]["human_takeovers"] += 1
                    takeover = {
                        "action": "human_takeover",
                        "status": "observed_page_changed_while_paused",
                        "url": latest_observation["url"],
                        "state_hash": latest_observation["state_hash"],
                    }
                    state["history"].append(takeover)
                    await self._browser_agent_event(
                        task.id,
                        "browser.human_takeover",
                        "检测到用户接管后的页面变化",
                        latest_observation["title"],
                        status="COMPLETED",
                        metadata={"url": latest_observation["url"], "state_hash": latest_observation["state_hash"]},
                    )

            for action_index in range(int(state["metrics"].get("browser_actions", 0)), max_actions):
                task, _ = await self._load(task.id)
                if not task or task.status == TaskStatus.CANCELLED.value:
                    raise TaskBlocked("浏览任务已取消。", failure_type="ACTION_FAILED")
                latest_observation = await self._observe_browser_page(
                    page, network, waited_loading_states=waited_loading_states
                )
                current_hash = latest_observation["state_hash"]
                current_url = latest_observation["url"]
                if not state["url_history"] or state["url_history"][-1] != current_url:
                    state["url_history"].append(current_url)
                    state["url_history"] = state["url_history"][-20:]
                if self._browser_url_loop(state["url_history"]):
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    await self._browser_agent_event(
                        task.id,
                        "browser.loop_detected",
                        "页面来回跳转已停止",
                        "检测到重复的 URL 往返；Agent 已停止继续操作。",
                        status="BLOCKED",
                        metadata={"url": current_url},
                    )
                    break
                visits = state["state_hashes"]
                if visits.count(current_hash) >= 3:
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    break
                visits.append(current_hash)
                state["state_hashes"] = visits[-20:]

                await self._persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.ACCESSIBILITY_TREE,
                    "playwright.aria_snapshot",
                    f"Observed {latest_observation['title']!r} at {latest_observation['url']}; {len(latest_observation['elements'])} visible controls.",
                    latest_observation["accessibility_tree"],
                    {
                        "url": latest_observation["url"],
                        "title": latest_observation["title"],
                        "state_hash": current_hash,
                    },
                )
                await self._persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.DOM_SNAPSHOT,
                    "playwright.visible_page_text",
                    "Visible text and interactive element snapshot for this decision.",
                    latest_observation["text"],
                    {"candidate_count": len(latest_observation["elements"]), "state_hash": current_hash},
                )

                if not state.get("history"):
                    screenshot = await self._artifact(
                        task,
                        "browser_agent",
                        "browser-initial.png",
                        "SCREENSHOT",
                        await page.screenshot(type="png"),
                        "image/png",
                    )
                    await self._persist_browser_agent_artifact(task.id, screenshot)

                plan, ai_info = await self._browser_agent_candidates(task, latest_observation, state)
                state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)

                if plan.goal_status == "completed" and self._browser_goal_verified(
                    task.goal, plan, latest_observation, state["history"], criteria, cart_intent
                ):
                    goal_completed = True
                    stop_reason = "OBSERVED_GOAL_EVIDENCE"
                    state["metrics"]["goal_completion"] = True
                    break
                if plan.goal_status == "blocked":
                    stop_reason = "AI_REPORTED_BLOCKER"
                    break

                element_by_id = {str(item["id"]): item for item in latest_observation["elements"]}
                seen_ids: set[str] = set()
                valid_candidates: list[dict[str, Any]] = []
                approval_candidates: list[dict[str, str]] = []
                rejected = 0
                from app.services.locator_decision_service import LocatorDecisionService

                for proposal in plan.candidates[:5]:
                    if proposal.candidate_id in seen_ids:
                        rejected += 1
                        continue
                    seen_ids.add(proposal.candidate_id)
                    element = element_by_id.get(proposal.target_id or "")
                    page_action = proposal.action_type in {"back", "scroll", "wait", "inspect"}
                    if not page_action and (not element or not element.get("visible") or not element.get("enabled")):
                        rejected += 1
                        continue
                    if proposal.action_type in {"fill", "select"} and not element:
                        rejected += 1
                        continue
                    if proposal.action_type == "fill" and (
                        element.get("tag") not in {"input", "textarea"}
                        or element.get("type") not in {"", "text", "search", "number"}
                        or not proposal.value
                        or element.get("type") != "search"
                        and not re.search(
                            r"search|搜索|查询",
                            f"{element.get('name', '')} {element.get('placeholder', '')}",
                            re.I,
                        )
                    ):
                        rejected += 1
                        continue
                    if proposal.action_type == "select" and (
                        element.get("tag") != "select"
                        or not any(
                            option.get("enabled") and str(option.get("value")) == str(proposal.value)
                            for option in element.get("options", [])
                        )
                    ):
                        rejected += 1
                        continue
                    if proposal.action_type in {"navigate", "open_product"} and not (
                        element and element.get("tag") == "a" and element.get("href")
                    ):
                        rejected += 1
                        continue
                    if proposal.action_type == "add_to_cart" and not cart_intent:
                        rejected += 1
                        continue
                    risk_action = proposal.action_type
                    label = str((element or {}).get("name") or proposal.target)
                    cart_control = bool(
                        re.search(
                            r"add.?to.?cart|add.?to.?bag|add.?to.?basket|加入购物车|加入购物袋|添加到购物车|添加到购物袋",
                            label,
                            re.I,
                        )
                    )
                    if cart_control and not cart_intent:
                        rejected += 1
                        continue
                    if risk_action == "click" and re.search(
                        r"search|filter|category|menu|搜索|筛选|分类|菜单", label, re.I
                    ):
                        risk_action = "filter"
                    if risk_action == "fill":
                        risk_action = "filter"
                    if risk_action == "select" and re.search(
                        r"color|colour|size|variant|颜色|色系|尺码|尺寸|规格", label, re.I
                    ):
                        risk_action = "choose_variant"
                    if risk_action == "click" and (element or {}).get("expanded") is not None:
                        risk_action = "filter"
                    risk = classify_browser_action(
                        risk_action,
                        name=label,
                        tag=str((element or {}).get("tag") or ""),
                        href=str((element or {}).get("_href") or (element or {}).get("href") or ""),
                        input_type=str((element or {}).get("type") or ""),
                    )
                    if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
                        approval_candidates.append(
                            {"candidate_id": proposal.candidate_id, "target": label[:120], "risk": risk}
                        )
                        rejected += 1
                        continue
                    locator = None
                    if not page_action:
                        action_for_verify = "fill" if proposal.action_type == "fill" else "click"
                        for variant in self._browser_locator_variants(element):
                            verification = await LocatorDecisionService.verify_candidate(
                                page, variant, {"action": action_for_verify}
                            )
                            if verification["verified"]:
                                locator = variant
                                break
                        if locator is None:
                            rejected += 1
                            continue
                    row = proposal.model_dump(mode="json")
                    if cart_control:
                        row["action_type"] = "add_to_cart"
                    row.update(
                        {
                            "target": label[:200],
                            "locator": locator,
                            "locator_strategy": locator.get("kind") if locator else "page",
                            "risk": risk,
                            "_element": element,
                        }
                    )
                    valid_candidates.append(row)

                candidate_summary = [
                    {
                        key: row.get(key)
                        for key in (
                            "candidate_id",
                            "action_type",
                            "target",
                            "locator_strategy",
                            "reason_summary",
                            "expected_effect",
                            "risk",
                        )
                    }
                    for row in valid_candidates
                ]
                await self._record_ai_trace(
                    task.id,
                    make_trace_event(
                        uuid4().hex,
                        "candidates_generated",
                        stage="candidate_generation",
                        title=f"AI 生成 {len(valid_candidates)} 个可验证候选",
                        message=state["current_subgoal"],
                        metadata={
                            "candidate_count": len(valid_candidates),
                            "candidate_summary": json.dumps(candidate_summary, ensure_ascii=False)[:480],
                            "rejected_count": rejected,
                            "ai_preference": plan.preferred_candidate_id,
                            **ai_info,
                        },
                    ),
                )
                await self._persist_browser_agent_state(
                    task.id,
                    state,
                    title=f"AI 正在浏览网页 · {state['current_subgoal']}",
                    summary=f"已检查 {len(latest_observation['elements'])} 个可见控件，得到 {len(valid_candidates)} 个有效候选。",
                )
                if not valid_candidates:
                    stop_reason = "APPROVAL_REQUIRED" if approval_candidates else "NO_CANDIDATE"
                    if approval_candidates:
                        await self._browser_agent_event(
                            task.id,
                            "browser.action_blocked",
                            "浏览操作需要用户确认",
                            "页面上只找到需要确认的高风险操作；Agent 没有执行。请在浏览器中接管。",
                            status="BLOCKED",
                            metadata={"blocked_candidates": json.dumps(approval_candidates, ensure_ascii=False)[:400]},
                        )
                    break

                jev_result = None
                jev_error = None
                jev_latency = 0.0
                if len(valid_candidates) > 1:
                    state["metrics"]["jev_decisions"] += 1
                    decision_started = time.perf_counter()
                    await self._record_ai_trace(
                        task.id,
                        make_trace_event(
                            uuid4().hex,
                            "decision_started",
                            stage="decision",
                            title="JEV 正在选择浏览动作",
                            message=state["current_subgoal"],
                            metadata={"candidate_count": len(valid_candidates), "jev_attempted": True},
                        ),
                    )
                    try:
                        decision_request = DecisionRequest(
                            name="browser_action_selection",
                            state={
                                "goal": task.goal[:1000],
                                "current_subgoal": state["current_subgoal"],
                                "page_summary": {
                                    "url": latest_observation["url"],
                                    "title": latest_observation["title"],
                                    "visible_text": latest_observation["text"][:2500],
                                    "state_hash": current_hash,
                                },
                                "relevant_elements": [
                                    {key: value for key, value in row["_element"].items() if not key.startswith("_")}
                                    for row in valid_candidates
                                    if row.get("_element")
                                ],
                                "candidates": candidate_summary,
                                "previous_action_result": (state.get("history") or [{}])[-1],
                            },
                            instructions="Select only the candidate_id for the best safe next browser action, or choose abstain. Never create or alter a selector.",
                            options=[
                                *[
                                    DecisionOption(
                                        key=row["candidate_id"],
                                        description=json.dumps(
                                            {
                                                key: row.get(key)
                                                for key in (
                                                    "action_type",
                                                    "target",
                                                    "locator",
                                                    "reason_summary",
                                                    "expected_effect",
                                                    "risk",
                                                )
                                            },
                                            ensure_ascii=False,
                                        )[:1000],
                                    )
                                    for row in valid_candidates
                                ],
                                DecisionOption(key="abstain", description="No candidate is reliably appropriate."),
                            ],
                        )
                        jev_result = await DecisionService().choose(
                            decision_request,
                            task_id=task.id,
                            run_id=uuid4().hex,
                        )
                    except Exception as error:
                        jev_error = type(error).__name__
                    jev_latency = round((time.perf_counter() - decision_started) * 1000, 1)
                    state["metrics"]["jev_latency_ms"] = jev_latency

                if jev_result and jev_result.provider == "jev" and jev_result.choice == "abstain":
                    state["metrics"]["jev_abstain"] += 1
                chosen, decision_provider, fallback_reason = self._choose_browser_candidate(
                    valid_candidates,
                    plan.preferred_candidate_id,
                    jev_result=jev_result,
                    jev_error=jev_error,
                )
                if decision_provider in {"ai-ranking", "local-heuristic"}:
                    state["metrics"]["fallbacks"] += 1
                    state["metrics"]["jev_failed"] += 1
                ai_preference = next(
                    (row for row in valid_candidates if row["candidate_id"] == plan.preferred_candidate_id), None
                )
                if (
                    ai_preference
                    and len(valid_candidates) > 1
                    and ai_preference["candidate_id"] != chosen["candidate_id"]
                ):
                    state["metrics"].setdefault("ai_jev_disagreements", 0)
                    state["metrics"]["ai_jev_disagreements"] += 1

                selected_locator = chosen.get("locator")
                if self._browser_repeats_same_target(state["history"], chosen):
                    state["metrics"]["loop_detected"] = True
                    stop_reason = "LOOP_DETECTED"
                    await self._browser_agent_event(
                        task.id,
                        "browser.loop_detected",
                        "重复动作已停止",
                        f"连续两次选择同一页面控件：{chosen['action_type']} · {chosen['target']}",
                        status="BLOCKED",
                        metadata={"candidate_id": chosen["candidate_id"], "action": chosen["action_type"]},
                    )
                    break
                decision_sample = {
                    "step": len(state["decision_samples"]) + 1,
                    "url": latest_observation["url"],
                    "state_hash": current_hash,
                    "subgoal": state["current_subgoal"],
                    "candidates": candidate_summary,
                    "ai_preferred_candidate_id": plan.preferred_candidate_id,
                    "selected_candidate_id": chosen["candidate_id"],
                    "provider": decision_provider,
                    "jev_attempted": len(valid_candidates) > 1,
                    "jev_failed": bool(fallback_reason and len(valid_candidates) > 1),
                    "jev_abstain": bool(jev_result and jev_result.provider == "jev" and jev_result.choice == "abstain"),
                    "fallback_used": decision_provider in {"ai-ranking", "local-heuristic"},
                    "fallback_reason": fallback_reason,
                    "ai_provider": ai_info["provider"],
                    "ai_model": ai_info["model"],
                    "ai_latency_ms": ai_info["latency_ms"],
                    "ai_input_tokens": ai_info["input_tokens"],
                    "ai_output_tokens": ai_info["output_tokens"],
                    "confidence": jev_result.confidence if decision_provider == "jev" and jev_result else None,
                    "scores": jev_result.probabilities if decision_provider == "jev" and jev_result else {},
                    "latency_ms": jev_latency if len(valid_candidates) > 1 else 0.0,
                    "model": jev_result.model if decision_provider == "jev" and jev_result else None,
                }
                state["decision_samples"].append(decision_sample)
                await self._record_ai_trace(
                    task.id,
                    make_trace_event(
                        uuid4().hex,
                        "decision_completed"
                        if decision_provider in {"jev", "single-candidate"}
                        else "decision.fallback",
                        stage="decision",
                        title=(
                            "JEV 选择了浏览动作"
                            if decision_provider == "jev"
                            else "仅有一个已验证候选，无需 JEV 决策"
                            if decision_provider == "single-candidate"
                            else "已切换到候选排序回退"
                        ),
                        message=f"{chosen['action_type']} · {chosen['target'][:120]}",
                        metadata={
                            "provider": decision_provider,
                            "model": decision_sample["model"],
                            "candidate_id": chosen["candidate_id"],
                            "candidate_count": len(valid_candidates),
                            "confidence": decision_sample["confidence"],
                            "latency_ms": decision_sample["latency_ms"],
                            "fallback_used": decision_sample["fallback_used"],
                            "fallback_reason": fallback_reason,
                            "candidate_summary": json.dumps(candidate_summary, ensure_ascii=False)[:480],
                            "candidate_scores": json.dumps(decision_sample["scores"], ensure_ascii=False)[:400],
                        },
                    ),
                )
                async with async_session_factory() as session_db:
                    repo = TaskRepository(session_db)
                    stored = await repo.add_decision(
                        task_id=task.id,
                        step_id=active_runtime_step.get(),
                        name="browser_action_selection",
                        provider=decision_provider,
                        choice=chosen["candidate_id"],
                        confidence=decision_sample["confidence"],
                        rationale=chosen["reason_summary"][:500],
                    )
                    await repo.add_event(
                        task.id,
                        "decision.created",
                        {
                            "step_id": active_runtime_step.get(),
                            "decision_id": stored.id,
                            "name": "browser_action_selection",
                            "choice": stored.choice,
                            "provider": stored.provider,
                            "confidence": stored.confidence,
                        },
                    )
                    await session_db.commit()

                before_cart = latest_observation["cart"]
                action_started = time.perf_counter()
                state["metrics"]["browser_actions"] += 1
                await self._browser_agent_event(
                    task.id,
                    "browser.action_started",
                    f"正在执行：{chosen['action_type']} · {chosen['target'] or chosen['value'] or '页面'}",
                    chosen["expected_effect"],
                    status="RUNNING",
                    metadata={
                        "action": chosen["action_type"],
                        "locator": json.dumps(selected_locator, ensure_ascii=False) if selected_locator else "page",
                        "candidate_id": chosen["candidate_id"],
                        "url": latest_observation["url"],
                    },
                )
                action_error = None
                try:
                    await self._execute_browser_candidate(page, chosen)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except Exception:
                        pass
                except Exception as error:
                    action_error = type(error).__name__
                after = await self._observe_browser_page(page, network, waited_loading_states=waited_loading_states)
                duration = round((time.perf_counter() - action_started) * 1000, 1)
                state["metrics"]["browser_latency_ms"] = duration
                cart_verified = chosen["action_type"] == "add_to_cart" and self._browser_cart_verified(
                    before_cart, after["cart"]
                )
                state_changed = after["state_hash"] != current_hash
                expected_verified = self._browser_expected_effect_observed(
                    chosen.get("expected_effect", ""),
                    " ".join([after["url"], after["title"], after["text"], after["accessibility_tree"]]),
                )
                if chosen["action_type"] == "add_to_cart":
                    effect_verified = cart_verified
                elif chosen["action_type"] in {"fill", "select"}:
                    current_element = next(
                        (item for item in after["elements"] if item.get("id") == chosen.get("target_id")), {}
                    )
                    effect_verified = (
                        bool(
                            chosen.get("value") and str(current_element.get("value") or "") == str(chosen.get("value"))
                        )
                        or state_changed
                        and expected_verified
                    )
                elif chosen["action_type"] == "inspect":
                    effect_verified = True
                else:
                    effect_verified = (state_changed or after["url"] != latest_observation["url"]) and (
                        expected_verified or not chosen.get("expected_effect")
                    )
                if action_error:
                    action_status = "failed"
                    state["metrics"]["failed_actions"] += 1
                    stop_reason = "ACTION_FAILED"
                elif effect_verified:
                    action_status = "success"
                    state["metrics"]["browser_action_success"] += 1
                elif chosen["action_type"] in {"wait", "inspect"}:
                    action_status = "partial"
                    state["metrics"].setdefault("partial_actions", 0)
                    state["metrics"]["partial_actions"] += 1
                else:
                    action_status = "unexpected"
                    state["metrics"]["failed_actions"] += 1
                    stop_reason = "UNEXPECTED_STATE"
                if decision_provider == "jev" and effect_verified:
                    state["metrics"]["jev_correct"] += 1
                screenshot = await self._artifact(
                    task,
                    "browser_agent",
                    f"browser-action-{len(state['history']) + 1:02d}.png",
                    "SCREENSHOT",
                    await page.screenshot(type="png"),
                    "image/png",
                )
                await self._persist_browser_agent_artifact(task.id, screenshot)
                action_result = {
                    "action": chosen["action_type"],
                    "target": chosen["target"],
                    "target_id": chosen.get("target_id"),
                    "locator": selected_locator,
                    "candidate_id": chosen["candidate_id"],
                    "expected_effect": chosen["expected_effect"],
                    "reason_summary": chosen["reason_summary"],
                    "risk": chosen["risk"],
                    "status": action_status,
                    "error_type": action_error,
                    "url_before": latest_observation["url"],
                    "url_after": after["url"],
                    "state_hash_before": current_hash,
                    "state_hash_after": after["state_hash"],
                    "state_changed": state_changed,
                    "expected_effect_observed": expected_verified,
                    "cart_verified": cart_verified,
                    "duration_ms": duration,
                    "screenshot_artifact_id": screenshot["artifact_id"],
                    "network": after["network"],
                }
                decision_sample["action_status"] = action_status
                decision_sample["effect_verified"] = effect_verified
                decision_sample["duration_ms"] = duration
                state["history"].append(action_result)
                state["history"] = state["history"][-20:]
                await self._persist_browser_agent_evidence(
                    task.id,
                    EvidenceType.SCREENSHOT,
                    "playwright.browser_agent",
                    f"{chosen['action_type']} {chosen['target']!r}: {action_status}.",
                    json.dumps(action_result, ensure_ascii=False),
                    action_result,
                    screenshot["artifact_id"],
                )
                await self._browser_agent_event(
                    task.id,
                    "browser.action_completed",
                    f"{action_status.title()}：{chosen['action_type']} · {chosen['target'] or '页面'}",
                    chosen["expected_effect"],
                    status="COMPLETED" if effect_verified else "PARTIAL" if action_status == "partial" else "FAILED",
                    duration_ms=duration,
                    metadata={
                        "action": chosen["action_type"],
                        "locator": json.dumps(selected_locator, ensure_ascii=False) if selected_locator else "page",
                        "url": after["url"],
                        "artifact_id": screenshot["artifact_id"],
                        "candidate_id": chosen["candidate_id"],
                        "verified": effect_verified,
                        "expected_effect": chosen["expected_effect"],
                    },
                )
                await self._browser_agent_event(
                    task.id,
                    "browser.observation",
                    "已重新观察页面",
                    f"{after['title']} · {after['url']}",
                    status="COMPLETED" if state_changed else "UNEXPECTED",
                    duration_ms=duration,
                    metadata={
                        "url": after["url"],
                        "title": after["title"],
                        "state_hash": after["state_hash"],
                        "network_requests": after["network"]["requests"],
                        "network_failed": after["network"]["failed"],
                        "artifact_id": screenshot["artifact_id"],
                    },
                )
                state["current_url"] = after["url"]
                state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
                if action_status in {"failed", "unexpected"}:
                    state["metrics"]["recovery_count"] += 1
                    if state["metrics"]["recovery_count"] > max_recoveries:
                        stop_reason = "ACTION_FAILED" if action_error else "UNEXPECTED_STATE"
                        latest_observation = after
                        break
                elif effect_verified:
                    state["metrics"]["recovery_count"] = max(0, state["metrics"]["recovery_count"] - 1)

                goal_completed = self._browser_goal_verified(
                    task.goal, plan, after, state["history"], criteria, cart_intent
                )
                if goal_completed:
                    stop_reason = "OBSERVED_GOAL_EVIDENCE"
                    state["metrics"]["goal_completion"] = True
                    latest_observation = after
                    break

                state["pause_state_hash"] = after["state_hash"]
                await self._persist_browser_agent_state(
                    task.id,
                    state,
                    title="QA Agent 正在浏览网页",
                    summary=f"当前目标：{state['current_subgoal']}；最近结果：{action_status} · {chosen['target'] or chosen['action_type']}。",
                )
                latest_observation = after
                fresh, _ = await self._load(task.id)
                if fresh and fresh.status == TaskStatus.PAUSING.value:
                    state["pause_count"] = int(state.get("pause_count", 0)) + 1
                    await self._persist_browser_agent_state(
                        task.id,
                        state,
                        title="Agent 已在浏览器动作边界暂停",
                        summary="你可以在同一浏览器页面手动完成一步，再恢复 Agent。恢复时会重新观察当前页面。",
                        status="PAUSED",
                        event_type="browser.agent_paused",
                    )
                    return {"_pause_after_step": True, "current_url": after["url"]}

            state["metrics"]["total_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            state["current_url"] = latest_observation.get("url") or state.get("current_url")
            state["stop_reason"] = stop_reason
            state["metrics"]["goal_completion"] = bool(goal_completed)
            await self._persist_browser_agent_state(
                task.id,
                state,
                title="浏览目标已验证" if goal_completed else "浏览 Agent 暂停并交由人工检查",
                summary=(
                    f"目标已由页面证据确认；当前 URL：{state['current_url']}"
                    if goal_completed
                    else f"停止原因：{stop_reason}；当前 URL：{state['current_url']}"
                ),
                status="COMPLETED" if goal_completed else "BLOCKED",
                event_type="browser.goal_completed" if goal_completed else "browser.goal_blocked",
            )
            sample_artifact = await self._artifact(
                task,
                "browser_agent",
                "jev-browser-decision-samples.json",
                "DECISION_SAMPLES",
                json.dumps(state["decision_samples"], ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
            )
            await self._persist_browser_agent_artifact(task.id, sample_artifact)
            if not goal_completed:
                failure_type = (
                    stop_reason
                    if stop_reason
                    in {
                        "NO_CANDIDATE",
                        "JEV_NO_DECISION",
                        "LOCATOR_INVALID",
                        "ACTION_FAILED",
                        "UNEXPECTED_STATE",
                        "PAGE_TIMEOUT",
                        "NAVIGATION_FAILED",
                        "LOOP_DETECTED",
                        "APPROVAL_REQUIRED",
                        "GOAL_NOT_REACHED",
                    }
                    else "GOAL_NOT_REACHED"
                )
                message = (
                    "浏览操作需要用户确认；Agent 已停止，请在浏览器中接管。"
                    if stop_reason == "APPROVAL_REQUIRED"
                    else "没有找到可靠的下一步浏览操作。"
                    if stop_reason == "NO_CANDIDATE"
                    else "页面证据尚未证明浏览目标完成。"
                )
                raise TaskBlocked(
                    message,
                    failure_type=failure_type,
                    details={
                        "current_url": state["current_url"],
                        "stop_reason": stop_reason,
                        "metrics": state["metrics"],
                        "decision_samples_artifact_id": sample_artifact["artifact_id"],
                    },
                )
            result = {
                "verified": True,
                "kind": "ai_jev_browser_agent",
                "goal": task.goal,
                "final_url": state["current_url"],
                "goal_evidence": {
                    "source": "live_page_observation",
                    "cart_verified": bool(state["history"] and state["history"][-1].get("cart_verified")),
                    "visible_text_criteria": criteria,
                    "completion_evidence": plan.completion_evidence,
                },
                "subgoals": state["subgoals"],
                "actions": state["history"],
                "decision_samples": state["decision_samples"],
                "decision_samples_artifact_id": sample_artifact["artifact_id"],
                "metrics": state["metrics"],
                "stop_reason": stop_reason,
                "recorder_session_id": recorder_session_id or None,
            }
            return result
        finally:
            if owns_browser and browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    @staticmethod
    def _browser_repeats_same_target(history: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
        action = str(candidate.get("action_type") or "")
        if action in {"scroll", "wait", "inspect"} or len(history) < 2:
            return False
        signature = (action, candidate.get("target_id"))
        return all((item.get("action"), item.get("target_id")) == signature for item in history[-2:])

    @staticmethod
    def _browser_url_loop(urls: list[str]) -> bool:
        return len(urls) >= 5 and urls[-1] == urls[-3] == urls[-5] and urls[-2] == urls[-4] and urls[-1] != urls[-2]

    @staticmethod
    def _choose_browser_candidate(
        candidates: list[dict[str, Any]],
        preferred_candidate_id: str | None,
        *,
        jev_result: Any = None,
        jev_error: str | None = None,
    ) -> tuple[dict[str, Any], str, str | None]:
        chosen = None
        reason = None
        if jev_result and jev_result.provider == "jev" and not jev_result.fallback_used:
            if jev_result.choice == "abstain":
                reason = "jev_abstain"
            else:
                chosen = next((item for item in candidates if item["candidate_id"] == jev_result.choice), None)
                if chosen is None:
                    reason = "jev_invalid_candidate"
        else:
            reason = (jev_result.reason if jev_result else None) or jev_error or "jev_unavailable"
        if chosen:
            return chosen, "jev", None
        if len(candidates) == 1:
            return candidates[0], "single-candidate", "single_candidate_no_decision_needed"
        chosen = next(
            (item for item in candidates if item["candidate_id"] == preferred_candidate_id),
            candidates[0],
        )
        provider = "ai-ranking" if chosen["candidate_id"] == preferred_candidate_id else "local-heuristic"
        return chosen, provider, reason or "jev_unavailable"

    @staticmethod
    async def _execute_browser_candidate(page: Any, candidate: dict[str, Any]) -> None:
        action = candidate["action_type"]
        element = candidate.get("_element") or {}
        locator_data = candidate.get("locator") or {}
        locator = page
        kind = locator_data.get("kind")
        value = str(locator_data.get("value") or "")
        if kind == "role":
            locator = page.get_by_role(value, name=locator_data.get("name"), exact=locator_data.get("exact", True))
        elif kind == "test_id":
            locator = page.get_by_test_id(value)
        elif kind == "label":
            locator = page.get_by_label(value, exact=locator_data.get("exact", True))
        elif kind == "placeholder":
            locator = page.get_by_placeholder(value, exact=locator_data.get("exact", True))
        elif kind == "text":
            locator = page.get_by_text(value, exact=locator_data.get("exact", True))
        elif kind == "id":
            locator = page.locator(f"[id={json.dumps(value)}]")
        elif kind == "css":
            locator = page.locator(value)
        if action in {"click", "open_product", "filter", "choose_variant", "add_to_cart"}:
            if action in {"filter", "choose_variant"} and element.get("tag") == "select":
                await locator.select_option(value=str(candidate.get("value") or ""), timeout=10000)
            else:
                await locator.click(timeout=10000)
        elif action == "navigate":
            target = str(element.get("_href") or element.get("href") or "")
            parsed = urlparse(target)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise TaskBlocked("观察到的链接不是安全的 http(s) 目标。", failure_type="NAVIGATION_FAILED")
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
        elif action == "fill":
            await locator.fill(str(candidate["value"])[:300], timeout=10000)
        elif action == "select":
            await locator.select_option(value=str(candidate["value"]), timeout=10000)
        elif action == "hover":
            await locator.hover(timeout=10000)
        elif action == "scroll":
            direction = str(candidate.get("value") or "down").lower()
            if direction not in {"up", "down"}:
                raise TaskBlocked("Scroll 候选方向无效。", failure_type="AI_OUTPUT_INVALID")
            await page.mouse.wheel(0, 650 if direction == "down" else -650)
        elif action == "wait":
            try:
                duration = max(100, min(5000, int(candidate.get("value") or 700)))
            except (ValueError, TypeError):
                duration = 700
            await page.wait_for_timeout(duration)
        elif action == "back":
            await page.go_back(wait_until="domcontentloaded", timeout=10000)
        elif action == "inspect":
            return
        else:
            raise TaskBlocked("AI 提议了不支持的浏览动作。", failure_type="AI_OUTPUT_INVALID")

    @staticmethod
    def _browser_expected_effect_observed(expected: str, observed: str) -> bool:
        expected = str(expected or "").casefold().strip()
        if not expected:
            return False
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", expected)
            if token
            not in {
                "the",
                "and",
                "with",
                "from",
                "page",
                "into",
                "detail",
                "details",
                "product",
                "results",
                "listing",
                "loaded",
                "opens",
                "appears",
                "shown",
                "visible",
                "selected",
                "now",
                "当前",
                "页面",
                "进入",
                "打开",
            }
        ]
        if not tokens:
            return expected in observed.casefold()
        haystack = observed.casefold()
        matches = sum(token in haystack for token in tokens)
        return matches >= min(2, len(tokens)) and matches / len(tokens) >= 0.5

    @staticmethod
    def _browser_goal_verified(
        goal: str,
        plan: BrowserAgentPlan,
        observation: dict[str, Any],
        history: list[dict[str, Any]],
        criteria: list[str],
        cart_intent: bool,
    ) -> bool:
        haystack = " ".join(
            [str(observation.get("url") or ""), str(observation.get("title") or ""), str(observation.get("text") or "")]
        ).casefold()
        if cart_intent:
            return any(item.get("action") == "add_to_cart" and item.get("cart_verified") is True for item in history)
        if criteria:
            return bool(history) and all(value.casefold() in haystack for value in criteria)
        completion_visible = any(
            str(value).strip().casefold() in haystack for value in plan.completion_evidence if str(value).strip()
        )
        goal_tokens = [
            token
            for token in re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", goal.casefold())
            if token
            not in {
                "please",
                "open",
                "find",
                "show",
                "with",
                "from",
                "this",
                "that",
                "the",
                "and",
                "for",
                "添加",
                "打开",
                "进入",
                "找到",
                "一个",
                "一下",
            }
        ]
        goal_visible = bool(goal_tokens) and all(token in haystack for token in goal_tokens)
        return bool(
            history
            and history[-1].get("status") == "success"
            and plan.goal_status == "completed"
            and (completion_visible or goal_visible)
        )

    async def _browser_inspect(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        url = str(self._input(task, "url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TaskBlocked("Browser exploration requires an http(s) URL without embedded credentials.")
        from playwright.async_api import async_playwright

        recorder_state = await self._recorder_storage_state(task)

        async with async_playwright() as playwright:
            proxy = browser_proxy_options()
            browser = await launch_chromium(playwright, headless=True, **({"proxy": proxy} if proxy else {}))
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800}, storage_state=recorder_state
                )
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
                for candidate in candidates:
                    candidate["risk"] = classify_browser_action(
                        "click",
                        name=candidate.get("name", ""),
                        tag=candidate.get("tag", ""),
                        href=candidate.get("href") or "",
                        input_type=candidate.get("type", ""),
                    )
                    candidate["safe"] = candidate["risk"] in {"READ_ONLY", "SAFE_INTERACTION"}
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
                            {
                                "url": page.url,
                                "title": title,
                                "http_status": response.status if response else None,
                                "recorder_state_applied": recorder_state is not None,
                            },
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
        observed_controls = [
            item
            for item in observed.get("candidates", [])
            if item.get("safe") and item.get("role") and item.get("name")
        ]
        trace_run_id = uuid4().hex
        raw_candidates = [
            {
                "kind": "role",
                "value": str(item["role"]),
                "name": str(item["name"])[:180],
                "exact": True,
                "task_candidate_index": int(item["index"]),
                "evidence": {"uniqueness": True},
            }
            for item in observed_controls
        ]
        event = {
            "tag": "control",
            "action": "click",
            "url": SensitiveRedactor.redact_url(str(observed.get("url") or ""))[:500],
            "target": {"task_goal": task.goal[:500], "accessible_name": "safe page action", "action": "inspect"},
            "context": {"page_title": str(observed.get("title") or "")[:200], "task_goal": task.goal[:500]},
            "candidates": raw_candidates,
        }
        if not raw_candidates:
            event_trace = make_trace_event(
                trace_run_id,
                "decision_completed",
                stage="decision",
                title="Local Strategy found no safe candidate",
                metadata={"provider": "local-strategy", "candidate_count": 0, "verified": False},
            )
            await self._record_ai_trace(task.id, event_trace)
            return {
                "choice": "none",
                "candidate": None,
                "provider": "local-strategy",
                "confidence": None,
                "rationale": "No safe named control was observed.",
                "_decision": {
                    "name": "explore_next_action",
                    "provider": "local-strategy",
                    "choice": "none",
                    "confidence": None,
                    "rationale": "No safe named control was observed.",
                },
                "_evidence": [],
            }

        from app.services.locator_decision_service import LocatorDecisionService

        can_call_provider = await self._reserve_ai_call(task.id)
        if can_call_provider:
            decision_service = DecisionService()
        else:
            from project_model.models import DecisionResult

            class BudgetExhaustedDecisionService:
                async def choose(self, request, *, run_id=None):
                    return DecisionResult(provider="fallback", fallback_used=True, reason="task_ai_budget_exhausted")

            decision_service = BudgetExhaustedDecisionService()
        pipeline = LocatorDecisionService(decision_service=decision_service)
        candidates = LocatorDecisionService.generate_candidates(event)
        try:
            selection = await self._run_locator_decision(task, observed, event, candidates, pipeline, trace_run_id)
        except Exception as error:
            selection = None
            logger.info(
                "Browser locator verification unavailable task_id=%s error_type=%s error=%s",
                task.id,
                type(error).__name__,
                SensitiveRedactor.redact_text(str(error))[:300],
            )

        if selection:
            for item in selection["trace"]:
                await self._record_ai_trace(task.id, item)
        selected_candidate = (selection or {}).get("selected_candidate")
        summary = (selection or {}).get("summary") or {"engine": "Local Strategy", "verified": False}
        if not summary.get("verified"):
            selected_candidate = None
        original = next(
            (
                item
                for item in observed_controls
                if selected_candidate and int(item["index"]) == selected_candidate.get("task_candidate_index")
            ),
            None,
        )
        provider = "jev" if summary.get("engine") == "Jev" else "local-strategy"
        confidence = summary.get("confidence") if provider == "jev" else None
        rationale = (
            f"{summary.get('engine', 'Local Strategy')} selected and Playwright verified {summary.get('candidate_id')}."
            if original
            else "No candidate passed Playwright verification."
        )
        if provider == "jev":
            async with async_session_factory() as session:
                repo = TaskRepository(session)
                fresh = await repo.get(task.id)
                if fresh:
                    fresh.context = {**fresh.context, "jev_calls": int(fresh.context.get("jev_calls", 0)) + 1}
                    await session.commit()
        if original:
            final_event = make_trace_event(
                trace_run_id,
                "decision_completed",
                stage="decision",
                title=f"{summary['engine']} selected and verified action",
                message=f"{original.get('role')} {original.get('name')}",
                metadata={
                    "provider": provider,
                    "model": summary.get("model"),
                    "latency_ms": summary.get("latency_ms"),
                    "candidate_id": summary.get("candidate_id"),
                    "candidate_count": summary.get("candidate_count"),
                    "confidence": confidence,
                    "verified": True,
                    "selected_action": {"role": original.get("role"), "name": original.get("name")},
                },
            )
            await self._record_ai_trace(task.id, final_event)
        decision = {
            "name": "explore_next_action",
            "provider": provider,
            "choice": str(original.get("index")) if original else "none",
            "confidence": confidence,
            "rationale": rationale,
            "candidate_id": summary.get("candidate_id"),
            "verified": bool(original),
            "model": summary.get("model") if provider == "jev" else None,
            "latency_ms": summary.get("latency_ms") if provider == "jev" else None,
        }
        return {
            "choice": decision["choice"],
            "candidate": original,
            "provider": provider,
            "confidence": confidence,
            "rationale": rationale,
            "_decision": {key: decision[key] for key in ("name", "provider", "choice", "confidence", "rationale")},
            "_evidence": [
                await self._evidence(
                    task,
                    "decide",
                    EvidenceType.LOCATOR_CANDIDATES,
                    "locator_decision_service",
                    f"{summary.get('engine', 'Local Strategy')} selected candidate {summary.get('candidate_id')}; verified={bool(original)}.",
                    json.dumps(
                        [
                            {
                                "candidate_id": item["candidate_id"],
                                "locator": item["locator"],
                                "static_score": item["static_score"],
                            }
                            for item in candidates
                        ],
                        ensure_ascii=False,
                    ),
                    {"provider": provider, "verified": bool(original), "candidate_id": summary.get("candidate_id")},
                )
            ],
        }

    async def _run_locator_decision(self, task, observed, event, candidates, pipeline, trace_run_id):
        if observed.get("_page") is not None:
            return await pipeline.decide(
                run_id=trace_run_id,
                event=event,
                candidates=candidates,
                page=observed["_page"],
                step_id=f"task:{task.id}",
            )
        from playwright.async_api import async_playwright

        url = str(observed.get("url") or "")
        recorder_state = await self._recorder_storage_state(task)
        async with async_playwright() as playwright:
            proxy = browser_proxy_options()
            browser = await launch_chromium(playwright, headless=True, **({"proxy": proxy} if proxy else {}))
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800}, storage_state=recorder_state
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                return await pipeline.decide(
                    run_id=trace_run_id,
                    event=event,
                    candidates=candidates,
                    page=page,
                    step_id=f"task:{task.id}",
                )
            finally:
                await browser.close()

    async def _run_step_tool(self, task_id: str, step: TaskStepORM, *, deadline: float | None = None):
        token = active_runtime_step.set(step.id)
        deadline_token = active_task_deadline.set(deadline)
        try:
            return await self._run_tool(task_id, step.key, step.tool)
        finally:
            active_task_deadline.reset(deadline_token)
            active_runtime_step.reset(token)

    async def _record_ai_trace(self, task_id: str, event) -> None:
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            payload = event.model_dump(mode="json") if callable(getattr(event, "model_dump", None)) else event
            if isinstance(payload, dict):
                payload = {**payload, "step_id": active_runtime_step.get()}
            await repo.add_event(task_id, "ai.trace", SensitiveRedactor.redact_value(payload))
            await session.commit()

    async def _analyze_requirement(self, task: TaskORM, _outputs: dict[str, Any]) -> dict[str, Any]:
        requirement_id = str(self._input(task, "requirement_id", "")).strip()
        if not requirement_id:
            raise TaskBlocked("Requirement analysis requires a requirement_id.")

        from app.services.requirement_lifecycle_service import RequirementLifecycleService

        lifecycle = RequirementLifecycleService()
        terminal_event = None
        try:
            async for event in lifecycle.stream(
                requirement_id,
                task_id=task.id,
                reserve_ai_call=lambda: self._reserve_ai_call(task.id),
            ):
                await self._record_ai_trace(task.id, event)
                if event.type in {"run.completed", "run.failed"}:
                    terminal_event = event
        except Exception as error:
            raise TaskBlocked(str(error)) from error

        # Mirror Jev choices into the runtime's task decision projection while the
        # authoritative analysis history remains on the Requirement document.
        async with async_session_factory() as session:
            requirement = await session.get(RequirementORM, requirement_id)
            raw = requirement.qa_model if requirement else {}
            history = raw.get("history", []) if isinstance(raw, dict) else []
            record = history[-1] if history else {}
            if record.get("id") == getattr(terminal_event, "run_id", None):
                repo = TaskRepository(session)
                step_id = active_runtime_step.get()
                for decision in record.get("decisions", []):
                    stored = await repo.add_decision(
                        task_id=task.id,
                        step_id=step_id,
                        name=str(decision.get("name") or "requirement_priority"),
                        provider=str(decision.get("provider") or "fallback"),
                        choice=str(decision.get("choice") or ""),
                        confidence=float(decision.get("confidence") or 0),
                        rationale=str(decision.get("reason") or decision.get("rationale") or ""),
                        escalated=bool(decision.get("escalated", False)),
                    )
                    await repo.add_event(
                        task.id,
                        "decision.created",
                        {
                            "decision_id": stored.id,
                            "step_id": step_id,
                            "name": stored.name,
                            "choice": stored.choice,
                            "provider": stored.provider,
                            "confidence": stored.confidence,
                        },
                    )
                await session.commit()

        if terminal_event is None:
            raise TaskBlocked("Requirement analysis ended without a completion event.")
        if terminal_event.type == "run.failed":
            error_code = str(terminal_event.metadata.get("error_code") or "")
            raise TaskBlocked(
                terminal_event.message or "Requirement analysis failed.",
                failure_type="AI_OUTPUT_INVALID" if error_code == "INVALID_STRUCTURED_OUTPUT" else "STEP_BLOCKED",
                details={"error_code": error_code} if error_code else {},
            )

        async with async_session_factory() as session:
            requirement = await session.get(RequirementORM, requirement_id)
            raw = requirement.qa_model if requirement else {}
        history = raw.get("history", []) if isinstance(raw, dict) else []
        record = history[-1] if history else {}
        if record.get("id") != terminal_event.run_id or record.get("status") != "SUCCESS":
            raise TaskBlocked("Requirement analysis result was not persisted to its source requirement.")
        analysis = raw.get("analysis") or {}
        return {
            "requirement_id": requirement_id,
            "analysis_record_id": record["id"],
            "provider": record.get("provider"),
            "model": record.get("model"),
            "risk_count": len(analysis.get("risks", [])),
            "scenario_count": len(analysis.get("scenarios", [])),
            "_evidence": [
                {
                    "type": EvidenceType.ANALYSIS.value,
                    "source": "requirement.lifecycle",
                    "summary": f"Persisted requirement analysis {record['id']} with {len(analysis.get('risks', []))} risks and {len(analysis.get('scenarios', []))} scenarios.",
                    "metadata": {"requirement_id": requirement_id, "analysis_record_id": record["id"]},
                }
            ],
        }

    async def _materialize_goal_cases(self, task: TaskORM, _outputs: dict[str, Any]) -> dict[str, Any]:
        requirement_id = str(self._input(task, "requirement_id", "")).strip()
        if not requirement_id:
            raise TaskBlocked("Creating requirement cases needs a selected requirement.")
        from app.services.requirement_lifecycle_service import RequirementLifecycleService

        lifecycle = RequirementLifecycleService()
        async with async_session_factory() as session:
            before = set(
                (
                    await session.scalars(select(TestCaseORM.id).where(TestCaseORM.requirement_id == requirement_id))
                ).all()
            )
        designs = await lifecycle.adopt_designs(requirement_id)
        cases = []
        for design in designs:
            cases.append(await lifecycle.adopt_case(design.id))
        created = [item.id for item in cases if item.id not in before]
        result = {
            "requirement_id": requirement_id,
            "design_ids": [item.id for item in designs],
            "case_ids": [item.id for item in cases],
            "created_case_ids": created,
            "created_count": len(created),
        }
        result["_evidence"] = [
            await self._evidence(
                task,
                "materialize_cases",
                EvidenceType.ANALYSIS,
                "RequirementLifecycleService.adopt_designs/adopt_case",
                f"Created {len(created)} missing test case(s); reused {len(cases) - len(created)} existing case(s).",
                json.dumps(result, ensure_ascii=False),
                {"requirement_id": requirement_id, "case_ids": result["case_ids"]},
            )
        ]
        return result

    async def _inspect_goal_coverage(self, task: TaskORM, _outputs: dict[str, Any]) -> dict[str, Any]:
        requirement_id = str(self._input(task, "requirement_id", "")).strip()
        if not requirement_id:
            raise TaskBlocked("Coverage inspection needs a selected requirement.")
        async with async_session_factory() as session:
            requirement = await session.get(RequirementORM, requirement_id)
            if requirement is None or requirement.project_id != task.project_id:
                raise TaskBlocked("Requirement no longer belongs to this project.")
            cases = list(
                (
                    await session.scalars(
                        select(TestCaseORM).where(
                            TestCaseORM.requirement_id == requirement_id,
                            TestCaseORM.project_id == task.project_id,
                        )
                    )
                ).all()
            )
            bindings = list(
                (
                    await session.scalars(
                        select(AutomationBindingORM).where(
                            AutomationBindingORM.test_case_id.in_([item.id for item in cases] or [""]),
                            AutomationBindingORM.status == AutomationBindingStatus.ACTIVE.value,
                        )
                    )
                ).all()
            )
            raw = requirement.qa_model or {}
        binding_by_case = {item.test_case_id: item for item in bindings}
        unbound = [item for item in cases if item.id not in binding_by_case]
        criteria_pairs = [
            (str(item.get("id", "")), str(item.get("description", "")))
            for item in (raw.get("criteria") or [])
            if isinstance(item, dict) and item.get("id") and item.get("description")
        ]
        if not criteria_pairs:
            criteria_pairs = [
                (f"AC-{index:03}", line.strip())
                for index, line in enumerate(requirement.acceptance_criteria.splitlines(), 1)
                if line.strip()
            ]
        covered_ids = {
            str(criterion_id)
            for case in cases
            for criterion_id in ((case.test_model or {}).get("coverage") or {}).get("criterion_ids", [])
        }
        missing_criteria = [
            {"id": criterion_id, "description": description}
            for criterion_id, description in criteria_pairs
            if criterion_id not in covered_ids
        ]
        analysis = raw.get("analysis") or {}
        result = {
            "requirement_id": requirement_id,
            "case_ids": [item.id for item in cases],
            "case_count": len(cases),
            "bound_case_count": len(cases) - len(unbound),
            "unbound_case_ids": [item.id for item in unbound],
            "nodeids": [binding_by_case[item.id].nodeid for item in cases if item.id in binding_by_case],
            "missing_criteria": missing_criteria,
            "analysis_coverage_gaps": analysis.get("coverage_gaps", []),
            "finding_count": len(missing_criteria) + len(analysis.get("coverage_gaps", [])),
        }
        result["_evidence"] = [
            await self._evidence(
                task,
                "coverage",
                EvidenceType.ANALYSIS,
                "Requirement/TestCase/AutomationBinding records",
                f"Found {len(cases)} cases, {len(unbound)} without active automation, and {len(missing_criteria)} uncovered acceptance criterion/criteria.",
                json.dumps(result, ensure_ascii=False),
                {"requirement_id": requirement_id, "case_ids": result["case_ids"], "nodeids": result["nodeids"]},
            )
        ]
        return result

    async def _resolve_requirement_tests(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        coverage = outputs.get("coverage", {})
        excluded = set((outputs.get("generated_run", {}) or {}).get("nodeids", []))
        async with async_session_factory() as session:
            bindings = list(
                (
                    await session.scalars(
                        select(AutomationBindingORM)
                        .join(TestCaseORM, TestCaseORM.id == AutomationBindingORM.test_case_id)
                        .where(
                            TestCaseORM.requirement_id == self._input(task, "requirement_id"),
                            TestCaseORM.project_id == task.project_id,
                            AutomationBindingORM.status == AutomationBindingStatus.ACTIVE.value,
                        )
                    )
                ).all()
            )
        nodeids = list(dict.fromkeys(item.nodeid for item in bindings if item.nodeid not in excluded))
        result = {"nodeids": nodeids, "case_ids": coverage.get("case_ids", []), "total": len(nodeids)}
        result["_evidence"] = [
            await self._evidence(
                task,
                "resolve_tests",
                EvidenceType.RUNTIME_METADATA,
                "AutomationBindingRepository",
                f"Resolved {len(nodeids)} requirement-scoped test node(s).",
                "\n".join(nodeids),
                {"requirement_id": self._input(task, "requirement_id"), "nodeids": nodeids},
            )
        ]
        return result

    async def _review_project_tests(self, task: TaskORM, _outputs: dict[str, Any]) -> dict[str, Any]:
        if not task.workspace_id:
            raise TaskBlocked("Project test review needs an available workspace.")
        report = await WorkspaceService().collect_tests(task.workspace_id)
        paths = list(dict.fromkeys(item.nodeid.split("::", 1)[0] for item in report.tests))[:40]
        findings = []
        for path in paths:
            try:
                source = await self._inspect_source(task, {}, path)
                review = await self._review_source(task, {"inspect": source})
                findings.extend({"file_path": path, **item} for item in review.get("findings", []))
            except (TaskBlocked, SyntaxError) as error:
                findings.append(
                    {"file_path": path, "severity": "MEDIUM", "code": "REVIEW_BLOCKED", "message": str(error)[:500]}
                )
        result = {
            "files_reviewed": paths,
            "files_skipped": max(0, len(report.tests) - len(paths)),
            "findings": findings,
        }
        result["_evidence"] = [
            await self._evidence(
                task,
                "review_project",
                EvidenceType.ANALYSIS,
                "TaskRuntimeService static test review",
                f"Reviewed {len(paths)} test file(s) and found {len(findings)} issue(s). This is a bounded AST review, not a semantic proof.",
                json.dumps(result, ensure_ascii=False),
                {"files_reviewed": paths, "finding_count": len(findings)},
            )
        ]
        return result

    async def _summarize_goal(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        run_results = [outputs[key] for key in ("generated_run", "run", "target_run", "regression") if outputs.get(key)]
        tests = {
            key: sum(int(result.get(field) or 0) for result in run_results)
            for key, field in (("total", "total"), ("passed", "passed"), ("failed", "failed"), ("skipped", "skipped"))
        }
        failures = (outputs.get("run_classify") or {}).get("failures", [])
        coverage = outputs.get("coverage") or {}
        review = outputs.get("review_project") or outputs.get("report") or {}
        generated = outputs.get("generate") or {}
        diagnosis = outputs.get("diagnose") or {}
        changes = []
        if outputs.get("write", {}).get("file_path"):
            changes.append({"file_path": outputs["write"]["file_path"], "kind": "generated_test"})
        if outputs.get("apply", {}).get("file_path"):
            changes.append({"file_path": outputs["apply"]["file_path"], "kind": "repair"})
        target_run = outputs.get("target_run") or {}
        passed_target_nodes = {
            item.get("nodeid") for item in target_run.get("executions", []) if item.get("status") == "PASSED"
        }
        unresolved_failures = [item for item in failures if item.get("nodeid") not in passed_target_nodes]
        unresolved = [
            *coverage.get("missing_criteria", []),
            *coverage.get("analysis_coverage_gaps", []),
            *unresolved_failures,
        ]
        for result in run_results:
            if result.get("blocked_nodeids"):
                unresolved.append(
                    {
                        "nodeids": result["blocked_nodeids"],
                        "reason": "Browser-dependent tests were left unrun because the goal prohibited browser use.",
                    }
                )
        generated_run_failed = (outputs.get("generated_run") or {}).get("status") in {"FAILED", "ERROR"}
        latest_run = (
            outputs.get("regression")
            or outputs.get("target_run")
            or outputs.get("run")
            or outputs.get("generated_run")
            or {}
        )
        if generated_run_failed or latest_run.get("status") in {"FAILED", "ERROR", "BLOCKED"}:
            status = "COMPLETED_WITH_UNRESOLVED"
            verified = False
            next_action = "Review the failure evidence and resolve the listed blocker."
        elif latest_run.get("status") == RunStatus.PASSED.value and not unresolved:
            status = "COMPLETED"
            verified = True
            next_action = "Review the linked Run and evidence."
        elif (
            outputs.get("generate")
            and not outputs.get("write")
            and not any(result.get("blocked_nodeids") for result in run_results)
        ):
            status = "PROPOSAL_READY"
            verified = False
            next_action = "Review the generated test artifact; no source was written."
        elif (outputs.get("diagnose") or {}).get("repairable") and not outputs.get("apply"):
            status = "REPAIR_PROPOSAL_READY"
            verified = False
            next_action = "Review the proposed diff and approve or reject it to continue."
        else:
            status = "COMPLETED_WITH_UNRESOLVED" if unresolved else "COMPLETED"
            verified = False
            next_action = (
                "Review the remaining coverage findings and choose a follow-up goal."
                if unresolved
                else "Review the evidence and choose the next QA goal."
            )
        registration = outputs.get("register") or {}
        if registration.get("registered") is False:
            unresolved.append({"case_ids": registration.get("case_ids", []), "reason": registration.get("reason")})
            status = "COMPLETED_WITH_UNRESOLVED"
            verified = False
            next_action = registration.get("reason", "Review the generated automation and rerun it before binding.")
        if registration.get("unresolved_case_ids"):
            unresolved.append(
                {
                    "case_ids": registration["unresolved_case_ids"],
                    "reason": "Automation for these cases was not run or bound under the requested browser constraint.",
                }
            )
            status = "COMPLETED_WITH_UNRESOLVED"
            verified = False
            next_action = "Run the browser-dependent case tests when browser use is allowed."
        if diagnosis and not diagnosis.get("repairable"):
            unresolved.append(
                {
                    "failure_id": (outputs.get("collect") or {}).get("id"),
                    "classification": diagnosis.get("classification"),
                    "reason": diagnosis.get("root_cause"),
                }
            )
            if status == "COMPLETED" and not verified:
                status = "COMPLETED_WITH_UNRESOLVED"
        async with async_session_factory() as session:
            completed_steps = list(
                (
                    await session.scalars(
                        select(TaskStepORM)
                        .where(
                            TaskStepORM.task_id == task.id,
                            TaskStepORM.status == TaskStepStatus.COMPLETED.value,
                        )
                        .order_by(TaskStepORM.position)
                    )
                ).all()
            )
            artifacts = list(
                (await session.scalars(select(TaskArtifactORM).where(TaskArtifactORM.task_id == task.id))).all()
            )
            invocations = list(
                (
                    await session.scalars(
                        select(AIInvocationORM)
                        .where(AIInvocationORM.task_id == task.id)
                        .order_by(AIInvocationORM.created_at)
                    )
                ).all()
            )
        ai_usage = {
            "providers": sorted({item.provider for item in invocations}),
            "models": sorted({item.model for item in invocations}),
            "calls": len(invocations),
            "latency_ms": sum(float(item.duration_ms or 0) for item in invocations),
            "fallbacks": sum(bool(item.fallback_used) for item in invocations),
            "errors": sum(item.status != "SUCCESS" for item in invocations),
        }
        diagnosis_finding = (
            {
                "failure_id": (outputs.get("collect") or {}).get("id"),
                "classification": diagnosis.get("classification"),
                "root_cause": diagnosis.get("root_cause"),
                "repairable": diagnosis.get("repairable", False),
            }
            if diagnosis
            else None
        )
        goal_contract = (task.inputs or {}).get("_goal_contract", {})
        constraints = []
        if goal_contract.get("no_run") or not goal_contract.get("run_tests", True):
            constraints.append("不运行测试")
        if not goal_contract.get("allow_source_changes", True):
            constraints.append("不修改源码")
        if not goal_contract.get("allow_browser", True):
            constraints.append("不使用浏览器")
        if goal_contract.get("no_full_regression"):
            constraints.append("不跑全量回归")
        summary = {
            "goal": task.goal,
            "status": status,
            "work_completed": [step.name for step in completed_steps],
            "findings": [
                *coverage.get("missing_criteria", []),
                *coverage.get("analysis_coverage_gaps", []),
                *failures,
                *review.get("findings", []),
                *([diagnosis_finding] if diagnosis_finding else []),
            ],
            "changes": changes,
            "tests": tests,
            "runs": [result.get("run_id") for result in run_results if result.get("run_id")],
            "cases": list(
                dict.fromkeys(
                    [*coverage.get("case_ids", []), *[item["case_id"] for item in generated.get("case_bindings", [])]]
                )
            ),
            "artifacts": [{"id": item.artifact_id, "name": item.name, "kind": item.kind} for item in artifacts],
            "unresolved": unresolved,
            "recommended_next_action": next_action,
            "verified": verified,
            "constraints": constraints,
            "ai": ai_usage,
            "requested_scope_without_nodeids": bool(
                (task.inputs or {}).get("_goal_contract", {}).get("no_full_regression")
                and not (task.inputs or {}).get("nodeids")
            ),
        }
        return {
            "summary": summary,
            "verified": verified,
            "_evidence": [
                await self._evidence(
                    task,
                    "goal_summary",
                    EvidenceType.ANALYSIS,
                    "QA Goal result contract",
                    f"{status}: {tests['passed']}/{tests['total']} passed; {len(summary['findings'])} finding(s).",
                    json.dumps(summary, ensure_ascii=False),
                    {"run_ids": summary["runs"], "case_ids": summary["cases"], "status": status},
                )
            ],
        }

    async def _browser_act(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        selected = outputs.get("decide", {}).get("candidate")
        inspected = outputs.get("inspect", {})
        if not selected:
            return {"action": "skipped", "reason": "No safe candidate was available."}
        if not selected.get("safe"):
            raise TaskBlocked("The selected browser action is not classified as safe.")
        risk = classify_browser_action(
            "click",
            name=selected.get("name", ""),
            tag=selected.get("tag", ""),
            href=selected.get("href") or "",
            input_type=selected.get("type", ""),
        )
        if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
            raise TaskBlocked(f"Browser action requires explicit approval: {risk}.")
        from playwright.async_api import async_playwright

        recorder_state = await self._recorder_storage_state(task)

        async with async_playwright() as playwright:
            proxy = browser_proxy_options()
            browser = await launch_chromium(playwright, headless=True, **({"proxy": proxy} if proxy else {}))
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800}, storage_state=recorder_state
                )
                page = await context.new_page()
                await page.goto(inspected["url"], wait_until="domcontentloaded", timeout=20000)
                from app.services.locator_decision_service import LocatorDecisionService

                observed_steps, evidence, artifacts = [], [], []
                visited = set()
                criteria = self._input(task, "observable_text_criteria", [])
                criteria = [str(value)[:200] for value in criteria[:10]] if isinstance(criteria, list) else []
                max_actions = max(1, min(3, int(self._input(task, "max_browser_actions", 3))))
                stop_reason = "action_limit_reached"
                goal_validated = False
                for index in range(max_actions):
                    role, name = selected.get("role"), selected.get("name")
                    risk = classify_browser_action(
                        "click",
                        name=name or "",
                        tag=selected.get("tag", ""),
                        href=selected.get("href") or "",
                        input_type=selected.get("type", ""),
                    )
                    if risk not in {"READ_ONLY", "SAFE_INTERACTION"}:
                        stop_reason = "approval_required"
                        break
                    key = (page.url, role, name)
                    if key in visited:
                        stop_reason = "repeated_action"
                        break
                    visited.add(key)
                    started = time.perf_counter()
                    candidate = {"kind": "role", "value": role, "name": name, "exact": True}
                    verification = await LocatorDecisionService.verify_candidate(page, candidate, {"action": "click"})
                    if not verification["verified"]:
                        stop_reason = "candidate_verification_failed"
                        break
                    before_url = page.url
                    await page.get_by_role(role, name=name, exact=True).click(timeout=10000)
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    title = await page.title()
                    text = (await page.locator("body").inner_text())[:6000]
                    screenshot = await self._artifact(
                        task,
                        "act",
                        f"observe-{index + 1}.png",
                        "SCREENSHOT",
                        await page.screenshot(type="png"),
                        "image/png",
                    )
                    artifacts.append(screenshot)
                    goal_validated = bool(criteria) and all(value in text for value in criteria)
                    observation = {
                        "step": index + 1,
                        "action": "click",
                        "risk": risk,
                        "locator": LocatorDecisionService.format_locator(candidate),
                        "from_url": before_url,
                        "url": page.url,
                        "title": title,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "status": "PASSED",
                        "goal_validated": goal_validated,
                        "screenshot_artifact_id": screenshot["artifact_id"],
                    }
                    observed_steps.append(observation)
                    evidence.append(
                        await self._evidence(
                            task,
                            "act",
                            EvidenceType.RUNTIME_METADATA,
                            "playwright.safe_click",
                            f"Observed safe action {index + 1}: {role} {name!r}.",
                            text,
                            observation,
                            screenshot["artifact_id"],
                        )
                    )
                    await self._record_ai_trace(
                        task.id,
                        {
                            "type": "browser.observation",
                            "stage": "observe",
                            "title": f"Observed browser action {index + 1}",
                            "metadata": observation,
                        },
                    )
                    if goal_validated:
                        stop_reason = "explicit_observation_criteria_matched"
                        break
                    if index + 1 == max_actions:
                        break
                    candidates = await page.locator("a[href],button,[role=button],[role=link]").evaluate_all(
                        r"""els => els.slice(0,60).map((el,index) => ({index,tag:el.tagName.toLowerCase(),role:el.getAttribute('role') || (el.tagName==='A'?'link':'button'),name:(el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\s+/g,' ').slice(0,120),href:el.getAttribute('href'),type:el.getAttribute('type') || ''}))"""
                    )
                    for item in candidates:
                        item["risk"] = classify_browser_action(
                            "click",
                            name=item["name"],
                            tag=item["tag"],
                            href=item["href"] or "",
                            input_type=item["type"],
                        )
                        item["safe"] = (
                            item["risk"] in {"READ_ONLY", "SAFE_INTERACTION"}
                            and (page.url, item["role"], item["name"]) not in visited
                        )
                    decision = await self._decision_select(
                        task, {"inspect": {"url": page.url, "title": title, "candidates": candidates, "_page": page}}
                    )
                    selected = decision.get("candidate")
                    if not selected:
                        stop_reason = "no_verified_safe_candidate"
                        break
                return {
                    "action": "clicked" if observed_steps else "skipped",
                    "goal_validated": goal_validated,
                    "validation_scope": "explicit_observed_text" if criteria else "observations_only",
                    "stop_reason": stop_reason,
                    "url": page.url,
                    "title": await page.title(),
                    "steps": observed_steps,
                    "_evidence": evidence,
                    "_artifacts": artifacts,
                }
            finally:
                await browser.close()

    async def _browser_verify(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        before = outputs.get("inspect", {})
        after = outputs.get("act", {})
        explicit_criteria = after.get("validation_scope") == "explicit_observed_text"
        verified = bool(
            before.get("title") and after.get("steps") and (not explicit_criteria or after.get("goal_validated"))
        )
        if not verified:
            raise TaskBlocked("Browser observations did not satisfy the requested goal criteria.")
        return {
            "verified": verified,
            "kind": "browser_exploration",
            "initial_url": before.get("url"),
            "initial_title": before.get("title"),
            "action_result": after,
            "observations": 1 + len(after.get("steps", [])),
            "goal_validated": after.get("goal_validated", False),
            "validation_scope": after.get("validation_scope", "observations_only"),
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
                task_id=task.id,
                prompt=(f"Replan instructions: {replan_instructions}\n\n{prompt}" if replan_instructions else prompt),
                system_instruction=TASK_CODE_PROMPT.system_instruction,
                response_schema=CodeAssistantResponse,
                prompt_id=TASK_CODE_PROMPT.prompt_id,
                prompt_version=TASK_CODE_PROMPT.version,
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
                        "ai_run_id": response.invocation_id,
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
            raise TaskBlocked(
                "AI returned no structured code proposal.",
                failure_type="AI_OUTPUT_INVALID",
                details={"validation_error": "Structured code proposal was not returned."},
            )
        result = CodeAssistantResponse.model_validate(response.structured_data)
        if not result.suggested_code or not result.suggested_code.strip():
            response_fields = (
                ", ".join(sorted(response.structured_data.keys()))
                if isinstance(response.structured_data, dict)
                else "unavailable"
            )
            reply_excerpt = SensitiveRedactor.redact_text(result.reply or "").strip().replace("\n", " ")[:240]
            detail = f"; model reply: {reply_excerpt}" if reply_excerpt else ""
            raise TaskBlocked(
                "AI returned structured output without suggested_code "
                f"(provider={response.provider}, model={response.model}, fields={response_fields}){detail}. "
                "No source was changed.",
                failure_type="AI_OUTPUT_INVALID",
                details={
                    "provider": response.provider,
                    "model": response.model,
                    "response_fields": response_fields,
                    "validation_error": "Structured response did not include non-empty suggested_code.",
                },
            )
        return result.model_copy(
            update={"provider": response.provider, "model": response.model, "fallback_used": response.fallback_used}
        )

    async def _generate_test(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        recorded_steps = self._input(task, "recorded_steps")
        default_name = str(self._input(task, "test_name", "test_goal_flow"))
        file_path = str(self._input(task, "file_path", f"tests/{default_name}.py"))
        case_bindings: list[dict[str, str]] = []
        if task.type == TaskType.QA_GOAL.value and self._input(task, "requirement_id"):
            case_ids = (outputs.get("coverage") or {}).get("unbound_case_ids", [])
            if len(case_ids) > 20:
                raise TaskBlocked("Automation generation is limited to 20 uncovered cases per goal.")
            async with async_session_factory() as session:
                cases = list(
                    (
                        await session.scalars(
                            select(TestCaseORM).where(
                                TestCaseORM.id.in_(case_ids or [""]),
                                TestCaseORM.project_id == task.project_id,
                                TestCaseORM.requirement_id == self._input(task, "requirement_id"),
                            )
                        )
                    ).all()
                )
            by_id = {case.id: case for case in cases}
            case_bindings = [
                {
                    "case_id": case_id,
                    "test_name": f"test_case_{case_id.replace('-', '_')}",
                    "title": by_id[case_id].title,
                    "preconditions": by_id[case_id].preconditions,
                    "steps": by_id[case_id].steps,
                    "expected_result": by_id[case_id].expected_result,
                }
                for case_id in case_ids
                if case_id in by_id
            ]
            if case_ids and len(case_bindings) != len(case_ids):
                raise TaskBlocked("One or more uncovered cases no longer belong to the selected requirement.")
            if not case_bindings:
                raise TaskBlocked("No uncovered cases remain; automation generation was skipped safely.")
            file_path = f"tests/test_qa_goal_{task.id[:8]}.py"
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
            bundle = ContextSelector().select(WorkspaceService().get_workspace_dir(task.workspace_id), query=task.goal)
            case_instruction = (
                "Generate exactly one top-level pytest test for each listed case, named exactly as provided. Preserve each case's expected result; do not skip, xfail, weaken assertions, or add unrelated tests.\n"
                f"Cases: {json.dumps(case_bindings, ensure_ascii=False)}\n"
                if case_bindings
                else ""
            )
            prompt = (
                "Create one complete pytest test for this QA goal, choosing Python, API or Playwright based on the goal and project fixtures. Use only the observed page details, "
                "goal, requirement and supplied acceptance criteria. Do not invent selectors or APIs. "
                "Return the complete Python test file in suggested_code and a workspace-relative tests/*.py target_file.\n"
                f"{case_instruction}"
                f"Goal: {task.goal}\nRequirement: {self._input(task, 'requirement', '')}\n"
                f"Existing case: {json.dumps(self._input(task, 'case_context', {}), ensure_ascii=False)}\n"
                f"Acceptance criteria: {json.dumps(self._input(task, 'acceptance_criteria', []), ensure_ascii=False)}\n"
                f"Observed page: {json.dumps({k: page.get(k) for k in ('url', 'title', 'accessibility_tree', 'candidates')}, ensure_ascii=False)[:18000]}"
                f"\nRepository conventions, fixtures and reusable page objects:\n{bundle.render()}"
            )
            source = (await self._call_code_ai(task, prompt)).model_dump()
            file_path = file_path if case_bindings else source.get("target_file") or file_path
        code = str(source.get("suggested_code", ""))
        self._validate_python_test(code, file_path)
        if case_bindings:
            names = {
                node.name
                for node in ast.parse(code).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
            }
            expected = {item["test_name"] for item in case_bindings}
            if names != expected:
                raise TaskBlocked("Generated automation must contain exactly one named test for each uncovered case.")
            self._validate_goal_generated_test(code, file_path)
        artifact = await self._artifact(
            task, "generate", Path(file_path).name, "GENERATED_TEST", code.encode("utf-8"), "text/x-python"
        )
        return {
            "target_file": file_path,
            "suggested_code": code,
            "action_type": source.get("action_type", "ai_generated"),
            "case_bindings": case_bindings,
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
                    {
                        "target_file": file_path,
                        "provider": "recorder" if recorded_steps else source.get("provider", "unknown"),
                    },
                    artifact["artifact_id"],
                )
            ],
        }

    @staticmethod
    def _validate_goal_generated_test(code: str, file_path: str) -> None:
        tree = ast.parse(code, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant) and node.test.value is True:
                raise TaskBlocked("QA Goal tests may not pass through a constant-true assertion.")
            if (
                isinstance(node, ast.ExceptHandler)
                and node.body
                and all(isinstance(item, ast.Pass) for item in node.body)
            ):
                raise TaskBlocked("QA Goal tests may not swallow exceptions with a pass-only handler.")
            if isinstance(node, ast.Call):
                func = node.func
                called = (
                    f"{func.value.id}.{func.attr}"
                    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if called in {"pytest.skip", "pytest.xfail", "pytest.importorskip"}:
                    raise TaskBlocked("QA Goal tests may not skip or xfail a requested scenario.")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Attribute)
                        and isinstance(target.value.value, ast.Name)
                        and target.value.value.id == "pytest"
                        and target.value.attr == "mark"
                        and target.attr in {"skip", "skipif", "xfail"}
                    ):
                        raise TaskBlocked("QA Goal tests may not mark a requested scenario skipped or xfailed.")

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
                    raise TaskBlocked(
                        "Generated test imports a process/network/system-control module; refusing execution."
                    )
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "urllib":
                safe_url_parser = (
                    node.level == 0
                    and node.module == "urllib.parse"
                    and all(alias.name in {"unquote", "urlsplit"} and alias.asname is None for alias in node.names)
                )
                if not safe_url_parser:
                    raise TaskBlocked(
                        "Generated test imports a process/network/system-control module; refusing execution."
                    )
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
        if task.type == TaskType.QA_GOAL.value:
            self._validate_goal_generated_test(code, file_path)
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
        repair_branch = False
        if task.current_step_id:
            async with async_session_factory() as session:
                current_step = await session.get(TaskStepORM, task.current_step_id)
                repair_branch = bool(current_step and current_step.key.startswith("repair_"))
        change = (
            outputs.get("repair", {})
            if repair_branch
            else outputs.get("generate") or outputs.get("refactor") or outputs.get("repair", {})
        )
        path = change.get("target_file", change.get("file_path"))
        if not path:
            raise TaskBlocked("No source proposal is available for approval.")
        try:
            original = await WorkspaceService().read_file(task.workspace_id or "", path)
        except FileNotFoundError:
            original = None
        expected = change.get("old_code", outputs.get("inspect", {}).get("source", original))
        if original != expected:
            raise TaskBlocked("Source changed after the proposal was prepared. Replan before approval.")
        updated = str(change.get("suggested_code", change.get("new_code", "")))
        diff = "".join(
            difflib.unified_diff(
                (original or "").splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}" if original is not None else "/dev/null",
                tofile=f"b/{path}",
            )
        )
        if not diff:
            raise TaskBlocked("The proposal contains no source changes.")
        artifact = await self._artifact(
            task, "approval", Path(path).name + ".diff", "PATCH_PROPOSAL", diff.encode(), "text/x-diff"
        )
        summary = {
            "file_path": path,
            "change_kind": task.type,
            "preview": diff[:12000],
            "preview_truncated": len(diff) > 12000,
            "artifact_id": artifact["artifact_id"],
            "base_exists": original is not None,
            "base_sha256": hashlib.sha256(original.encode()).hexdigest() if original is not None else None,
        }
        async with async_session_factory() as session:
            repo = TaskRepository(session)
            row = await repo.get(task.id)
            if row:
                row.context = {**row.context, "pending_change_summary": summary}
                await repo.add_artifact(task_id=task.id, step_id=task.current_step_id, **artifact)
                await repo.add_event(task.id, "step.progress", {"type": "approval.requested", **summary})
                await session.commit()
        raise ApprovalRequired()

    async def _write_approved_source(self, task: TaskORM, outputs: dict[str, Any], path: str, code: str) -> None:
        if not self._approval_granted(outputs):
            raise TaskBlocked("Source cannot be applied without explicit approval.")
        async with async_session_factory() as session:
            row = await TaskRepository(session).get(task.id)
            summary = (row.context or {}).get("pending_change_summary", {}) if row else {}
        if summary.get("file_path") != path or "base_exists" not in summary:
            raise TaskBlocked("Approval has no source baseline. Replan and review the Diff.")
        try:
            await WorkspaceService().write_file_if_unchanged(
                task.workspace_id or "", path, code, summary["base_exists"], summary.get("base_sha256")
            )
        except FileExistsError as exc:
            raise TaskBlocked(
                "Source changed while awaiting approval. Existing edits were preserved; replan and review a new Diff."
            ) from exc

    async def _write_generated(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        change = outputs.get("generate") or outputs.get("refactor")
        if not change:
            raise TaskBlocked("No approved generated source is available.")
        await self._write_approved_source(task, outputs, change["target_file"], change["suggested_code"])
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
            from app.persistence.models import BrowserSessionORM
            from app.services.failure_evidence_service import FailureEvidenceService

            browser = (
                (
                    await session.execute(
                        select(BrowserSessionORM)
                        .where(BrowserSessionORM.case_execution_id == failure.execution_id)
                        .order_by(BrowserSessionORM.started_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            page = browser.page_evidence_json if browser else None
            if isinstance(page, str):
                try:
                    page = json.loads(page)
                except ValueError:
                    page = {}
            evidence_bundle = await FailureEvidenceService.collect(
                failure, session, WorkspaceService(), browser=browser, page=page
            )
            result = {
                "id": failure.id,
                "run_id": failure.run_id,
                "test_nodeid": failure.test_nodeid,
                "classification": failure.classification,
                "exception_type": failure.exception_type,
                "error_message": SensitiveRedactor.redact_text(failure.error_message or ""),
                "stack_trace": SensitiveRedactor.redact_text(failure.stack_trace or "")[-12000:],
                "failing_locator": SensitiveRedactor.redact_text(failure.failing_locator or "") or None,
                "screenshot_path": failure.screenshot_path,
                "trace_path": failure.trace_path,
                "dom_snapshot_path": failure.dom_snapshot_path,
                "repair_proposal": SensitiveRedactor.redact_value(failure.repair_proposal)
                if failure.repair_proposal
                else None,
                "evidence_bundle": evidence_bundle.model_dump(mode="json"),
                "rendered_evidence": evidence_bundle.render(),
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
            repairable = rules.get("classification") == "LOCATOR_CHANGED" and bool(
                (failure.get("evidence_bundle") or {}).get("page_url")
                and (failure.get("evidence_bundle") or {}).get("controls")
                or self._input(task, "proposed_locator")
                or failure.get("repair_proposal")
            )
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
                "repairable": repairable,
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
            historical_context="Current bounded evidence (not historical proof):\n"
            + failure.get("rendered_evidence", "No additional evidence captured."),
        )
        completion = orchestrator.last_completion
        ai_fallback = (not completion) or completion.fallback_used or completion.provider.lower() == "fake"
        # Treat direct traceback classification as the evidence boundary. AI can enrich the
        # explanation, but cannot overwrite a clearly observed assertion/timeout category. If
        # the provider fell back to a local/fake completion, report the rule explanation instead
        # of presenting fallback prose as an AI root-cause finding.
        classification = rules.get("classification", "UNKNOWN")
        evidence_bundle = failure.get("evidence_bundle") or {}
        repairable = classification == "LOCATOR_CHANGED" and bool(
            evidence_bundle.get("page_url")
            and evidence_bundle.get("controls")
            or self._input(task, "proposed_locator")
            or failure.get("repair_proposal")
        )
        result = {
            "classification": classification,
            "root_cause": rules.get("root_cause") if ai_fallback else analysis.root_cause,
            "evidence": analysis.evidence,
            "hypotheses": analysis.hypotheses,
            "recommended_actions": analysis.recommended_actions,
            "confidence": analysis.confidence,
            "provider": "FailureClassifier" if ai_fallback else completion.provider,
            "fallback_used": ai_fallback,
            "repairable": repairable,
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
        failure_evidence = failure.get("evidence_bundle") or {}
        observed_controls = failure_evidence.get("controls") or []
        has_failure_page_observation = bool(failure_evidence.get("page_url") and observed_controls)

        if not proposed:
            test_name = str(failure.get("test_nodeid") or "").split("::")[-1]
            tree = ast.parse(source)
            functions = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test_name
            ]
            for function in functions:
                for assertion in (node for node in ast.walk(function) if isinstance(node, ast.Assert)):
                    expression = assertion.test
                    if (
                        isinstance(expression, ast.Compare)
                        and len(expression.ops) == 1
                        and isinstance(expression.ops[0], ast.Eq)
                    ):
                        try:
                            left, right = ast.literal_eval(expression.left), ast.literal_eval(expression.comparators[0])
                        except (ValueError, TypeError):
                            continue
                        if left != right:
                            raise TaskBlocked(
                                "The failed test contains a deterministically false literal assertion. Confirm the intended expectation before proposing a code change; the assertion is retained."
                            )

        if proposed and old_locator and old_locator in source:
            updated = source.replace(old_locator, proposed, 1)
        else:
            if (
                diagnosis.get("classification") == "LOCATOR_CHANGED"
                and not failure.get("dom_snapshot_path")
                and not has_failure_page_observation
                and not self._input(task, "url")
                and not proposed
            ):
                raise TaskBlocked(
                    "Locator repair needs a DOM snapshot, a failure-time browser observation with a page URL and observed controls, or a user-supplied proposed_locator; no source was changed."
                )
            result = await self._call_code_ai(
                task,
                "Repair the failing test based on the exact failure evidence and inspected source. "
                "Keep the change minimal. Preserve business expectations and assertions; never change an expected value merely to make a test pass. Return the complete replacement test module in suggested_code; "
                "do not claim a repair if the evidence is insufficient.\n"
                f"Goal: {task.goal}\nClassification: {diagnosis.get('classification')}\n"
                f"User-proposed locator candidate: {proposed or 'none'}\n"
                f"Failure: {failure.get('error_message')}\nTraceback:\n{failure.get('stack_trace')}\n"
                f"Source path: {path}\nSource:\n{source}\n"
                f"Bounded source, fixtures and execution evidence:\n{failure.get('rendered_evidence', '')}\n"
                "Use any page URL and observed controls from the failure evidence bundle above to ground locator changes. "
                "If that evidence does not support a safe replacement, return the source unchanged.",
            )
            updated = result.suggested_code or ""
            original_assertions = [
                ast.dump(node, include_attributes=False)
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Assert)
            ]
            proposed_assertions = [
                ast.dump(node, include_attributes=False)
                for node in ast.walk(ast.parse(updated))
                if isinstance(node, ast.Assert)
            ]
            if original_assertions != proposed_assertions:
                raise TaskBlocked(
                    "AI repair changed an existing assertion. The proposal was not applied; review intended expectations explicitly."
                )
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
        await self._write_approved_source(task, outputs, proposal["file_path"], proposal["suggested_code"])
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
        contract = self._input(task, "_goal_contract", {}) or {}
        if task.type == TaskType.QA_GOAL.value and not contract.get("allow_browser", True):
            runnable, blocked = self._without_browser(task, nodeids)
            if not runnable:
                return {"status": "BLOCKED", "nodeids": [], "blocked_nodeids": blocked, "total": 0}
            result = await self._execute_pytest(task, runnable)
            return {**result, "blocked_nodeids": blocked}
        return await self._execute_pytest(task, nodeids)

    async def _register_test_case(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
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
            async with async_session_factory() as session:
                for item in case_bindings:
                    nodeid = f"{generated['target_file']}::{item['test_name']}"
                    if nodeid not in nodeids:
                        blocked_case_ids.append(item["case_id"])
                        continue
                    case = await session.get(TestCaseORM, item["case_id"])
                    if (
                        case is None
                        or case.project_id != task.project_id
                        or case.requirement_id != self._input(task, "requirement_id")
                    ):
                        raise TaskBlocked("Generated test evidence does not match its requirement case.")
                    await AutomationBindingRepository(session).create_or_update(
                        AutomationBindingCreate(
                            test_case_id=case.id,
                            workspace_id=task.workspace_id,
                            nodeid=nodeid,
                            file_path=generated["target_file"],
                            framework=FrameworkType.PLAYWRIGHT_PYTHON,
                            status=AutomationBindingStatus.ACTIVE,
                        )
                    )
                    case.automation_status = AutomationStatus.AUTOMATED.value
                    registrations.append({"case_id": case.id, "nodeid": nodeid})
                await session.commit()
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
        recorded_steps = self._input(task, "recorded_steps", []) or []
        title = str(self._input(task, "case_name", task.goal))[:250]
        async with async_session_factory() as session:
            existing = (
                await session.get(TestCaseORM, str(self._input(task, "test_case_id")))
                if self._input(task, "test_case_id")
                else None
            )
            existing = (
                existing
                or (
                    await session.execute(
                        select(TestCaseORM).where(
                            TestCaseORM.project_id == task.project_id,
                            TestCaseORM.external_system == "AGENT_TASK",
                            TestCaseORM.external_case_id == task.id,
                        )
                    )
                ).scalar_one_or_none()
            )
            if existing is None:
                existing = await TestCaseRepository(session).create(
                    TestCaseCreate(
                        project_id=task.project_id,
                        title=title,
                        steps=[
                            str(step.get("description", ""))
                            for step in recorded_steps
                            if isinstance(step, dict) and step.get("description")
                        ],
                        expected_result=str(self._input(task, "requirement", ""))[:2000],
                        automation_status=AutomationStatus.AUTOMATED,
                        tags=["ai-generated"],
                        external_system="AGENT_TASK",
                        external_case_id=task.id,
                    )
                )
            await AutomationBindingRepository(session).create_or_update(
                AutomationBindingCreate(
                    test_case_id=existing.id,
                    workspace_id=task.workspace_id,
                    nodeid=str(nodeids[0]),
                    file_path=str(generated["target_file"]),
                    framework=FrameworkType.PLAYWRIGHT_PYTHON,
                    status=AutomationBindingStatus.ACTIVE,
                )
            )
            existing.automation_status = AutomationStatus.AUTOMATED.value
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
        return await self._execute_pytest(
            task,
            nodeids[:100],
            parent_run_id=outputs.get("collect", {}).get("run_id"),
            origin_failure_id=outputs.get("collect", {}).get("id"),
        )

    async def _run_regression(self, task: TaskORM, outputs: dict[str, Any]) -> dict[str, Any]:
        nodeids = self._input(task, "regression_nodeids", []) or self._input(task, "nodeids", [])
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
        contract = self._input(task, "_goal_contract", {}) or {}
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
    def _without_browser(task: TaskORM, nodeids: list[str]) -> tuple[list[str], list[str]]:
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
        task: TaskORM,
        nodeids: list[str],
        *,
        parent_run_id: str | None = None,
        origin_failure_id: str | None = None,
    ) -> dict[str, Any]:
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
            parent_run_id=(parent_run_id or self._input(task, "run_id"))
            if task.type in {TaskType.FIX_FAILURE.value, TaskType.QA_GOAL.value}
            else None,
            origin_failure_id=origin_failure_id or self._input(task, "failure_id")
            if task.type in {TaskType.FIX_FAILURE.value, TaskType.QA_GOAL.value}
            else None,
        )
        deadline = active_task_deadline.get() or time.monotonic() + task.max_duration_seconds
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
                    task.id,
                    "step.progress",
                    {
                        "type": "child_run.started",
                        "run_id": child_run.id,
                        "nodeids": nodeids,
                        "step_id": active_runtime_step.get(),
                    },
                )
                await session.commit()

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
        run_id = run.get("run_id")
        async with async_session_factory() as session:
            records = (
                list((await session.scalars(select(FailureRecordORM).where(FailureRecordORM.run_id == run_id))).all())
                if run_id
                else []
            )
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
                await self._evidence(
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
