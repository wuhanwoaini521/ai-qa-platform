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

#: What a discovery artefact was collected from. The first five are projected from the run row;
#: the ``evidence_*`` ones are the structured index added in Round 15.
DiscoveryCollection = Literal[
    "page_state",
    "screenshot",
    "network",
    "console",
    "action",
    "evidence_dom_element",
    "evidence_network_request",
    "evidence_locator_candidate",
    "evidence_user_action",
    "evidence_scenario",
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


class DiscoveryEvidenceMetrics(BaseModel):
    """What the structured evidence index holds for this run, per kind.

    These are the deterministic counts from the evidence analysis, not a second counting pass: the
    canvas reads the same numbers the evidence API reports.
    """

    dom_elements: int = 0
    dom_elements_deduped: int = 0
    page_states: int = 0
    locators: int = 0
    locators_ambiguous: int = 0
    requests: int = 0
    requests_associated: int = 0
    actions: int = 0
    state_changes: int = 0
    scenarios: int = 0
    covered: int = 0
    candidate_gaps: int = 0
    undetermined: int = 0
    captured: bool = False


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
    evidence: DiscoveryEvidenceMetrics | None = None


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
