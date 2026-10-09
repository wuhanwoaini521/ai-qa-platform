from __future__ import annotations

import hashlib
import json
from typing import Any

from project_model.models import RunStatus
from project_model.task_models import (
    EvidenceType,
    TaskCreate,
    TaskGoalPreview,
    TaskGoalPreviewStep,
    TaskType,
)

from app.domain.task_records import TaskRecord as TaskExecutionRecord
from app.services.requirement_lifecycle_service import RequirementLifecycleService
from app.services.task_errors import TaskBlocked
from app.services.task_execution_ports import TaskExecutionPorts
from app.services.task_workflows import build_qa_goal_plan, parse_qa_goal
from app.services.workspace_service import WorkspaceService
from app.settings import get_config


class TaskGoalService:
    """Own QA goal planning, requirement coverage, and result synthesis."""

    def __init__(self, context: TaskExecutionPorts) -> None:
        self.context = context

    @staticmethod
    def apply_runtime_limits(data: TaskCreate) -> TaskCreate:
        config = get_config()
        if not config.agent.enabled:
            raise ValueError("Agent task execution is disabled by config/config.yaml.")
        explicit = data.model_fields_set
        return data.model_copy(
            update={
                "max_steps": min(data.max_steps, config.agent.max_steps)
                if "max_steps" in explicit
                else config.agent.max_steps,
                "max_retries": min(data.max_retries, config.agent.max_retries)
                if "max_retries" in explicit
                else config.agent.max_retries,
                "max_duration_seconds": min(data.max_duration_seconds, int(config.agent.max_runtime_seconds))
                if "max_duration_seconds" in explicit
                else int(config.agent.max_runtime_seconds),
                "max_ai_calls": min(data.max_ai_calls, config.ai.budget.max_task_calls)
                if config.ai.budget.enabled and "max_ai_calls" in explicit
                else config.ai.budget.max_task_calls
                if config.ai.budget.enabled
                else data.max_ai_calls,
            }
        )

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

    async def preview_goal(self, data: TaskCreate) -> TaskGoalPreview:
        data = self.apply_runtime_limits(data)
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
            "inputs_hash": request_inputs_hash or TaskGoalService._goal_request_inputs_hash(data.inputs),
            "contract": contract,
            "facts": facts,
            "plan": [step.model_dump(mode="json") for step in plan],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _compile_goal(self, data: TaskCreate):
        contract = parse_qa_goal(data.goal, data.inputs)
        async with self.context.repository_scope() as repositories:
            project = await repositories.projects.get_by_id(data.project_id)
            if project is None:
                raise ValueError("Project not found.")
            workspace_repository = repositories.workspaces
            workspace_row = await workspace_repository.get_by_id(data.workspace_id)
            if workspace_row is None:
                workspace_row = await workspace_repository.get_by_project_id(data.workspace_id)
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
                "workspace_snapshot_hash": self.context.workspace_source_digest(workspace_row.project_id),
            }
            if contract["target"] == "requirement" and contract["requirement_id"]:
                requirement = await repositories.requirements.get_by_id(contract["requirement_id"])
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
                designs = await repositories.test_designs.list_by_requirement(requirement.id)
                cases = await repositories.test_cases.list_by_requirement(requirement.id, data.project_id)
                case_ids = [case.id for case in cases]
                bindings = await repositories.automation_bindings.list_active_for_cases(case_ids)
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
                case = await repositories.test_cases.get_by_id(contract["test_case_id"])
                if case is None or case.project_id != data.project_id:
                    raise ValueError("Selected test case not found in the selected project.")
                if (
                    case.requirement_id
                    and contract["requirement_id"]
                    and contract["requirement_id"] != case.requirement_id
                ):
                    raise ValueError("Selected test case belongs to a different requirement.")
                binding = await repositories.automation_bindings.get_by_test_case_id(case.id)
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
                run_repository = repositories.test_runs
                failure = await run_repository.get_failure_by_id(contract["failure_id"])
                run = await run_repository.get_by_id(failure.run_id) if failure else None
                if failure is None or run is None or run.project_id != data.project_id:
                    raise ValueError("Selected failure not found in the selected project.")
                facts["context_label"] = f"{failure.test_name or failure.test_nodeid} · {failure.id[:8]}"
            elif contract["target"] == "project":
                facts["context_label"] = project.name or data.project_id

        plan = build_qa_goal_plan(contract, facts)
        if not plan:
            raise ValueError("This goal has no safe, registered capability for the selected context.")
        return contract, facts, plan

    async def _materialize_goal_cases(self, task: TaskExecutionRecord, _outputs: dict[str, Any]) -> dict[str, Any]:
        requirement_id = str(self.context.input(task, "requirement_id", "")).strip()
        if not requirement_id:
            raise TaskBlocked("Creating requirement cases needs a selected requirement.")

        lifecycle = RequirementLifecycleService(repository_scope=self.context.repository_scope)
        async with self.context.repository_scope() as repositories:
            before = {item.id for item in await repositories.test_cases.list_by_requirement(requirement_id)}
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
            await self.context.evidence(
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

    async def _inspect_goal_coverage(self, task: TaskExecutionRecord, _outputs: dict[str, Any]) -> dict[str, Any]:
        requirement_id = str(self.context.input(task, "requirement_id", "")).strip()
        if not requirement_id:
            raise TaskBlocked("Coverage inspection needs a selected requirement.")
        async with self.context.repository_scope() as repositories:
            requirement = await repositories.requirements.get_by_id(requirement_id)
            if requirement is None or requirement.project_id != task.project_id:
                raise TaskBlocked("Requirement no longer belongs to this project.")
            cases = await repositories.test_cases.list_by_requirement(requirement_id, task.project_id)
            bindings = await repositories.automation_bindings.list_active_for_cases([item.id for item in cases])
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
            await self.context.evidence(
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

    async def _resolve_requirement_tests(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
        coverage = outputs.get("coverage", {})
        excluded = set((outputs.get("generated_run", {}) or {}).get("nodeids", []))
        async with self.context.repository_scope() as repositories:
            bindings = await repositories.automation_bindings.list_active_by_requirement(
                task.project_id or "", self.context.input(task, "requirement_id")
            )
        nodeids = list(dict.fromkeys(item.nodeid for item in bindings if item.nodeid not in excluded))
        result = {"nodeids": nodeids, "case_ids": coverage.get("case_ids", []), "total": len(nodeids)}
        result["_evidence"] = [
            await self.context.evidence(
                task,
                "resolve_tests",
                EvidenceType.RUNTIME_METADATA,
                "AutomationBindingRepository",
                f"Resolved {len(nodeids)} requirement-scoped test node(s).",
                "\n".join(nodeids),
                {"requirement_id": self.context.input(task, "requirement_id"), "nodeids": nodeids},
            )
        ]
        return result

    async def _review_project_tests(self, task: TaskExecutionRecord, _outputs: dict[str, Any]) -> dict[str, Any]:
        if not task.workspace_id:
            raise TaskBlocked("Project test review needs an available workspace.")
        report = await WorkspaceService().collect_tests(task.workspace_id)
        paths = list(dict.fromkeys(item.nodeid.split("::", 1)[0] for item in report.tests))[:40]
        findings = []
        for path in paths:
            try:
                source = await self.context.inspect_source(task, {}, path)
                review = await self.context.review_source(task, {"inspect": source})
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
            await self.context.evidence(
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

    async def _summarize_goal(self, task: TaskExecutionRecord, outputs: dict[str, Any]) -> dict[str, Any]:
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
        async with self.context.repository_scope() as repositories:
            repository = repositories.tasks
            completed_steps = await repository.completed_steps(task.id)
            artifacts = await repository.artifacts_for_task(task.id)
            invocations = await repository.ai_invocations_for_task(task.id)
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
                await self.context.evidence(
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
