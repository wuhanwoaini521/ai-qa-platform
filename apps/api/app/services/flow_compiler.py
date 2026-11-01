"""Compile an authored flow document into the existing recorder/pytest pipeline.

The flow canvas owns authoring only. Compilation reuses `RecorderStep` and
`generate_python_case`, so a compiled flow behaves exactly like a recorded case: same variables,
same evidence markers, same runner, same nodeid contract.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.recorder_service import (
    RecorderGenerateRequest,
    RecorderLocator,
    RecorderStep,
    generate_python_case,
)

NodeKind = Literal["navigate", "click", "fill", "assert_text", "assert_visible", "wait", "condition"]
LocatorKind = Literal["css", "test_id", "role", "label", "placeholder", "id", "name", "text"]

MAX_NODES = 300
MAX_DEPTH = 5


class FlowNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    kind: NodeKind
    description: str = Field(default="", max_length=160)
    url: str | None = Field(default=None, max_length=2048)
    locator_kind: LocatorKind = "css"
    locator_value: str | None = Field(default=None, max_length=2000)
    locator_name: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, max_length=4000)
    # Assertion-to-criterion binding: assert nodes carry the acceptance criteria they verify.
    criterion_ids: list[str] = Field(default_factory=list, max_length=10)
    condition_kind: Literal["css", "text", "test_id"] = "css"
    condition_value: str | None = Field(default=None, max_length=500)
    # Data variables: a fill value read from the run environment instead of the authored literal.
    env_var: str | None = Field(default=None, max_length=120)
    then: list["FlowNode"] = Field(default_factory=list, max_length=100)
    else_nodes: list["FlowNode"] = Field(default_factory=list, max_length=100)

    @field_validator("else_nodes", mode="before")
    @classmethod
    def _accept_else_alias(cls, value):
        return value

    @field_validator("env_var")
    @classmethod
    def _normalize_env_var(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", normalized):
            raise ValueError("environment variable names must look like QA_DATA_EMAIL")
        return normalized

    @model_validator(mode="after")
    def validate_shape(self):
        if self.kind == "condition":
            if not (self.condition_value or "").strip():
                raise ValueError("condition node requires a condition value")
            if self.kind != "condition" and (self.then or self.else_nodes):
                raise ValueError("only condition nodes may carry branches")
        elif self.then or self.else_nodes:
            raise ValueError("only condition nodes may carry branches")
        if self.kind == "navigate":
            if not (self.url or "").strip():
                raise ValueError("navigate node requires a url")
        elif self.kind in {"click", "fill", "assert_text", "assert_visible"}:
            if not (self.locator_value or "").strip():
                raise ValueError(f"{self.kind} node requires a locator")
            if self.kind == "fill":
                if self.env_var and self.value is not None:
                    raise ValueError("a fill node takes either a literal value or an environment variable, not both")
                if not self.env_var and self.value is None:
                    raise ValueError("fill node requires a value")
            elif self.kind == "assert_text" and self.value is None:
                raise ValueError("assert_text node requires a value")
        elif self.kind == "wait":
            try:
                wait_ms = int(self.value or "1000")
            except ValueError as error:
                raise ValueError("wait node requires a millisecond value") from error
            if not 0 <= wait_ms <= 120_000:
                raise ValueError("wait node must be between 0 and 120000 ms")
        return self


FlowNode.model_rebuild(force=True)


class FlowDocument(BaseModel):
    version: Literal[1] = 1
    test_name: str = Field(default="flow_canvas_case", min_length=1, max_length=120)
    nodes: list[FlowNode] = Field(default_factory=list, max_length=MAX_NODES)

    @model_validator(mode="after")
    def validate_document(self):
        if not self.nodes:
            raise ValueError("a flow needs at least one node")
        if self.nodes[0].kind != "navigate":
            raise ValueError("a flow must start with a navigate node")
        ids = self._collect_ids(self.nodes)
        if len(ids) != len(set(ids)):
            raise ValueError("node ids must be unique")
        self._check_depth(self.nodes, 1)
        return self

    @staticmethod
    def _collect_ids(nodes: list[FlowNode]) -> list[str]:
        collected: list[str] = []
        for node in nodes:
            collected.append(node.id)
            collected.extend(FlowDocument._collect_ids(node.then))
            collected.extend(FlowDocument._collect_ids(node.else_nodes))
        return collected

    @staticmethod
    def _check_depth(nodes: list[FlowNode], depth: int) -> None:
        if depth > MAX_DEPTH:
            raise ValueError(f"conditional nesting deeper than {MAX_DEPTH} levels is not supported")
        for node in nodes:
            FlowDocument._check_depth(node.then, depth + 1)
            FlowDocument._check_depth(node.else_nodes, depth + 1)


def _locator(node: FlowNode) -> RecorderLocator | None:
    if node.locator_value is None:
        return None
    return RecorderLocator(
        kind=node.locator_kind,
        value=node.locator_value,
        name=node.locator_name,
    )


def _to_step(node: FlowNode) -> RecorderStep:
    if node.kind == "navigate":
        return RecorderStep(id=node.id, action="navigate", url=node.url, description=node.description)
    if node.kind == "wait":
        return RecorderStep(
            id=node.id, action="wait", value=str(int(node.value or "1000")), description=node.description
        )
    if node.kind == "condition":
        return RecorderStep(
            id=node.id,
            action="condition",
            condition_kind=node.condition_kind,
            condition_value=node.condition_value,
            description=node.description or f"if {node.condition_value}",
            then_steps=[_to_step(child) for child in node.then],
            else_steps=[_to_step(child) for child in node.else_nodes],
        )
    action = {
        "click": "click",
        "fill": "fill",
        "assert_text": "assert_text",
        "assert_visible": "assert_visible",
    }[node.kind]
    return RecorderStep(
        id=node.id,
        action=action,
        locator=_locator(node),
        value=None if node.env_var else node.value,
        value_redacted=bool(node.env_var),
        secret_env_var=node.env_var,
        description=node.description,
    )


def compile_flow(document: FlowDocument) -> dict:
    """Return the generated pytest source for a flow document plus compile metadata."""
    steps = [_to_step(node) for node in document.nodes]
    request = RecorderGenerateRequest(test_name=document.test_name, steps=steps)
    code = generate_python_case(request)
    return {
        "code": code,
        "test_name": _normalized_test_name(document.test_name),
        "node_count": len(FlowDocument._collect_ids(document.nodes)),
        "step_count": _count_steps(steps),
        "assertions": _assertions(document.nodes),
        "warnings": _warnings(document),
    }


def _assertions(nodes: list[FlowNode]) -> list[dict]:
    """Assertion nodes that declare criteria, flattened in execution order."""
    found: list[dict] = []
    for node in nodes:
        if node.kind in {"assert_text", "assert_visible"} and node.criterion_ids:
            requirement = node.kind == "assert_text" and f' contains "{node.value}"' or ""
            statement = (node.description or f"assert {node.locator_value}{requirement}").strip()
            found.append(
                {
                    "node_id": node.id,
                    "criterion_ids": node.criterion_ids,
                    "statement": statement[:400],
                    "check": f"{node.kind}:{node.locator_kind}={node.locator_value}{requirement}",
                }
            )
        found.extend(_assertions(node.then))
        found.extend(_assertions(node.else_nodes))
    return found


def _normalized_test_name(name: str) -> str:
    import re

    normalized = re.sub(r"\W+", "_", name).strip("_") or "test_recorded_case"
    if normalized[0].isdigit():
        normalized = "test_" + normalized
    if not normalized.startswith("test_"):
        normalized = "test_" + normalized
    return normalized


def _count_steps(steps: list[RecorderStep]) -> int:
    total = 0
    for step in steps:
        total += 1 + _count_steps(step.then_steps) + _count_steps(step.else_steps)
    return total


def _warnings(document: FlowDocument) -> list[str]:
    warnings: list[str] = []
    for node in document.nodes:
        if node.kind in {"fill", "assert_text"} and node.value and "$" in node.value:
            warnings.append(
                f"{node.id}: value looks like a variable placeholder; use a plain value or set one in the run environment."
            )
    return warnings
