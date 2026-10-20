"""Read models for the workspace workflow canvas.

The canvas is a projection, not an engine: every node is an existing record and its
``status`` is the domain status verbatim. The server stays the only authority for
task and run state; the client only picks a colour tone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowNodeKind = Literal[
    "DISCOVERY",
    "RECORDER",
    "STUDIO",
    "RUN",
    "FAILURE",
    "FAILURE_ANALYSIS",
    "HUMAN_APPROVAL",
    "EXACT_VERIFICATION",
]

#: What a discovery artefact was collected from. Round 15 adds the collections the
#: exploration loop does not record yet (dom_element, locator_candidate, network_request,
#: user_action, test_scenario, coverage_gap).
DiscoveryCollection = Literal[
    "page_state",
    "screenshot",
    "network",
    "console",
    "action",
]

DiscoveryCollectionMethod = Literal["browser_runtime", "recorder", "manual"]


class WorkflowEvidenceRef(BaseModel):
    """One addressable artefact behind a node: an artifact id, a file path or an API path."""

    kind: str
    label: str
    ref: str | None = None
    url: str | None = None


class DiscoveryEvidenceRef(BaseModel):
    """One captured exploration artefact, addressed per discovery node.

    ``id`` is stable across polls so a later round can attach more collections to the
    same node without renumbering anything.
    """

    id: str
    collection: DiscoveryCollection
    page_url: str | None = None
    captured_at: str | None = None
    collection_method: DiscoveryCollectionMethod = "browser_runtime"
    artifact_ref: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class DiscoveryMetrics(BaseModel):
    """Counts a discovery run already knows; the canvas shows them instead of guessing."""

    states: int = 0
    actions: int = 0
    features: int = 0
    requirements: int = 0
    gaps: int = 0
    covered: int = 0
    partial: int = 0
    not_covered: int = 0
    test_cases: int = 0


class WorkflowNode(BaseModel):
    id: str
    kind: WorkflowNodeKind
    stage: str
    title: str
    subtitle: str | None = None
    status: str
    entity_type: str
    entity_id: str
    task_id: str | None = None
    parent_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[WorkflowEvidenceRef] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    metrics: DiscoveryMetrics | None = None
    evidence_index: list[DiscoveryEvidenceRef] = Field(default_factory=list)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    label: str | None = None


class WorkflowStage(BaseModel):
    key: str
    title: str
    kind: WorkflowNodeKind
    description: str = ""


class WorkflowCanvas(BaseModel):
    project_id: str
    generated_at: datetime
    stages: list[WorkflowStage]
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    counts: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False
