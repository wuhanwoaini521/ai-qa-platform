"""Authoring side of a QA workflow: drafts, published versions, validation, comparison and compilation.

Nothing here executes or mutates a task. The compile step hands a plan to the existing task runtime,
which stays the only thing that runs steps.
"""

from __future__ import annotations

from typing import Any

from project_model.task_models import TaskStepSpec
from project_model.workflow_definition import (
    CATALOGUE,
    NODE_KINDS,
    WorkflowEdgeSpec,
    WorkflowGraphSpec,
    WorkflowIssue,
    WorkflowNodeSpec,
    catalogue_payload,
    dependencies,
    execution_order,
    validate_graph,
)

from app.persistence.models import WorkflowDefinitionORM, WorkflowDefinitionVersionORM
from app.repositories.task_repo import TaskRepository
from app.repositories.workflow_definition_repo import (
    WorkflowDefinitionRepository,
    WorkflowVersionConflict,
    WorkflowVersionNotFound,
    graph_checksum,
)

DRAFT = "DRAFT"
PUBLISHED = "PUBLISHED"


def issues_payload(issues: list[WorkflowIssue]) -> list[dict[str, Any]]:
    return [issue.model_dump() for issue in issues]


def _graph(raw: dict[str, Any] | None) -> WorkflowGraphSpec:
    try:
        return WorkflowGraphSpec.model_validate(raw or {"nodes": [], "edges": []})
    except Exception:  # a stored graph that no longer parses is reported as empty, never guessed at
        return WorkflowGraphSpec()


def version_payload(row: WorkflowDefinitionVersionORM, *, with_graph: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "version": row.version,
        "state": row.state,
        "checksum": row.checksum,
        "issues": row.issues or [],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "published_by": row.published_by,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "node_count": len((row.graph or {}).get("nodes") or []),
        "edge_count": len((row.graph or {}).get("edges") or []),
    }
    if with_graph:
        payload["graph"] = row.graph or {"nodes": [], "edges": []}
    return payload


def compare_graphs(base: WorkflowGraphSpec, head: WorkflowGraphSpec) -> dict[str, Any]:
    """Deterministic graph diff: what a reviewer needs before publishing."""
    base_nodes = {node.key: node for node in base.nodes}
    head_nodes = {node.key: node for node in head.nodes}
    added = sorted(set(head_nodes) - set(base_nodes))
    removed = sorted(set(base_nodes) - set(head_nodes))
    changed: list[dict[str, Any]] = []
    for key in sorted(set(base_nodes) & set(head_nodes)):
        before, after = base_nodes[key], head_nodes[key]
        fields = [
            name
            for name, left, right in (
                ("kind", before.kind, after.kind),
                ("title", before.title, after.title),
                ("inputs", before.inputs, after.inputs),
            )
            if left != right
        ]
        if fields:
            changed.append({"key": key, "fields": fields, "before": before.model_dump(), "after": after.model_dump()})
    base_edges = {(edge.source, edge.target) for edge in base.edges}
    head_edges = {(edge.source, edge.target) for edge in head.edges}
    return {
        "nodes": {
            "added": [head_nodes[key].model_dump() for key in added],
            "removed": [base_nodes[key].model_dump() for key in removed],
            "changed": changed,
        },
        "edges": {
            "added": [{"source": source, "target": target} for source, target in sorted(head_edges - base_edges)],
            "removed": [{"source": source, "target": target} for source, target in sorted(base_edges - head_edges)],
        },
        "identical": not added and not removed and not changed and base_edges == head_edges,
    }


class WorkflowNameTaken(ValueError):
    """Two definitions in one project cannot share a name."""


class WorkflowDefinitionService:
    def __init__(self, definitions: WorkflowDefinitionRepository, tasks: TaskRepository | None = None) -> None:
        self.definitions = definitions
        self.tasks = tasks

    def catalogue(self) -> list[dict[str, Any]]:
        return catalogue_payload()

    async def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self.definitions.list_definitions(project_id)
        return [await self._summary(row) for row in rows]

    async def _summary(self, row: WorkflowDefinitionORM) -> dict[str, Any]:
        draft = await self.definitions.draft(row.id)
        return {
            "id": row.id,
            "project_id": row.project_id,
            "name": row.name,
            "description": row.description,
            "published_version": row.published_version,
            "draft_version": row.draft_version,
            "draft_node_count": len(((draft.graph if draft else {}) or {}).get("nodes") or []),
            "draft_issues": (draft.issues if draft else []) or [],
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def detail(self, definition: WorkflowDefinitionORM) -> dict[str, Any]:
        draft = await self.definitions.draft(definition.id)
        versions = await self.definitions.versions(definition.id)
        published = None
        if definition.published_version:
            published = await self.definitions.get_version(definition.id, definition.published_version)
        return {
            **(await self._summary(definition)),
            "draft": {
                "version": draft.version if draft else None,
                "checksum": draft.checksum if draft else None,
                "graph": (draft.graph if draft else {"nodes": [], "edges": []}),
                "issues": (draft.issues if draft else []) or [],
            },
            "published": version_payload(published, with_graph=True) if published else None,
            "versions": [version_payload(row) for row in versions],
            "catalogue": self.catalogue(),
        }

    async def create(self, project_id: str, name: str, description: str, actor_id: str | None) -> WorkflowDefinitionORM:
        if any(existing.name == name for existing in await self.definitions.list_definitions(project_id)):
            raise WorkflowNameTaken(f"A workflow named '{name}' already exists in this project.")
        definition, _ = await self.definitions.create(project_id, name, description, actor_id)
        return definition

    async def save(
        self,
        definition: WorkflowDefinitionORM,
        graph: dict[str, Any],
        actor_id: str | None,
        base_checksum: str | None = None,
    ) -> dict[str, Any]:
        """A draft may be saved while invalid — the issues travel with it so the editor can show them."""
        parsed = _graph(graph)
        issues = validate_graph(parsed)
        draft = await self.definitions.save_draft(
            definition,
            parsed.model_dump(exclude_none=True),
            issues_payload(issues),
            actor_id,
            base_checksum=base_checksum,
        )
        return {"draft": version_payload(draft, with_graph=True), "issues": issues_payload(issues)}

    async def validate(self, graph: dict[str, Any]) -> list[dict[str, Any]]:
        return issues_payload(validate_graph(_graph(graph)))

    async def publish(self, definition: WorkflowDefinitionORM, actor_id: str | None) -> dict[str, Any]:
        draft = await self.definitions.draft(definition.id)
        if draft is None:
            raise WorkflowVersionNotFound("This definition has no draft to publish.")
        issues = validate_graph(_graph(draft.graph))
        if issues:
            raise WorkflowVersionConflict(
                "A workflow with validation issues cannot be published: " + "; ".join(issue.message for issue in issues)
            )
        published = await self.definitions.publish(definition, [], actor_id)
        return {
            "published": version_payload(published, with_graph=True),
            "draft_version": definition.draft_version,
        }

    async def restore(self, definition: WorkflowDefinitionORM, version: int, actor_id: str | None) -> dict[str, Any]:
        draft = await self.definitions.restore_as_draft(definition, version, actor_id)
        return {
            "draft": version_payload(draft, with_graph=True),
            "issues": issues_payload(validate_graph(_graph(draft.graph))),
        }

    async def compare(self, definition: WorkflowDefinitionORM, base: int, head: int) -> dict[str, Any]:
        base_row = await self.definitions.get_version(definition.id, base)
        head_row = await self.definitions.get_version(definition.id, head)
        if base_row is None or head_row is None:
            raise WorkflowVersionNotFound("One of the compared versions does not exist.")
        return {
            "definition_id": definition.id,
            "base": version_payload(base_row),
            "head": version_payload(head_row),
            "diff": compare_graphs(_graph(base_row.graph), _graph(head_row.graph)),
        }

    async def published_version(
        self, definition: WorkflowDefinitionORM, version: int | None = None
    ) -> WorkflowDefinitionVersionORM:
        """The exact row an execution binds to; only published versions are runnable."""
        wanted = version if version is not None else definition.published_version
        if not wanted:
            raise WorkflowVersionNotFound("This workflow has not been published yet.")
        row = await self.definitions.get_version(definition.id, wanted)
        if row is None or row.state != PUBLISHED:
            raise WorkflowVersionNotFound(f"Version {wanted} is not a published version.")
        return row

    async def compile_plan(
        self, definition: WorkflowDefinitionORM, version: int | None = None
    ) -> tuple[list[TaskStepSpec], WorkflowDefinitionVersionORM]:
        """Turn a published graph into runtime steps; dependency keys become step dependencies."""
        row = await self.published_version(definition, version)
        graph = _graph(row.graph)
        issues = validate_graph(graph)
        if issues:
            raise WorkflowVersionConflict(
                "This published version no longer validates: " + "; ".join(issue.message for issue in issues)
            )
        waits = dependencies(graph)
        nodes = {node.key: node for node in graph.nodes}
        steps: list[TaskStepSpec] = []
        for key in execution_order(graph):
            node = nodes[key]
            spec = NODE_KINDS[node.kind]
            steps.append(
                TaskStepSpec(
                    key=node.key,
                    name=(node.title or spec.title)[:200],
                    tool=node.kind,
                    depends_on=waits[key],
                    inputs=_compile_inputs(node.inputs),
                )
            )
        return steps, row

    async def execution_diff(
        self,
        definition: WorkflowDefinitionORM,
        version: int | None,
        task_id: str,
    ) -> dict[str, Any]:
        """Compare a definition against what a task actually ran: read-only, matched by node kind.

        Nothing here is inferred. A node the task never reached is reported as not executed, and a step
        whose tool no node declares is reported as undeclared; inputs and dependency edges are not compared.
        """
        if self.tasks is None:
            raise WorkflowVersionNotFound("This deployment cannot read task rows.")
        task = await self.tasks.get_by_id(task_id)
        if task is None or task.project_id != definition.project_id:
            raise WorkflowVersionNotFound(f"Task {task_id} does not belong to this project.")
        row = (
            await self.definitions.get_version(definition.id, version)
            if version is not None
            else (await self.definitions.draft(definition.id))
        )
        if row is None:
            raise WorkflowVersionNotFound(f"Version {version} does not exist on this definition.")
        graph = _graph(row.graph)
        steps = await self.tasks.get_steps(task_id)

        by_kind: dict[str, list[Any]] = {}
        for step in steps:
            by_kind.setdefault(step.tool, []).append(step)

        matched: list[dict[str, Any]] = []
        not_executed: list[dict[str, Any]] = []
        consumed: set[str] = set()
        for node in graph.nodes:
            candidates = [step for step in by_kind.get(node.kind, []) if step.id not in consumed]
            if not candidates:
                not_executed.append(
                    {
                        "key": node.key,
                        "kind": node.kind,
                        "reason": "no_step_of_this_kind_ran",
                    }
                )
                continue
            step = candidates[0]
            consumed.add(step.id)
            matched.append(
                {
                    "key": node.key,
                    "kind": node.kind,
                    "step_key": step.key,
                    "step_id": step.id,
                    "status": str(step.status),
                    "duration_ms": step.duration_ms,
                    "error": step.error,
                }
            )

        declared = {node.kind for node in graph.nodes}
        undeclared: list[dict[str, Any]] = []
        for step in steps:
            if step.id in consumed:
                continue
            undeclared.append(
                {
                    "step_key": step.key,
                    "step_id": step.id,
                    "tool": step.tool,
                    "status": str(step.status),
                    "reason": (
                        "the_definition_declares_this_kind_but_the_task_ran_it_more_often"
                        if step.tool in declared
                        else "the_definition_declares_no_node_of_this_kind"
                    ),
                }
            )

        return {
            "definition_id": definition.id,
            "version": row.version,
            "state": row.state,
            "checksum": row.checksum,
            "task_id": task.id,
            "task_type": str(task.type),
            "task_status": str(task.status),
            "totals": {
                "definition_nodes": len(graph.nodes),
                "ran_steps": len(steps),
                "matched": len(matched),
                "not_executed": len(not_executed),
                "undeclared": len(undeclared),
            },
            "matched": matched,
            "not_executed": not_executed,
            "undeclared": undeclared,
            "unknown": [
                "step_inputs_are_not_compared",
                "step_dependencies_are_not_compared",
                "a_repeated_kind_is_matched_in_step_order",
            ],
        }


def _compile_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """``{"$input": name}`` means "bind from the run inputs", so the step leaves the key out."""
    compiled: dict[str, Any] = {}
    for name, value in inputs.items():
        if isinstance(value, dict) and set(value) == {"$input"}:
            continue
        compiled[name] = value
    return compiled


def empty_graph() -> dict[str, Any]:
    return {"nodes": [], "edges": []}


__all__ = [
    "CATALOGUE",
    "DRAFT",
    "PUBLISHED",
    "WorkflowDefinitionService",
    "WorkflowEdgeSpec",
    "WorkflowGraphSpec",
    "WorkflowNodeSpec",
    "compare_graphs",
    "empty_graph",
    "graph_checksum",
    "issues_payload",
    "version_payload",
]
