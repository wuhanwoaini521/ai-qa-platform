"""Project existing execution rows into an agent execution tree.

The tree answers four questions about a task: who executed what, when, through which provider, and
which evidence came out of it. Every node is a stored row; the projection never guesses a fact. A
value the server cannot establish stays ``None`` and its name is listed in ``unknown``.

Nothing here writes or executes: no task is created, no provider is called, no state is replayed.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable

from project_model.execution_trace import (
    ExecutionTrace,
    TraceCounts,
    TraceEdge,
    TraceNode,
    TraceTokenUsage,
)
from project_model.models import utc_now
from qa_core.failure.redactor import SensitiveRedactor

from app.domain.task_records import TaskRecord
from app.repositories.ai_repo import AIRepository
from app.repositories.discovery_suggestion_repo import DiscoverySuggestionRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.test_run_repo import TestRunRepository

MAX_SUMMARY_CHARS = 160
#: Facts no stored row can answer today, so the trace states them instead of filling them.
TRACE_UNKNOWN = ["parent_task_id", "cost", "unit_price"]


def _summary_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return SensitiveRedactor.redact_text(value)[:MAX_SUMMARY_CHARS]
    if isinstance(value, (list, tuple, set)):
        return f"[{len(value)}]"
    if isinstance(value, dict):
        return f"{{{len(value)} fields}}"
    return SensitiveRedactor.redact_text(str(value))[:MAX_SUMMARY_CHARS]


def _type_value(value: object) -> str:
    raw = str(getattr(value, "value", value))
    return raw.rsplit(".", 1)[-1]


def safe_summary(values: dict[str, Any] | None) -> dict[str, str]:
    """Keep scalars and short strings; drop sensitive keys and describe structures by shape."""
    summary: dict[str, str] = {}
    for key, value in (values or {}).items():
        key_text = str(key)
        if SensitiveRedactor.SENSITIVE_KEYS.search(key_text):
            continue
        text = _summary_text(value)
        if text:
            summary[key_text] = text
    return summary


def _duration_ms(started_at, finished_at) -> float | None:
    if started_at is None or finished_at is None:
        return None
    return round((finished_at - started_at).total_seconds() * 1000, 2)


class ExecutionTraceService:
    """Read-only execution tree for one task, or for the recent tasks of one project."""

    def __init__(
        self,
        tasks: TaskRepository,
        invocations: AIRepository,
        runs: TestRunRepository,
        suggestions: DiscoverySuggestionRepository,
    ) -> None:
        self.tasks = tasks
        self.invocations = invocations
        self.runs = runs
        self.suggestions = suggestions

    async def for_task(self, task_id: str, owner_id: str) -> ExecutionTrace | None:
        task = await self.tasks.get(task_id, owner_id)
        if task is None:
            return None
        return await self._build([task], root_task_id=task.id)

    async def for_project(self, project_id: str, owner_id: str, *, limit: int = 6) -> ExecutionTrace:
        tasks = await self.tasks.list(owner_id, project_id=project_id, limit=limit)
        if not tasks:
            return ExecutionTrace(
                project_id=project_id,
                generated_at=utc_now(),
                unknown=[*TRACE_UNKNOWN, "task"],
                root_count=0,
            )
        return await self._build(tasks, project_id=project_id)

    async def _build(
        self,
        task_models: list[TaskRecord],
        *,
        root_task_id: str | None = None,
        project_id: str | None = None,
    ) -> ExecutionTrace:
        task_ids = [task.id for task in task_models]
        details = [await self.tasks.get_detail(task) for task in task_models]
        invocations = await self.invocations.list_by_task_ids(task_ids)
        runs = await self.runs.list_by_task_ids(task_ids)
        suggestions = await self.suggestions.list_by_task_ids(task_ids)

        nodes: list[TraceNode] = []
        edges: list[TraceEdge] = []
        counts = TraceCounts()

        for task, detail in zip(task_models, details):
            task_node_id = f"task:{task.id}"
            nodes.append(
                TraceNode(
                    id=task_node_id,
                    type="task",
                    label=SensitiveRedactor.redact_text(task.goal)[:120],
                    task_id=task.id,
                    started_at=task.started_at or task.created_at,
                    finished_at=task.finished_at,
                    status=task.status,
                    links={"task": f"/runs/tasks?taskId={task.id}"},
                    inputs=safe_summary({"type": task.type, **task.inputs}),
                    outputs=safe_summary({"failure_reason": task.failure_reason}),
                    error_code="TASK_BLOCKED" if task.status in {"BLOCKED", "FAILED"} else None,
                    unknown=["parent_task_id"],
                )
            )
            counts.task += 1

            steps = detail.steps or detail.plan
            step_by_id = {step.id: step for step in steps}
            # A step declares its dependencies by step *key*, not by id.
            step_id_by_key = {step.key: step.id for step in steps}
            for step in steps:
                step_node_id = f"step:{step.id}"
                nodes.append(
                    TraceNode(
                        id=step_node_id,
                        type="step",
                        label=step.name,
                        task_id=task.id,
                        parent_id=task_node_id,
                        started_at=step.started_at,
                        finished_at=step.finished_at,
                        status=step.status,
                        position=step.position,
                        tool=step.tool,
                        evidence_ids=list(step.evidence_ids),
                        inputs=safe_summary(step.inputs),
                        outputs=safe_summary(step.outputs),
                        error_code="STEP_FAILED" if step.error else None,
                        duration_ms=step.duration_ms or _duration_ms(step.started_at, step.finished_at),
                        unknown=["token_usage", "cost"],
                    )
                )
                counts.step += 1
                edges.append(
                    TraceEdge(
                        id=f"{step_node_id}->{task_node_id}", source=step_node_id, target=task_node_id, type="CHILD_OF"
                    )
                )
                for dependency in step.dependencies or []:
                    target_step = dependency if dependency in step_by_id else step_id_by_key.get(dependency)
                    if target_step:
                        edges.append(
                            TraceEdge(
                                id=f"{step_node_id}->dep:{target_step}",
                                source=step_node_id,
                                target=f"step:{target_step}",
                                type="DEPENDS_ON",
                            )
                        )

            for item in detail.evidence:
                node_id = f"evidence:{item.id}"
                parent = f"step:{item.step_id}" if item.step_id in step_by_id else task_node_id
                nodes.append(
                    TraceNode(
                        id=node_id,
                        type="evidence",
                        # The enum stringifies as "EvidenceType.ANALYSIS"; the card shows the value only.
                        label=f"{_type_value(item.type)} · {item.source}"[:120],
                        task_id=task.id,
                        parent_id=parent,
                        started_at=item.created_at,
                        finished_at=item.created_at,
                        status="COMPLETED",
                        evidence_ids=[item.id],
                        outputs=safe_summary({"summary": item.summary, "artifact_id": item.artifact_id}),
                        unknown=["cost"],
                    )
                )
                counts.evidence += 1
                edges.append(TraceEdge(id=f"{node_id}->{parent}", source=node_id, target=parent, type="PRODUCES"))

            for artifact in detail.artifacts:
                node_id = f"artifact:{artifact.id}"
                parent = f"step:{artifact.step_id}" if artifact.step_id in step_by_id else task_node_id
                nodes.append(
                    TraceNode(
                        id=node_id,
                        type="artifact",
                        label=artifact.name[:120],
                        task_id=task.id,
                        parent_id=parent,
                        started_at=artifact.created_at,
                        finished_at=artifact.created_at,
                        status="COMPLETED",
                        outputs=safe_summary({"kind": artifact.kind, "artifact_id": artifact.artifact_id}),
                        unknown=["cost"],
                    )
                )
                counts.artifact += 1
                edges.append(TraceEdge(id=f"{node_id}->{parent}", source=node_id, target=parent, type="PRODUCES"))

            invocation_nodes: dict[str, str] = {}
            for row in invocations:
                if row.task_id != task.id:
                    continue
                node_id = f"invocation:{row.id}"
                invocation_nodes[row.id] = node_id
                parent = f"step:{row.step_id}" if row.step_id in step_by_id else task_node_id
                tokens = None
                unknown = ["cost"]
                if row.token_source == "provider" and row.input_tokens is not None and row.output_tokens is not None:
                    tokens = TraceTokenUsage(
                        input_tokens=row.input_tokens,
                        output_tokens=row.output_tokens,
                        source=row.token_source,
                    )
                else:
                    unknown.append("token_usage")
                if row.step_id is None:
                    unknown.append("step_id")
                started_at = row.started_at
                finished_at = started_at + timedelta(milliseconds=row.duration_ms or 0) if started_at else None
                nodes.append(
                    TraceNode(
                        id=node_id,
                        type="invocation",
                        label=row.task,
                        task_id=task.id,
                        invocation_id=row.id,
                        parent_id=parent,
                        started_at=started_at,
                        finished_at=finished_at,
                        status=row.status,
                        provider=row.provider,
                        model=row.model,
                        token_usage=tokens,
                        error_code=row.error_type,
                        error_message=row.error_type,
                        duration_ms=row.duration_ms or None,
                        fallback_used=row.fallback_used,
                        outputs=safe_summary(
                            {
                                "decision_name": row.decision_name,
                                "decision_choice": row.decision_choice,
                                "decision_confidence": row.decision_confidence,
                                "retry_count": row.retry_count,
                                "fallback_used": row.fallback_used,
                            }
                        ),
                        unknown=unknown,
                    )
                )
                counts.invocation += 1
                edges.append(TraceEdge(id=f"{node_id}->{parent}", source=node_id, target=parent, type="INVOKES"))

            for row in runs:
                if row.task_id != task.id:
                    continue
                node_id = f"run:{row.id}"
                nodes.append(
                    TraceNode(
                        id=node_id,
                        type="run",
                        label=row.id,
                        task_id=task.id,
                        parent_id=task_node_id,
                        started_at=row.created_at,
                        finished_at=row.finished_at,
                        status=row.status,
                        links={"run": f"/runs/{row.id}"},
                        duration_ms=row.duration_ms or None,
                        outputs=safe_summary(
                            {
                                "nodeids": list(row.nodeids or []),
                                "total": row.total,
                                "passed": row.passed,
                                "failed": row.failed,
                                "skipped": row.skipped,
                            }
                        ),
                        unknown=["token_usage", "cost"],
                    )
                )
                counts.run += 1
                edges.append(
                    TraceEdge(id=f"{node_id}->{task_node_id}", source=node_id, target=task_node_id, type="PRODUCES")
                )

            for row in suggestions:
                if row.task_id != task.id:
                    continue
                # The same scenario is re-proposed by every run, so the row id is what is unique here.
                node_id = f"suggestion:{row.id}"
                invoker = invocation_nodes.get(str(row.invocation_id)) if row.invocation_id else None
                parent = invoker or task_node_id
                nodes.append(
                    TraceNode(
                        id=node_id,
                        type="suggestion",
                        label=str((row.payload or {}).get("title") or row.scenario_id)[:120],
                        task_id=task.id,
                        invocation_id=str(row.invocation_id) if row.invocation_id else None,
                        parent_id=parent,
                        started_at=row.created_at,
                        finished_at=row.created_at,
                        status=row.analysis_status,
                        provider=row.provider or None,
                        model=row.model or None,
                        evidence_ids=list(row.evidence_ids or []),
                        outputs=safe_summary(
                            {
                                "review_status": row.review_status,
                                "scenario_id": row.scenario_id,
                                "run_id": row.run_id,
                                "cited_evidence": len(row.evidence_ids or []),
                                "coverage_status": (row.payload or {}).get("coverage_status"),
                                "grade": (row.jev or {}).get("grade"),
                                "jev_status": (row.jev or {}).get("status"),
                                "related_cases": list(row.related_case_ids or []),
                            }
                        ),
                        unknown=["cost"],
                        links={"readings": f"/workspace/{row.project_id}?stage=automation&view=canvas"},
                    )
                )
                counts.suggestion += 1
                edges.append(TraceEdge(id=f"{node_id}->{parent}", source=node_id, target=parent, type="PRODUCES"))

        return ExecutionTrace(
            root_task_id=root_task_id,
            project_id=project_id or (task_models[0].project_id if task_models else None),
            status=task_models[0].status if len(task_models) == 1 else None,
            generated_at=utc_now(),
            nodes=nodes,
            edges=edges,
            counts=counts,
            unknown=list(TRACE_UNKNOWN),
            root_count=len(task_models),
            truncated=len(nodes) >= 400,
        )


def edge_targets(edges: Iterable[TraceEdge]) -> set[str]:
    """Every edge must land on a node that exists; used by the tests and by the UI guard."""
    return {edge.target for edge in edges}
