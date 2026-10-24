"""Read models for the agent execution tree.

The tree is a projection of rows that already exist: tasks, steps, AI invocations, task evidence,
artifacts, the runs a task asked for and the suggestions a task produced. Nothing here is an engine
and nothing here writes state.

Facts the server cannot establish are reported as ``None`` plus the field name in ``unknown``. A node
never carries a guessed value: a missing step reference on an invocation is ``UNKNOWN``, an
unreported token count is ``UNKNOWN``, and a cost is only present when a real price table exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TraceNodeType = Literal["task", "step", "invocation", "evidence", "artifact", "run", "suggestion"]

TraceEdgeType = Literal["CHILD_OF", "INVOKES", "PRODUCES", "DEPENDS_ON"]

#: ``unpriced`` is the honest default: the platform has no price table, so it must not invent one.
TracePricing = Literal["unpriced"]


class TraceTokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    #: ``provider`` when the provider reported the numbers, never ``estimated``.
    source: str


class TraceNode(BaseModel):
    id: str
    type: TraceNodeType
    label: str
    task_id: str | None = None
    invocation_id: str | None = None
    parent_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str | None = None
    #: Position inside its task, for steps. ``None`` for rows that have no ordering.
    position: int | None = None
    #: The step's tool name; ``None`` on nodes that are not steps.
    tool: str | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: TraceTokenUsage | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    #: Safe summaries: scalars and short strings only, sensitive keys removed.
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    cost: float | None = None
    pricing: TracePricing = "unpriced"
    #: Field names the server could not establish for this node, e.g. ``["step_id", "token_usage"]``.
    unknown: list[str] = Field(default_factory=list)
    duration_ms: float | None = None
    #: Whether the platform answered from a degraded path (Jev fallback), straight from the row.
    fallback_used: bool | None = None
    #: The invocation's own outcome code, e.g. ``timeout``; ``None`` when the call succeeded.
    error_message: str | None = None
    #: Routes to the existing screens for this row, e.g. ``{"run": "/runs/run_12"}``.
    links: dict[str, str] = Field(default_factory=dict)


class TraceEdge(BaseModel):
    id: str
    source: str
    target: str
    type: TraceEdgeType


class TraceCounts(BaseModel):
    task: int = 0
    step: int = 0
    invocation: int = 0
    evidence: int = 0
    artifact: int = 0
    run: int = 0
    suggestion: int = 0


class ExecutionTrace(BaseModel):
    root_task_id: str | None = None
    project_id: str | None = None
    status: str | None = None
    workflow_execution_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_version_id: str | None = None
    workflow_version: int | None = None
    workflow_checksum: str | None = None
    generated_at: datetime
    nodes: list[TraceNode] = Field(default_factory=list)
    edges: list[TraceEdge] = Field(default_factory=list)
    counts: TraceCounts = Field(default_factory=TraceCounts)
    #: Trace-wide gaps, e.g. ``["parent_task_id", "cost"]``.
    unknown: list[str] = Field(default_factory=list)
    #: How many root tasks were folded into this trace (the project view can hold several).
    root_count: int = 0
    truncated: bool = False
