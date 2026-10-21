"""A planned workflow is a proposal, and the server — not the model — decides whether it is legal.

The model is allowed to return anything. Everything it returns is coerced, validated against the same
catalogue the editor uses, and handed back with the issues attached. Nothing is saved here.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.services.workflow_planner_service import WorkflowPlanUnavailable, WorkflowPlannerService
from qa_core.ai.registry import AIProviderRegistry

pytestmark = pytest.mark.integration


class _Provider:
    def __init__(self, payload: dict | str | Exception) -> None:
        self.payload = payload
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)
        if isinstance(self.payload, Exception):
            raise self.payload
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(content=content, invocation_id="inv_plan", structured_data=None)


def _use(monkeypatch, payload) -> _Provider:
    provider = _Provider(payload)
    monkeypatch.setattr(AIProviderRegistry, "get_provider", classmethod(lambda cls, *a, **k: provider))
    return provider


@pytest.mark.asyncio
async def test_a_catalogue_only_plan_comes_back_valid_with_its_rationale(monkeypatch):
    _use(
        monkeypatch,
        {
            "summary": "读出差距，起草，人工批准后写入。",
            "nodes": [
                {
                    "key": "collect",
                    "kind": "discovery.collect_gaps",
                    "inputs": {"discovery_run_id": "qd_1"},
                    "rationale": "先取差距。",
                },
                {"key": "generate", "kind": "tests.generate", "rationale": "再起草用例。"},
                {"key": "approve", "kind": "task.request_approval", "rationale": "写入前必须人工批准。"},
                {"key": "write", "kind": "source.write_generated", "rationale": "批准后才写入。"},
            ],
            "edges": [
                {"source": "collect", "target": "generate"},
                {"source": "generate", "target": "approve"},
                {"source": "approve", "target": "write"},
            ],
        },
    )
    plan = await WorkflowPlannerService().plan("把差距变成用例并在批准后写入", project_id="proj", actor="u1")

    assert plan["valid"] is True
    assert plan["issues"] == []
    assert [node["key"] for node in plan["graph"]["nodes"]] == ["collect", "generate", "approve", "write"]
    assert plan["graph"]["nodes"][0]["rationale"] == "先取差距。"
    assert plan["summary"].startswith("读出差距")
    assert plan["invocation_id"] == "inv_plan"


@pytest.mark.asyncio
async def test_an_unknown_kind_is_reported_and_never_hidden(monkeypatch):
    _use(
        monkeypatch,
        {
            "summary": "run a script",
            "nodes": [
                {"key": "shell", "kind": "shell.exec", "inputs": {"cmd": "rm -rf /"}},
                {"key": "generate", "kind": "tests.generate"},
            ],
            "edges": [{"source": "shell", "target": "generate"}],
        },
    )
    plan = await WorkflowPlannerService().plan("跑个脚本", project_id="proj", actor="u1")

    assert plan["valid"] is False
    assert "UNKNOWN_KIND" in {issue["code"] for issue in plan["issues"]}


@pytest.mark.asyncio
async def test_a_cycle_is_reported(monkeypatch):
    _use(
        monkeypatch,
        {
            "nodes": [
                {"key": "a", "kind": "failure.collect", "inputs": {"failure_id": "f1"}},
                {"key": "b", "kind": "tests.generate"},
            ],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        },
    )
    plan = await WorkflowPlannerService().plan("循环", project_id="proj", actor="u1")

    assert plan["valid"] is False
    assert {issue["code"] for issue in plan["issues"]} == {"CYCLE"}


@pytest.mark.asyncio
async def test_a_skipped_required_input_is_reported(monkeypatch):
    _use(
        monkeypatch,
        {"nodes": [{"key": "collect", "kind": "failure.collect"}], "edges": []},
    )
    plan = await WorkflowPlannerService().plan("分析失败", project_id="proj", actor="u1")

    assert plan["valid"] is False
    assert {issue["code"] for issue in plan["issues"]} == {"MISSING_INPUT"}


@pytest.mark.asyncio
async def test_the_model_cannot_smuggle_extra_fields_into_a_node(monkeypatch):
    _use(
        monkeypatch,
        {
            "nodes": [
                {
                    "key": "generate",
                    "kind": "tests.generate",
                    "inputs": {"unknown_input": "x", "nested": {"a": 1}},
                    "shell": "rm -rf /",
                    "rationale": "ok",
                }
            ],
            "edges": [],
        },
    )
    plan = await WorkflowPlannerService().plan("起草", project_id="proj", actor="u1")

    node = plan["graph"]["nodes"][0]
    assert "shell" not in node
    assert node["inputs"] == {"unknown_input": "x"}
    assert plan["valid"] is False  # the undeclared input is refused by the catalogue gate


@pytest.mark.asyncio
async def test_a_provider_outage_is_an_error_not_an_empty_plan(monkeypatch):
    _use(monkeypatch, RuntimeError("AI provider unavailable"))

    with pytest.raises(WorkflowPlanUnavailable, match="could not plan"):
        await WorkflowPlannerService().plan("随便", project_id="proj", actor="u1")


@pytest.mark.asyncio
async def test_text_that_is_not_a_plan_is_an_error_not_a_crash(monkeypatch):
    _use(monkeypatch, "I cannot help with that.")

    with pytest.raises(WorkflowPlanUnavailable, match="did not return a workflow plan"):
        await WorkflowPlannerService().plan("随便", project_id="proj", actor="u1")


@pytest.mark.asyncio
async def test_planning_leaves_the_project_untouched(client, monkeypatch):
    project = await client.post("/api/projects", json={"name": "Planner project", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    _use(
        monkeypatch,
        {
            "summary": "one step",
            "nodes": [{"key": "generate", "kind": "tests.generate"}],
            "edges": [],
        },
    )

    planned = await client.post(
        f"/api/projects/{project_id}/workflows/plan", json={"prompt": "只生成用例，先不要写入"}
    )
    assert planned.status_code == 200, planned.text
    assert planned.json()["valid"] is True
    assert planned.json()["graph"]["nodes"][0]["key"] == "generate"

    # Nothing was created: a candidate is a response body, not an artifact.
    listed = await client.get(f"/api/projects/{project_id}/workflows")
    assert listed.json()["definitions"] == []


@pytest.mark.asyncio
async def test_an_unavailable_provider_is_a_503_with_a_reason(client, monkeypatch):
    project = await client.post("/api/projects", json={"name": "Planner outage", "bootstrap_workspace": True})
    project_id = project.json()["id"]
    _use(monkeypatch, RuntimeError("AI provider unavailable"))

    planned = await client.post(f"/api/projects/{project_id}/workflows/plan", json={"prompt": "任何流程"})
    assert planned.status_code == 503
    assert "could not plan" in planned.json()["detail"]
