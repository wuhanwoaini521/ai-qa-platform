"""Turn a sentence into a candidate workflow.

The model proposes; the server decides. Every node the model returns is validated against the same
catalogue and the same deterministic gate the editor and the runtime use, so a candidate can never
introduce a node kind the platform cannot run. Nothing here saves, publishes or executes anything:
a candidate is a response body the user has to accept.
"""

from __future__ import annotations

import json
from typing import Any

from project_model.workflow_definition import (
    MAX_INPUT_CHARS,
    NODE_KINDS,
    WorkflowEdgeSpec,
    WorkflowGraphSpec,
    WorkflowNodeSpec,
    validate_graph,
)
from qa_core.ai.models import AICompletionRequest
from qa_core.ai.provider import clean_json_text
from qa_core.ai.registry import AIProviderRegistry
from qa_core.failure.redactor import SensitiveRedactor

from app.services.workflow_definition_service import issues_payload

MAX_PROMPT_CHARS = 2000
PLANNER_PROMPT_ID = "workflow_planner"

SYSTEM_INSTRUCTION = (
    "You plan QA workflows for a quality platform. You may only use the node kinds listed in the "
    "catalogue, each with the inputs it declares. Reply with one JSON object and nothing else:\n"
    '{"summary": "<one sentence>", "nodes": [{"key": "lower_snake_case", "kind": "<catalogue key>", '
    '"inputs": {"<declared input>": "<value>"}, "rationale": "<why this step, in the user\'s language>"}], '
    '"edges": [{"source": "<node key>", "target": "<node key>"}]}\n'
    "Rules: every kind must appear in the catalogue; every required input must be present; the graph must "
    "be acyclic; keys must be unique lower_snake_case; declare no more than 30 nodes; never write code, "
    "never invent an input, never add a step whose only purpose is to run a shell command or a script. "
    "If the request needs a step the catalogue does not offer, plan the closest supported workflow and say "
    "so in the summary."
)


class WorkflowPlanUnavailable(RuntimeError):
    """The provider could not produce a plan; nothing was saved."""


def _text(value: Any, limit: int) -> str:
    return str(value)[:limit] if value is not None else ""


def _inputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for name, raw in value.items():
        if not isinstance(name, str):
            continue
        if isinstance(raw, (str, int, float, bool)):
            cleaned[name] = raw if not isinstance(raw, str) else raw[:MAX_INPUT_CHARS]
        elif isinstance(raw, list):
            cleaned[name] = [str(item)[:200] for item in raw[:50] if isinstance(item, (str, int, float))]
    return cleaned


class WorkflowPlannerService:
    """One model call, one validated candidate, no side effects."""

    @staticmethod
    def catalogue_prompt() -> str:
        lines = []
        for spec in NODE_KINDS.values():
            required = [name for name, item in spec.inputs.items() if item.required]
            optional = [name for name, item in spec.inputs.items() if not item.required]
            lines.append(
                f"- {spec.key} ({spec.risk}): {spec.summary} required={required or 'none'} "
                f"optional={optional or 'none'}"
            )
        return "\n".join(lines)

    async def plan(self, prompt: str, *, project_id: str, actor: str) -> dict[str, Any]:
        provider = AIProviderRegistry.get_provider()
        request = AICompletionRequest(
            prompt=(
                f"Project: {project_id}\n"
                f"Catalogue of node kinds:\n{self.catalogue_prompt()}\n\n"
                f"Write a workflow for this request:\n{prompt[:MAX_PROMPT_CHARS]}"
            ),
            system_instruction=SYSTEM_INSTRUCTION,
            prompt_id=PLANNER_PROMPT_ID,
            prompt_version="1",
            temperature=0.1,
            max_tokens=2400,
            timeout_seconds=60,
            max_retries=1,
        )
        try:
            response = await provider.complete(request)
        except Exception as error:  # the provider is allowed to be down; the caller gets a clear reason
            raise WorkflowPlanUnavailable(f"The AI provider could not plan this workflow: {error}") from error

        try:
            raw = json.loads(clean_json_text(response.content))
        except (TypeError, ValueError) as error:
            raise WorkflowPlanUnavailable("The AI provider did not return a workflow plan.") from error
        if not isinstance(raw, dict):
            raise WorkflowPlanUnavailable("The AI provider did not return a workflow plan.")

        nodes: list[dict[str, Any]] = []
        rationales: dict[str, str] = {}
        for item in raw.get("nodes") or []:
            if not isinstance(item, dict):
                continue
            key = _text(item.get("key"), 60)
            kind = _text(item.get("kind"), 80)
            nodes.append({"key": key, "kind": kind, "inputs": _inputs(item.get("inputs"))})
            rationales[key] = _text(item.get("rationale"), 400)
        edges = [
            {"source": _text(item.get("source"), 60), "target": _text(item.get("target"), 60)}
            for item in raw.get("edges") or []
            if isinstance(item, dict)
        ]

        graph = WorkflowGraphSpec(
            nodes=[WorkflowNodeSpec.model_validate(node) for node in nodes],
            edges=[WorkflowEdgeSpec.model_validate(edge) for edge in edges],
        )
        issues = validate_graph(graph)
        for node in nodes:
            node["rationale"] = rationales.get(node["key"], "")
        return {
            "summary": _text(raw.get("summary"), 600),
            "graph": {"nodes": nodes, "edges": edges},
            "issues": issues_payload(issues),
            "valid": not issues,
            "invocation_id": response.invocation_id,
            "provider_note": SensitiveRedactor.redact_text(_text(raw.get("note"), 600)),
            "planned_by": actor,
        }
