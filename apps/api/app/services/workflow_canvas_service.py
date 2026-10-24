"""Project existing records into the read-only workflow canvas.

One query per entity family, one node per real record. Nothing is invented: an empty
project yields the stage columns and no nodes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from project_model.workflow_canvas import (
    DiscoveryEvidenceMetrics,
    DiscoveryEvidenceRef,
    DiscoveryIntelligenceMetrics,
    DiscoveryMetrics,
    WorkflowCanvas,
    WorkflowEdge,
    WorkflowEvidenceRef,
    WorkflowNode,
    WorkflowStage,
)

from app.repositories.discovery_evidence_repo import DiscoveryEvidenceRepository
from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository
from app.repositories.quality_discovery_repo import QualityDiscoveryRepository
from app.services.automation_binding_service import AutomationBindingService
from app.services.discovery_evidence_analysis import analyze_collection
from app.services.discovery_intelligence_service import suggestion_summary
from app.services.failure_service import FailureService
from app.services.failure_workflow_service import FailureWorkflowService
from app.services.task_command_service import TaskCommandService
from app.services.test_run_service import TestRunService

STAGES: tuple[WorkflowStage, ...] = (
    WorkflowStage(key="discovery", title="发现", kind="DISCOVERY", description="探索产品并对照需求与覆盖"),
    WorkflowStage(key="recorder", title="录制", kind="RECORDER", description="把真实点击录成可编辑步骤"),
    WorkflowStage(key="studio", title="编辑", kind="STUDIO", description="在工作区改用例代码"),
    WorkflowStage(key="run", title="运行", kind="RUN", description="执行测试并留下证据"),
    WorkflowStage(key="failure", title="失败", kind="FAILURE", description="失败记录与源码位置"),
    WorkflowStage(key="analysis", title="分析", kind="FAILURE_ANALYSIS", description="AI + Jev 根因与修复提案"),
    WorkflowStage(key="approval", title="人工审批", kind="HUMAN_APPROVAL", description="未批准不改代码"),
    WorkflowStage(key="verification", title="精确验证", kind="EXACT_VERIFICATION", description="同一用例重跑并验证"),
)

MAX_DISCOVERY_RUNS = 3
MAX_RECORDER = 4
MAX_RUNS = 6
MAX_FAILURES = 4
MAX_TASKS = 40


def _duration_ms(started: datetime | None, finished: datetime | None) -> int | None:
    if started is None or finished is None:
        return None
    return max(0, int((finished - started).total_seconds() * 1000))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class WorkflowCanvasService:
    def __init__(
        self,
        *,
        runs: TestRunService,
        failures: FailureService,
        workflow: FailureWorkflowService,
        discovery: QualityDiscoveryRepository,
        evidence: DiscoveryEvidenceRepository,
        suggestions: DiscoverySuggestionRepository,
        bindings: AutomationBindingService,
    ) -> None:
        self.runs = runs
        self.failures = failures
        self.workflow = workflow
        self.discovery = discovery
        self.evidence = evidence
        self.suggestions = suggestions
        self.bindings = bindings

    async def build(
        self,
        project_id: str,
        owner_id: str,
        *,
        tasks: TaskCommandService,
        requirement_id: str | None = None,
    ) -> WorkflowCanvas:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        all_runs = await self.runs.list_runs(project_id=project_id)
        failure_rows = await self.failures.list_failures(project_id=project_id, limit=MAX_FAILURES)
        # The latest runs plus the runs a listed failure came from, so the repair chain
        # stays visible even when its run is older than the newest six.
        run_rows = list(all_runs[:MAX_RUNS])
        displayed = {run.id for run in run_rows}
        by_id = {run.id: run for run in all_runs}
        for failure in failure_rows:
            run = by_id.get(failure.run_id)
            if run is not None and run.id not in displayed:
                run_rows.append(run)
                displayed.add(run.id)
        task_rows = await tasks.list(owner_id, project_id=project_id, limit=MAX_TASKS)
        discovery_rows = await self.discovery.list_by_project(
            project_id, MAX_DISCOVERY_RUNS + 1, requirement_id=requirement_id
        )
        discovery_match_count = await self.discovery.count_by_project(project_id, requirement_id=requirement_id)
        discovery_truncated = discovery_match_count > MAX_DISCOVERY_RUNS
        discovery_rows = discovery_rows[:MAX_DISCOVERY_RUNS]
        binding_rows = (await self.bindings.list_recorded(project_id))[:MAX_RECORDER]

        task_by_failure: dict[str, Any] = {}
        for task in task_rows:
            failure_id = _mapping(task.inputs).get("failure_id")
            if isinstance(failure_id, str) and task.type.value == "FIX_FAILURE":
                task_by_failure.setdefault(failure_id, task)

        # Discovery instances ------------------------------------------------------
        discovery_ids: set[str] = set()
        for row in discovery_rows:
            result = _mapping(row.result)
            metrics = await self._discovery_metrics_async(row.id, result)
            node = WorkflowNode(
                id=f"discovery:{row.id}",
                kind="DISCOVERY",
                stage="discovery",
                title=f"探索 {row.mode}",
                subtitle=row.start_url,
                status=row.status,
                entity_type="discovery_run",
                entity_id=row.id,
                task_id=_mapping(result).get("runtime_task_id"),
                started_at=row.created_at,
                finished_at=row.finished_at,
                duration_ms=_duration_ms(row.created_at, row.finished_at),
                inputs={"mode": row.mode, "start_url": row.start_url, "requirement_id": row.requirement_id},
                outputs={
                    "states": metrics.states,
                    "actions": metrics.actions,
                    "features": metrics.features,
                    "gaps": metrics.gaps,
                    "error": row.error,
                    "progress": _mapping(row.progress),
                },
                evidence=[
                    WorkflowEvidenceRef(kind="api", label="探索详情", ref=f"/api/discovery/runs/{row.id}"),
                    WorkflowEvidenceRef(kind="api", label="质量地图", ref=f"/api/discovery/runs/{row.id}/quality-map"),
                    WorkflowEvidenceRef(kind="api", label="结构证据", ref=f"/api/discovery/runs/{row.id}/evidence"),
                    WorkflowEvidenceRef(
                        kind="api", label="候选场景与覆盖", ref=f"/api/discovery/runs/{row.id}/scenarios"
                    ),
                ],
                links={
                    "workspace": f"/workspace/{project_id}?stage=discover&view=discover&projectId={project_id}",
                    "api": f"/api/discovery/runs/{row.id}",
                    "evidence": f"/api/discovery/runs/{row.id}/evidence",
                    "scenarios": f"/api/discovery/runs/{row.id}/scenarios",
                    "diff": f"/api/discovery/runs/{row.id}/evidence/diff",
                },
                metrics=metrics,
                evidence_index=self._discovery_evidence(row, result),
            )
            nodes.append(node)
            discovery_ids.add(row.id)

        # Recorder instances -------------------------------------------------------
        recorder_nodes: dict[str, WorkflowNode] = {}
        studio_nodes: dict[str, WorkflowNode] = {}
        for binding in binding_rows:
            node = WorkflowNode(
                id=f"recorder:{binding.id}",
                kind="RECORDER",
                stage="recorder",
                title=f"录制 {len(binding.recorder_steps)} 步",
                subtitle=binding.file_path,
                status=binding.status.value,
                entity_type="automation_binding",
                entity_id=binding.id,
                parent_id=f"case:{binding.test_case_id}",
                inputs={"test_case_id": binding.test_case_id, "nodeid": binding.nodeid},
                outputs={"steps": len(binding.recorder_steps), "file_path": binding.file_path},
                evidence=[
                    WorkflowEvidenceRef(
                        kind="step",
                        label=f"{step['action']} · {step.get('locator') or '未记录定位器'}",
                        ref=step.get("evidence_id"),
                    )
                    for step in binding.recorder_steps
                ],
                links={
                    "workspace": (
                        f"/workspace/{project_id}?stage=automation&view=browser&projectId={project_id}"
                        f"&caseId={binding.test_case_id}&file={binding.file_path}"
                    ),
                },
            )
            nodes.append(node)
            recorder_nodes[binding.nodeid] = node

            studio = studio_nodes.get(binding.file_path)
            if studio is None:
                studio = WorkflowNode(
                    id=f"studio:{binding.file_path}",
                    kind="STUDIO",
                    stage="studio",
                    title=binding.file_path,
                    subtitle=binding.nodeid,
                    status="READY",
                    entity_type="workspace_file",
                    entity_id=binding.file_path,
                    outputs={"nodeid": binding.nodeid},
                    links={
                        "workspace": (
                            f"/workspace/{project_id}?stage=automation&view=code&projectId={project_id}"
                            f"&caseId={binding.test_case_id}&file={binding.file_path}"
                        ),
                        "api": f"/api/workspaces/{project_id}/file?path={binding.file_path}",
                    },
                )
                studio_nodes[binding.file_path] = studio
                nodes.append(studio)
            edges.append(
                WorkflowEdge(
                    id=f"edge:recorder:{binding.id}:studio",
                    source=node.id,
                    target=studio.id,
                    kind="RECORDED_INTO",
                    label="录制写入",
                )
            )

        # Run + failure instances --------------------------------------------------
        failure_by_run: dict[str, list[Any]] = {}
        for failure in failure_rows:
            failure_by_run.setdefault(failure.run_id, []).append(failure)

        run_nodes: dict[str, WorkflowNode] = {}
        for run in run_rows:
            node = WorkflowNode(
                id=f"run:{run.id}",
                kind="RUN",
                stage="run",
                title=f"运行 {run.id[:12]}",
                subtitle=", ".join(run.nodeids[:2]) or None,
                status=run.status.value if hasattr(run.status, "value") else str(run.status),
                entity_type="test_run",
                entity_id=run.id,
                task_id=run.task_id,
                parent_id=f"run:{run.parent_run_id}" if run.parent_run_id else None,
                started_at=getattr(run, "created_at", None),
                finished_at=getattr(run, "updated_at", None),
                duration_ms=int(run.duration_ms) if run.duration_ms else None,
                inputs={"nodeids": run.nodeids, "browser": run.browser},
                outputs={
                    "total": run.total,
                    "passed": run.passed,
                    "failed": run.failed,
                    "skipped": run.skipped,
                },
                evidence=[
                    WorkflowEvidenceRef(kind="api", label="运行详情", ref=f"/api/runs/{run.id}"),
                    *[WorkflowEvidenceRef(kind="nodeid", label=nodeid) for nodeid in run.nodeids[:3]],
                ],
                links={"run": f"/runs/{run.id}", "api": f"/api/runs/{run.id}"},
            )
            nodes.append(node)
            run_nodes[run.id] = node
            for file_path in {nodeid.split("::")[0] for nodeid in run.nodeids}:
                studio = studio_nodes.get(file_path)
                if studio is not None:
                    edges.append(
                        WorkflowEdge(
                            id=f"edge:studio:{studio.id}:run:{run.id}",
                            source=studio.id,
                            target=node.id,
                            kind="RAN_AS",
                            label="运行",
                        )
                    )

        for failure in [row for row in failure_rows if row.run_id in run_nodes]:
            failure_node = WorkflowNode(
                id=f"failure:{failure.id}",
                kind="FAILURE",
                stage="failure",
                title=failure.test_name or failure.test_nodeid,
                subtitle="" if not failure.source_file else f"{failure.source_file}:{failure.source_line or '?'}",
                status=failure.classification,
                entity_type="failure",
                entity_id=failure.id,
                parent_id=f"run:{failure.run_id}",
                started_at=failure.created_at,
                inputs={"nodeid": failure.test_nodeid, "exception": failure.exception_type},
                outputs={
                    "message": failure.error_message,
                    "source_file": failure.source_file,
                    "source_line": failure.source_line,
                    "failing_locator": failure.failing_locator,
                },
                evidence=[
                    ref
                    for ref in (
                        WorkflowEvidenceRef(kind="screenshot", label="失败截图", ref=failure.screenshot_path),
                        WorkflowEvidenceRef(kind="trace", label="Playwright trace", ref=failure.trace_path),
                        WorkflowEvidenceRef(kind="dom", label="DOM 快照", ref=failure.dom_snapshot_path),
                        WorkflowEvidenceRef(kind="console", label=f"控制台日志 {len(failure.console_logs)} 条")
                        if failure.console_logs
                        else None,
                    )
                    if ref is not None
                ],
                links={
                    "failure": f"/failures/{failure.id}",
                    "debug": (
                        f"/workspace/{project_id}?stage=failure&view=debug&projectId={project_id}"
                        f"&failureId={failure.id}&file={failure.source_file or ''}"
                    ),
                    "api": f"/api/failures/{failure.id}",
                },
            )
            nodes.append(failure_node)
            source_run = run_nodes.get(failure.run_id)
            if source_run is not None:
                edges.append(
                    WorkflowEdge(
                        id=f"edge:run:{failure.run_id}:failure:{failure.id}",
                        source=source_run.id,
                        target=failure_node.id,
                        kind="FAILED_AS",
                        label="失败",
                    )
                )

            history = await self.workflow.list_history(failure.id)
            analysis = history[0] if history else None
            if analysis is not None:
                analysis_id = str(analysis.get("id"))
                events = _sequence(analysis.get("events"))
                result = _mapping(analysis.get("result"))
                analysis_node = WorkflowNode(
                    id=f"analysis:{analysis_id}",
                    kind="FAILURE_ANALYSIS",
                    stage="analysis",
                    title="AI + Jev 根因分析",
                    subtitle=f"{len(events)} 条事件 · {len(history)} 次尝试",
                    status=str(analysis.get("status")),
                    entity_type="failure_analysis",
                    entity_id=analysis_id,
                    parent_id=failure_node.id,
                    started_at=analysis.get("created_at"),
                    finished_at=analysis.get("finished_at"),
                    inputs={"attempts": len(history)},
                    outputs={
                        "block_reason": result.get("block_reason"),
                        "repair_state": result.get("repair_state"),
                        "has_proposal": bool(result.get("repair_proposal") or result.get("diagnosis")),
                        "last_event": str(_mapping(events[-1]).get("type")) if events else None,
                    },
                    evidence=[
                        WorkflowEvidenceRef(
                            kind="event",
                            label=str(_mapping(event).get("type")),
                            ref=str(_mapping(event).get("message") or ""),
                        )
                        for event in events[-3:]
                    ],
                    links={"failure": f"/failures/{failure.id}", "api": f"/api/failures/{failure.id}/analyses"},
                )
                nodes.append(analysis_node)
                edges.append(
                    WorkflowEdge(
                        id=f"edge:failure:{failure.id}:analysis:{analysis_id}",
                        source=failure_node.id,
                        target=analysis_node.id,
                        kind="ANALYZED_BY",
                        label="分析",
                    )
                )
                analysis_node_id = analysis_node.id
            else:
                analysis_node_id = None

            task = task_by_failure.get(failure.id)
            approval_step = None
            verify_step = None
            if task is not None:
                approval_step = next((step for step in task.plan if step.key == "approval"), None)
                verify_step = next((step for step in task.plan if step.key == "verify"), None)

            repair = await self.workflow.get_repair_workflow(failure.id)
            approval_status = approval_step.status.value if approval_step is not None else repair.state.value
            approval_node = WorkflowNode(
                id=f"approval:{task.id}" if task is not None else f"approval:{failure.id}",
                kind="HUMAN_APPROVAL",
                stage="approval",
                title="人工审批源码改动",
                subtitle=("源码改动待人工批准" if task is not None else "等待审批后才应用补丁"),
                status=approval_status,
                entity_type="task" if task is not None else "locator_repair",
                entity_id=task.id if task is not None else (repair.repair_id or failure.id),
                task_id=task.id if task is not None else None,
                parent_id=failure_node.id,
                inputs={"allowed_actions": [str(action) for action in repair.allowed_actions]},
                outputs={
                    "approved": _mapping(approval_step.outputs).get("approved") if approval_step else None,
                    "comment": _mapping(approval_step.outputs).get("comment") if approval_step else None,
                    "goal": task.goal if task is not None else None,
                },
                evidence=[WorkflowEvidenceRef(kind="api", label="任务详情", ref=f"/api/tasks/{task.id}")]
                if task is not None
                else [],
                links={
                    "task": f"/tasks?taskId={task.id}" if task is not None else f"/failures/{failure.id}",
                    "failure": f"/failures/{failure.id}",
                },
            )
            nodes.append(approval_node)
            edges.append(
                WorkflowEdge(
                    id=f"edge:approval:{approval_node.id}",
                    source=analysis_node_id or failure_node.id,
                    target=approval_node.id,
                    kind="PENDING_APPROVAL",
                    label="待批准",
                )
            )

            verification_run_id = None
            if verify_step is not None:
                run_id = _mapping(verify_step.outputs).get("run_id")
                verification_run_id = run_id if isinstance(run_id, str) else None
            if verification_run_id is None:
                verification_run_id = repair.verification_run_id
            verification_node = WorkflowNode(
                id=f"verification:{failure.id}",
                kind="EXACT_VERIFICATION",
                stage="verification",
                title="精确验证",
                subtitle=verification_run_id or "还没有验证运行",
                status=(
                    _mapping(verify_step.outputs).get("status")
                    if verify_step is not None and verify_step.outputs
                    else repair.verification_run_status or repair.state.value
                )
                or "NOT_STARTED",
                entity_type="test_run",
                entity_id=verification_run_id or failure.id,
                task_id=task.id if task is not None else None,
                parent_id=approval_node.id,
                inputs={"failure_id": failure.id, "nodeid": failure.test_nodeid},
                outputs={"verified": repair.verified, "run_id": verification_run_id},
                evidence=[WorkflowEvidenceRef(kind="api", label="验证运行", ref=f"/api/runs/{verification_run_id}")]
                if verification_run_id
                else [],
                links={
                    "run": f"/runs/{verification_run_id}" if verification_run_id else f"/failures/{failure.id}",
                    "api": f"/api/failures/{failure.id}/verification",
                },
            )
            nodes.append(verification_node)
            edges.append(
                WorkflowEdge(
                    id=f"edge:verification:{failure.id}",
                    source=approval_node.id,
                    target=verification_node.id,
                    kind="VERIFIED_BY",
                    label="验证",
                )
            )

        counts = {stage.key: 0 for stage in STAGES}
        for node in nodes:
            counts[node.stage] = counts.get(node.stage, 0) + 1

        return WorkflowCanvas(
            project_id=project_id,
            generated_at=datetime.now(UTC),
            stages=list(STAGES),
            nodes=nodes,
            edges=edges,
            counts=counts,
            discovery_match_count=discovery_match_count,
            discovery_truncated=discovery_truncated,
            truncated=len(run_rows) > MAX_RUNS
            or len([row for row in failure_rows if row.run_id in run_nodes]) >= MAX_FAILURES
            or discovery_truncated
            or len(binding_rows) >= MAX_RECORDER,
        )

    async def _discovery_metrics_async(self, run_id: str, result: dict[str, Any]) -> DiscoveryMetrics:
        """Run-row counts plus the structured evidence index, read from the one analysis."""
        metrics = self._discovery_metrics(result)
        rows = await self.evidence.list_by_run(run_id, limit=2000)
        scenarios = await self.evidence.list_scenarios(run_id)
        analysis = analyze_collection(rows, _sequence(result.get("states")))
        elements = analysis["dom_element"]
        locators = analysis["locator_candidate"]
        requests = analysis["network_request"]
        actions = analysis["user_action"]
        statuses = [scenario.coverage_status for scenario in scenarios]
        suggestions = await self.suggestions.list_by_run(run_id, limit=500)
        reading = suggestion_summary(suggestions)
        if suggestions:
            metrics.intelligence = DiscoveryIntelligenceMetrics(
                suggestions=reading["total"],
                pending_review=reading["pending_review"],
                accepted=reading["accepted"],
                rejected=reading["rejected"],
                linked=reading["linked"],
                created_cases=reading["created_cases"],
                insufficient=reading["by_analysis_status"].get("INSUFFICIENT_EVIDENCE", 0),
                ungrounded_rejected=reading["by_analysis_status"].get("REJECTED", 0),
                failed=reading["by_analysis_status"].get("FAILED", 0),
                degraded=reading["by_analysis_status"].get("DEGRADED", 0),
                jev_graded=reading["jev_graded"],
                jev_fallback=reading["jev_fallback"],
            )
        metrics.evidence = DiscoveryEvidenceMetrics(
            dom_elements=elements["raw"],
            dom_elements_deduped=elements["deduped"],
            page_states=analysis["page_state"]["total"],
            locators=locators["total"],
            locators_ambiguous=locators["ambiguous"],
            requests=requests["deduped"],
            requests_associated=requests["associated"],
            actions=actions["total"],
            state_changes=actions["state_changed"],
            scenarios=len(scenarios),
            covered=statuses.count("COVERED"),
            candidate_gaps=statuses.count("CANDIDATE_GAP"),
            undetermined=statuses.count("UNDETERMINED"),
            captured=bool(rows),
        )
        return metrics

    @staticmethod
    def _discovery_metrics(result: dict[str, Any]) -> DiscoveryMetrics:
        states = _sequence(result.get("states"))
        coverage = _sequence(result.get("coverage"))
        test_case_ids = {
            case_id
            for item in coverage
            for case_id in _sequence(_mapping(item).get("test_case_ids"))
            if isinstance(case_id, str)
        }
        statuses = [_mapping(item).get("coverage_status") for item in coverage]
        return DiscoveryMetrics(
            states=len(states),
            actions=len(_sequence(result.get("actions"))),
            features=len(_sequence(result.get("features"))),
            requirements=len(_sequence(result.get("requirements"))),
            gaps=len(_sequence(result.get("gaps"))),
            covered=statuses.count("COVERED"),
            partial=statuses.count("PARTIAL"),
            not_covered=statuses.count("NOT_COVERED"),
            test_cases=len(test_case_ids),
        )

    @staticmethod
    def _discovery_evidence(row: Any, result: dict[str, Any]) -> list[DiscoveryEvidenceRef]:
        """Only the collections the exploration loop already records."""
        evidence: list[DiscoveryEvidenceRef] = []
        for state in _sequence(result.get("states")):
            state = _mapping(state)
            state_id = str(state.get("state_id") or "")
            if not state_id:
                continue
            page_url = state.get("url")
            captured_at = state.get("observed_at")
            if state.get("evidence_id"):
                evidence.append(
                    DiscoveryEvidenceRef(
                        id=f"{state_id}:page_state",
                        collection="page_state",
                        page_url=page_url,
                        captured_at=captured_at,
                        artifact_ref=str(state.get("evidence_id")),
                        summary={
                            "page_type": state.get("page_type"),
                            "controls": len(_sequence(state.get("controls"))),
                            "landmarks": len(_sequence(state.get("landmarks"))),
                            "depth": state.get("depth"),
                        },
                    )
                )
            if state.get("screenshot_evidence_id"):
                evidence.append(
                    DiscoveryEvidenceRef(
                        id=f"{state_id}:screenshot",
                        collection="screenshot",
                        page_url=page_url,
                        captured_at=captured_at,
                        artifact_ref=str(state.get("screenshot_evidence_id")),
                        summary={"page_type": state.get("page_type")},
                    )
                )
            network = _mapping(state.get("network"))
            if network:
                evidence.append(
                    DiscoveryEvidenceRef(
                        id=f"{state_id}:network",
                        collection="network",
                        page_url=page_url,
                        captured_at=captured_at,
                        summary=_mapping(network),
                    )
                )
            if state.get("console_errors"):
                evidence.append(
                    DiscoveryEvidenceRef(
                        id=f"{state_id}:console",
                        collection="console",
                        page_url=page_url,
                        captured_at=captured_at,
                        summary={"errors": len(_sequence(state.get("console_errors")))},
                    )
                )
        for action in _sequence(result.get("actions"))[:20]:
            action = _mapping(action)
            candidate_id = action.get("candidate_id")
            if not isinstance(candidate_id, str):
                continue
            evidence.append(
                DiscoveryEvidenceRef(
                    id=f"{candidate_id}:action",
                    collection="action",
                    page_url=action.get("target"),
                    captured_at=action.get("started_at"),
                    summary={
                        "action_type": action.get("action_type"),
                        "status": action.get("status"),
                        "from_state_id": action.get("from_state_id"),
                    },
                )
            )
        return evidence
