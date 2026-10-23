"""Versioned workflow definitions and the catalogue of node kinds they may use.

A definition is an authored graph. Only kinds listed in ``CATALOGUE`` are accepted, and every kind
is the name of a tool that the task runtime already registers — an author picks a step, never code.
Validation is deterministic and happens on the server: the editor shows the same issues the runtime
would refuse to execute.
"""

from __future__ import annotations

import heapq
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

NodeRisk = Literal["READ", "EXECUTE", "PROPOSE", "WRITE", "APPROVAL"]
ExecutionClass = Literal[
    "AUTO_READ_ONLY",
    "AUTO_SANDBOXED",
    "DRAFT_ONLY",
    "HUMAN_APPROVAL_REQUIRED",
    "FORBIDDEN",
    "BLOCKED",
]
InputType = Literal["string", "integer", "boolean", "list"]

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,59}$")
MAX_NODES = 30
MAX_INPUT_CHARS = 2000


class InputSpec(BaseModel):
    kind: InputType
    required: bool = False
    description: str = ""


class NodeKindSpec(BaseModel):
    key: str
    title: str
    risk: NodeRisk
    summary: str
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    outputs: str = ""
    output_types: dict[str, InputType] = Field(default_factory=dict)

    @property
    def writes(self) -> bool:
        return self.risk == "WRITE"


def _input(kind: InputType, description: str, required: bool = True) -> InputSpec:
    return InputSpec(kind=kind, required=required, description=description)


CATALOGUE: tuple[NodeKindSpec, ...] = (
    NodeKindSpec(
        key="requirement.analyze",
        title="Analyze requirement",
        risk="READ",
        summary="Read one requirement and record its analysis as evidence.",
        inputs={"requirement_id": _input("string", "Requirement id to analyze.")},
        outputs="analysis summary",
    ),
    NodeKindSpec(
        key="browser.inspect",
        title="Inspect page",
        risk="READ",
        summary="Open a URL and record what the page looks like.",
        inputs={"url": _input("string", "Page to inspect.")},
        outputs="observed controls",
    ),
    NodeKindSpec(
        key="browser.act",
        title="Observe page action",
        risk="READ",
        summary="Perform one safe action that was observed on the page.",
        inputs={"url": _input("string", "Page the action runs on.")},
        outputs="action result",
    ),
    NodeKindSpec(
        key="decision.select_candidate",
        title="Select browser candidate",
        risk="READ",
        summary="Pick one safe candidate to act on, using the model.",
        inputs={"url": _input("string", "Page the decision applies to.")},
        outputs="selected candidate",
    ),
    NodeKindSpec(
        key="discovery.run",
        title="Explore product",
        risk="EXECUTE",
        summary="Run one bounded exploration of a discovery run and persist its evidence.",
        inputs={"discovery_run_id": _input("string", "Quality Discovery run to explore.")},
        outputs="states, actions, evidence",
    ),
    NodeKindSpec(
        key="discovery.collect_gaps",
        title="Collect uncovered scenarios",
        risk="READ",
        summary="Collect the scenarios whose coverage is still unsettled.",
        inputs={"discovery_run_id": _input("string", "Quality Discovery run to read.")},
        outputs="unsettled scenarios",
    ),
    NodeKindSpec(
        key="discovery.analyze_gaps",
        title="Ask the model about gaps",
        risk="READ",
        summary="Ask the provider to read each unsettled scenario and cite its evidence.",
        inputs={"discovery_run_id": _input("string", "Quality Discovery run to read.")},
        outputs="readings with evidence ids",
    ),
    NodeKindSpec(
        key="discovery.grade_gaps",
        title="Grade evidence sufficiency",
        risk="READ",
        summary="Grade whether the cited evidence can support a test case.",
        inputs={"discovery_run_id": _input("string", "Quality Discovery run to read.")},
        outputs="grading with its source",
    ),
    NodeKindSpec(
        key="discovery.summarize_gaps",
        title="Summarize decisions needed",
        risk="READ",
        summary="Summarize what still needs a human decision.",
        inputs={"discovery_run_id": _input("string", "Quality Discovery run to read.")},
        outputs="summary",
    ),
    NodeKindSpec(
        key="failure.collect",
        title="Collect failure evidence",
        risk="READ",
        summary="Load one failure record with its run and browser evidence.",
        inputs={"failure_id": _input("string", "Failure record to collect.")},
        outputs="failure, run and evidence snapshot",
        output_types={"id": "string"},
    ),
    NodeKindSpec(
        key="failure.classify",
        title="Classify failure",
        risk="READ",
        summary="Classify the failure from the collected evidence.",
        inputs={"failure_id": _input("string", "Failure record to classify.")},
        outputs="classification",
        output_types={"classification": "string", "root_cause": "string", "failing_locator": "string"},
    ),
    NodeKindSpec(
        key="source.inspect_failure",
        title="Inspect failing source",
        risk="READ",
        summary="Read the source location the failure points at.",
        inputs={"failure_id": _input("string", "Failure record to inspect.")},
        outputs="source excerpt",
    ),
    NodeKindSpec(
        key="failure.diagnose",
        title="Diagnose cause",
        risk="READ",
        summary="Diagnose the cause with the model, citing collected evidence.",
        inputs={"failure_id": _input("string", "Failure record to diagnose.")},
        outputs="diagnosis",
    ),
    NodeKindSpec(
        key="failure.prepare_repair",
        title="Prepare repair proposal",
        risk="PROPOSE",
        summary="Prepare a bounded source change proposal; nothing is written.",
        inputs={"failure_id": _input("string", "Failure record being repaired.")},
        outputs="patch proposal",
    ),
    NodeKindSpec(
        key="tests.generate",
        title="Generate test code",
        risk="PROPOSE",
        summary="Generate candidate test code from the goal and evidence; nothing is written.",
        inputs={},
        outputs="generated source",
    ),
    NodeKindSpec(
        key="source.validate_generated",
        title="Validate generated source",
        risk="READ",
        summary="Check generated source before anyone approves writing it.",
        inputs={},
        outputs="validation",
    ),
    NodeKindSpec(
        key="task.request_approval",
        title="Request human approval",
        risk="APPROVAL",
        summary="Stop and wait for a human to approve what the following node will write.",
        inputs={},
        outputs="approval decision",
    ),
    NodeKindSpec(
        key="source.write_generated",
        title="Write approved test to workspace",
        risk="WRITE",
        summary="Write the approved generated test into the workspace.",
        inputs={},
        outputs="written file",
    ),
    NodeKindSpec(
        key="source.apply_repair",
        title="Apply approved repair",
        risk="WRITE",
        summary="Apply the approved patch to the workspace source.",
        inputs={},
        outputs="written file",
    ),
    NodeKindSpec(
        key="source.validate_workspace",
        title="Validate changed source",
        risk="READ",
        summary="Validate the workspace after a change.",
        inputs={},
        outputs="validation",
    ),
    NodeKindSpec(
        key="tests.resolve",
        title="Resolve regression scope",
        risk="READ",
        summary="Resolve which test cases the requested scope covers.",
        inputs={"requirement_id": _input("string", "Requirement to resolve.", required=False)},
        outputs="nodeids",
    ),
    NodeKindSpec(
        key="tests.run_target",
        title="Run target test",
        risk="EXECUTE",
        summary="Execute the target test file or nodeid.",
        inputs={
            "nodeids": _input("list", "Nodeids to run.", required=False),
            "failure_id": _input("string", "Failure whose test should run.", required=False),
        },
        outputs="run result",
    ),
    NodeKindSpec(
        key="tests.run_regression",
        title="Run regression scope",
        risk="EXECUTE",
        summary="Execute the requested regression nodeids.",
        inputs={"nodeids": _input("list", "Nodeids to run.")},
        outputs="run result",
    ),
    NodeKindSpec(
        key="tests.verify",
        title="Verify result",
        risk="READ",
        summary="Verify that the recorded run actually passed.",
        inputs={},
        outputs="verification",
    ),
    NodeKindSpec(
        key="tests.compare",
        title="Compare before and after",
        risk="READ",
        summary="Compare a before run with an after run.",
        inputs={},
        outputs="comparison",
    ),
)

NODE_KINDS: dict[str, NodeKindSpec] = {spec.key: spec for spec in CATALOGUE}
WRITE_KINDS = frozenset(spec.key for spec in CATALOGUE if spec.writes)
APPROVAL_KIND = "task.request_approval"

# Effect classifications from the handler audit. Only the two deterministic failure readers are
# enabled for Workflow launch; the other read-only handlers remain out until their boundaries are tested.
WORKFLOW_EXECUTION_POLICY: dict[str, dict[str, Any]] = {
    "requirement.analyze": {
        "classification": "DRAFT_ONLY",
        "enabled": False,
        "reason": "Calls a provider and stores analysis metadata.",
    },
    "browser.inspect": {
        "classification": "BLOCKED",
        "enabled": False,
        "reason": "Browser navigation has no Workflow-specific network boundary.",
    },
    "browser.act": {
        "classification": "BLOCKED",
        "enabled": False,
        "reason": "Browser interaction may mutate a remote site.",
    },
    "decision.select_candidate": {
        "classification": "BLOCKED",
        "enabled": False,
        "reason": "Browser decision handling is not bounded for Workflow execution.",
    },
    "discovery.run": {
        "classification": "BLOCKED",
        "enabled": False,
        "reason": "Runs a long-lived browser exploration with remote effects.",
    },
    "discovery.collect_gaps": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "discovery.analyze_gaps": {
        "classification": "DRAFT_ONLY",
        "enabled": False,
        "reason": "Calls a provider and persists proposal metadata.",
    },
    "discovery.grade_gaps": {
        "classification": "DRAFT_ONLY",
        "enabled": False,
        "reason": "Calls a provider and persists proposal metadata.",
    },
    "discovery.summarize_gaps": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "failure.collect": {
        "classification": "AUTO_READ_ONLY",
        "enabled": True,
        "reason": "Deterministically reads project-scoped failure evidence.",
    },
    "failure.classify": {
        "classification": "AUTO_READ_ONLY",
        "enabled": True,
        "reason": "Uses the deterministic local FailureClassifier.",
    },
    "source.inspect_failure": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "failure.diagnose": {
        "classification": "BLOCKED",
        "enabled": False,
        "reason": "Sends failure evidence to a configured provider.",
    },
    "failure.prepare_repair": {
        "classification": "DRAFT_ONLY",
        "enabled": False,
        "reason": "Creates a repair proposal and may call a provider.",
    },
    "tests.generate": {
        "classification": "DRAFT_ONLY",
        "enabled": False,
        "reason": "Creates generated source proposals and may call a provider.",
    },
    "source.validate_generated": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "task.request_approval": {
        "classification": "HUMAN_APPROVAL_REQUIRED",
        "enabled": False,
        "reason": "Approval is not bound to Workflow version, execution, node and proposal hash.",
    },
    "source.write_generated": {
        "classification": "HUMAN_APPROVAL_REQUIRED",
        "enabled": False,
        "reason": "Workflow-bound approval and proposal revalidation are not implemented.",
    },
    "source.apply_repair": {
        "classification": "HUMAN_APPROVAL_REQUIRED",
        "enabled": False,
        "reason": "Workflow-bound approval and proposal revalidation are not implemented.",
    },
    "source.validate_workspace": {
        "classification": "FORBIDDEN",
        "enabled": False,
        "reason": "Runs project-controlled pytest code without an OS or container sandbox.",
    },
    "tests.resolve": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "tests.run_target": {
        "classification": "FORBIDDEN",
        "enabled": False,
        "reason": "Runs project-controlled pytest code without an OS or container sandbox.",
    },
    "tests.run_regression": {
        "classification": "FORBIDDEN",
        "enabled": False,
        "reason": "Runs project-controlled pytest code without an OS or container sandbox.",
    },
    "tests.verify": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
    "tests.compare": {
        "classification": "AUTO_READ_ONLY",
        "enabled": False,
        "reason": "Read-only handler is outside the initial verified subset.",
    },
}


class WorkflowNodeSpec(BaseModel):
    key: str
    kind: str
    title: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None


class WorkflowEdgeSpec(BaseModel):
    source: str
    target: str


class WorkflowGraphSpec(BaseModel):
    nodes: list[WorkflowNodeSpec] = Field(default_factory=list)
    edges: list[WorkflowEdgeSpec] = Field(default_factory=list)


class WorkflowIssue(BaseModel):
    code: str
    message: str
    node_key: str | None = None


def dependencies(graph: WorkflowGraphSpec) -> dict[str, list[str]]:
    """Map every node key to the keys it waits for."""
    waits: dict[str, list[str]] = {node.key: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.target in waits:
            waits[edge.target].append(edge.source)
    return waits


def execution_order(graph: WorkflowGraphSpec) -> list[str]:
    """Topological order over edges; node keys break ties. Cycles are reported by validate."""
    waits = dependencies(graph)
    ready = [key for key, parents in waits.items() if not parents]
    heapq.heapify(ready)
    order: list[str] = []
    remaining = {key: set(parents) for key, parents in waits.items()}
    while ready:
        key = heapq.heappop(ready)
        order.append(key)
        for other, parents in remaining.items():
            if key in parents:
                parents.discard(key)
                if not parents and other not in order and other not in ready:
                    heapq.heappush(ready, other)
    return order


def _matches_type(value: Any, kind: InputType) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, list) and all(isinstance(item, (str, int)) for item in value)


def _is_reference(value: Any) -> bool:
    return isinstance(value, dict) and len(value) == 1 and ("$input" in value or "$output" in value)


def validate_graph(graph: WorkflowGraphSpec) -> list[WorkflowIssue]:
    """Deterministic gate: the same issues the runtime would refuse to execute on."""
    issues: list[WorkflowIssue] = []
    if not graph.nodes:
        return [WorkflowIssue(code="EMPTY_GRAPH", message="A workflow needs at least one node.")]
    if len(graph.nodes) > MAX_NODES:
        issues.append(
            WorkflowIssue(code="TOO_MANY_NODES", message=f"A workflow may declare at most {MAX_NODES} nodes.")
        )
    seen: set[str] = set()
    for node in graph.nodes:
        if not KEY_PATTERN.match(node.key):
            issues.append(
                WorkflowIssue(
                    code="INVALID_KEY",
                    message=f"Node key '{node.key}' must be lower_snake_case (max 60 characters).",
                    node_key=node.key,
                )
            )
        if node.key in seen:
            issues.append(
                WorkflowIssue(code="DUPLICATE_KEY", message=f"Node key '{node.key}' is used twice.", node_key=node.key)
            )
        seen.add(node.key)
        spec = NODE_KINDS.get(node.kind)
        if spec is None:
            issues.append(
                WorkflowIssue(
                    code="UNKNOWN_KIND",
                    message=f"Node '{node.key}' uses unknown kind '{node.kind}'.",
                    node_key=node.key,
                )
            )
            continue
        for name, declared in spec.inputs.items():
            value = node.inputs.get(name)
            if value in (None, "", []):
                if declared.required:
                    issues.append(
                        WorkflowIssue(
                            code="MISSING_INPUT",
                            message=f"Node '{node.key}' needs '{name}': {declared.description}",
                            node_key=node.key,
                        )
                    )
                continue
            if _is_reference(value):
                continue
            if not _matches_type(value, declared.kind):
                issues.append(
                    WorkflowIssue(
                        code="INVALID_INPUT",
                        message=f"Node '{node.key}' expects '{name}' to be {declared.kind}.",
                        node_key=node.key,
                    )
                )
        for name, value in node.inputs.items():
            if name not in spec.inputs:
                issues.append(
                    WorkflowIssue(
                        code="UNKNOWN_INPUT",
                        message=f"Node '{node.key}' does not accept input '{name}'.",
                        node_key=node.key,
                    )
                )
            elif isinstance(value, str) and len(value) > MAX_INPUT_CHARS:
                issues.append(
                    WorkflowIssue(
                        code="INPUT_TOO_LONG",
                        message=f"Node '{node.key}' input '{name}' exceeds {MAX_INPUT_CHARS} characters.",
                        node_key=node.key,
                    )
                )
    keys = {node.key for node in graph.nodes}
    for edge in graph.edges:
        if edge.source not in keys or edge.target not in keys:
            issues.append(
                WorkflowIssue(
                    code="UNKNOWN_EDGE_NODE",
                    message=f"Edge {edge.source} → {edge.target} refers to a node that does not exist.",
                )
            )
        if edge.source == edge.target:
            issues.append(
                WorkflowIssue(
                    code="SELF_EDGE", message=f"Node '{edge.source}' cannot depend on itself.", node_key=edge.target
                )
            )
    waits = dependencies(graph)
    if not issues:
        ordered = execution_order(graph)
        if len(ordered) != len(keys):
            stalled = sorted(keys - set(ordered))
            issues.append(
                WorkflowIssue(
                    code="CYCLE",
                    message=f"These nodes form a cycle and can never run: {', '.join(stalled)}.",
                    node_key=stalled[0],
                )
            )
    ancestry: dict[str, set[str]] = {}
    for key in keys:
        seen_nodes: set[str] = set()
        stack = list(waits.get(key, []))
        while stack:
            parent = stack.pop()
            if parent in seen_nodes:
                continue
            seen_nodes.add(parent)
            stack.extend(waits.get(parent, []))
        ancestry[key] = seen_nodes
    for node in graph.nodes:
        if node.kind not in WRITE_KINDS:
            continue
        ancestors = ancestry.get(node.key, set())
        if not any(graph_by_key(ancestors, graph).get(key, "") == APPROVAL_KIND for key in ancestors):
            issues.append(
                WorkflowIssue(
                    code="WRITE_WITHOUT_APPROVAL",
                    message=(
                        f"Node '{node.key}' writes to the workspace, so a 'Request human approval' node must run "
                        "before it."
                    ),
                    node_key=node.key,
                )
            )
    if any(node.kind == APPROVAL_KIND for node in graph.nodes) and not any(
        node.kind in WRITE_KINDS for node in graph.nodes
    ):
        issues.append(
            WorkflowIssue(
                code="APPROVAL_WITHOUT_WRITE",
                message="This workflow asks for approval but never writes anything.",
                node_key=next(node.key for node in graph.nodes if node.kind == APPROVAL_KIND),
            )
        )
    return issues


def graph_by_key(keys: set[str], graph: WorkflowGraphSpec) -> dict[str, str]:
    """Kind of each requested node key."""
    kinds = {node.key: node.kind for node in graph.nodes}
    return {key: kinds[key] for key in keys if key in kinds}


def validate_execution_graph(graph: WorkflowGraphSpec, inputs: dict[str, Any]) -> list[WorkflowIssue]:
    """Fail closed before a published graph is submitted to Task Runtime."""
    issues = validate_graph(graph)
    if issues:
        return issues

    keys = {node.key for node in graph.nodes}
    waits = dependencies(graph)
    ancestry: dict[str, set[str]] = {}
    for key in keys:
        ancestors: set[str] = set()
        stack = list(waits.get(key, []))
        while stack:
            parent = stack.pop()
            if parent in ancestors:
                continue
            ancestors.add(parent)
            stack.extend(waits.get(parent, []))
        ancestry[key] = ancestors

    for node in graph.nodes:
        policy = WORKFLOW_EXECUTION_POLICY.get(node.kind)
        if policy is None:
            issues.append(
                WorkflowIssue(
                    code="UNKNOWN_KIND", message=f"Node '{node.key}' has no execution policy.", node_key=node.key
                )
            )
        elif not policy["enabled"]:
            issues.append(
                WorkflowIssue(
                    code="NODE_EXECUTION_BLOCKED",
                    message=f"Node '{node.key}' ({node.kind}) is {policy['classification']}: {policy['reason']}",
                    node_key=node.key,
                )
            )

    collectors = [node for node in graph.nodes if node.kind == "failure.collect"]
    classifiers = [node for node in graph.nodes if node.kind == "failure.classify"]
    if len(collectors) != 1 or len(graph.nodes) not in {1, 2} or len(classifiers) != len(graph.nodes) - 1:
        issues.append(
            WorkflowIssue(
                code="UNSUPPORTED_EXECUTION_SHAPE",
                message="The verified Workflow subset is one failure.collect node, optionally followed by one failure.classify node.",
            )
        )
    if collectors:
        collector = collectors[0]
        if set(collector.inputs) != {"failure_id"}:
            issues.append(
                WorkflowIssue(
                    code="INVALID_EXECUTION_BINDING",
                    message="failure.collect may only bind the launch input '$input.failure_id'.",
                    node_key=collector.key,
                )
            )
        if collector.inputs.get("failure_id") != {"$input": "failure_id"}:
            issues.append(
                WorkflowIssue(
                    code="INVALID_EXECUTION_BINDING",
                    message="failure.collect.failure_id must bind to the launch input '$input.failure_id'.",
                    node_key=collector.key,
                )
            )
    if len(classifiers) == 1 and len(collectors) == 1:
        classifier = classifiers[0]
        collector = collectors[0]
        expected = {"$output": f"{collector.key}.id"}
        if set(classifier.inputs) != {"failure_id"}:
            issues.append(
                WorkflowIssue(
                    code="INVALID_EXECUTION_BINDING",
                    message="failure.classify may only consume the collected failure id.",
                    node_key=classifier.key,
                )
            )
        if classifier.inputs.get("failure_id") != expected or collector.key not in ancestry.get(classifier.key, set()):
            issues.append(
                WorkflowIssue(
                    code="INVALID_EXECUTION_BINDING",
                    message=f"failure.classify.failure_id must bind to '{collector.key}.id' and depend on that collector.",
                    node_key=classifier.key,
                )
            )

    used_inputs: dict[str, InputType] = {}
    for node in graph.nodes:
        spec = NODE_KINDS.get(node.kind)
        if spec is None:
            continue
        for name, value in node.inputs.items():
            if name not in spec.inputs:
                continue
            if isinstance(value, dict) and ("$input" in value or "$output" in value):
                if len(value) != 1:
                    issues.append(
                        WorkflowIssue(
                            code="MALFORMED_REFERENCE",
                            message=f"Node '{node.key}' input '{name}' has a malformed reference.",
                            node_key=node.key,
                        )
                    )
                    continue
                if "$input" in value:
                    input_name = value["$input"]
                    declared = spec.inputs.get(name)
                    if not isinstance(input_name, str) or not input_name or declared is None:
                        issues.append(
                            WorkflowIssue(
                                code="MALFORMED_REFERENCE",
                                message=f"Node '{node.key}' input '{name}' has an invalid launch input reference.",
                                node_key=node.key,
                            )
                        )
                        continue
                    previous = used_inputs.get(input_name)
                    if previous is not None and previous != declared.kind:
                        issues.append(
                            WorkflowIssue(
                                code="INPUT_TYPE_CONFLICT",
                                message=f"Launch input '{input_name}' is used with incompatible types.",
                                node_key=node.key,
                            )
                        )
                    used_inputs[input_name] = declared.kind
                else:
                    reference = value["$output"]
                    if not isinstance(reference, str) or "." not in reference:
                        issues.append(
                            WorkflowIssue(
                                code="MALFORMED_REFERENCE",
                                message=f"Node '{node.key}' input '{name}' has an invalid output reference.",
                                node_key=node.key,
                            )
                        )
                        continue
                    source_key, path = reference.split(".", 1)
                    source = next((item for item in graph.nodes if item.key == source_key), None)
                    source_spec = NODE_KINDS.get(source.kind) if source else None
                    output_type = source_spec.output_types.get(path) if source_spec else None
                    declared = spec.inputs.get(name)
                    if source is None or source_key not in ancestry.get(node.key, set()) or output_type is None:
                        issues.append(
                            WorkflowIssue(
                                code="INVALID_OUTPUT_REFERENCE",
                                message=f"Node '{node.key}' input '{name}' references an undeclared or non-ancestor output '{reference}'.",
                                node_key=node.key,
                            )
                        )
                    elif declared is None or declared.kind != output_type:
                        issues.append(
                            WorkflowIssue(
                                code="REFERENCE_TYPE_MISMATCH",
                                message=f"Output '{reference}' is incompatible with node input '{name}'.",
                                node_key=node.key,
                            )
                        )
            elif isinstance(value, (dict, list)) and _contains_reference(value):
                issues.append(
                    WorkflowIssue(
                        code="MALFORMED_REFERENCE",
                        message=f"Node '{node.key}' input '{name}' must contain one reference as its full value.",
                        node_key=node.key,
                    )
                )

    if set(inputs) != set(used_inputs):
        unknown = sorted(set(inputs) - set(used_inputs))
        missing = sorted(set(used_inputs) - set(inputs))
        if unknown:
            issues.append(
                WorkflowIssue(
                    code="UNKNOWN_LAUNCH_INPUT", message=f"Unused launch inputs are not accepted: {', '.join(unknown)}."
                )
            )
        if missing:
            issues.append(
                WorkflowIssue(
                    code="MISSING_LAUNCH_INPUT", message=f"Required launch inputs are missing: {', '.join(missing)}."
                )
            )
    for name, kind in used_inputs.items():
        if name in inputs and not _matches_type(inputs[name], kind):
            issues.append(WorkflowIssue(code="INVALID_LAUNCH_INPUT", message=f"Launch input '{name}' must be {kind}."))
        elif (
            name in inputs
            and isinstance(inputs[name], str)
            and (not inputs[name].strip() or len(inputs[name]) > MAX_INPUT_CHARS)
        ):
            issues.append(
                WorkflowIssue(
                    code="INVALID_LAUNCH_INPUT",
                    message=f"Launch input '{name}' must be non-empty and at most {MAX_INPUT_CHARS} characters.",
                )
            )
    return issues


def _contains_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return _is_reference(value) or any(_contains_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_reference(item) for item in value)
    return False


def catalogue_payload() -> list[dict[str, Any]]:
    """The node catalogue and its audited execution eligibility for the editor."""
    return [
        {
            "kind": spec.key,
            "title": spec.title,
            "risk": spec.risk,
            "summary": spec.summary,
            "writes": spec.writes,
            "execution": WORKFLOW_EXECUTION_POLICY[spec.key],
            "inputs": [
                {
                    "name": name,
                    "kind": declared.kind,
                    "required": declared.required,
                    "description": declared.description,
                }
                for name, declared in spec.inputs.items()
            ],
            "outputs": spec.outputs,
        }
        for spec in CATALOGUE
    ]
