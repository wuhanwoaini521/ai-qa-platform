from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from app.container import get_quality_discovery_service
from app.main import app as fastapi_app
from app.persistence.models import (
    AutomationBindingORM,
    BrowserSessionORM,
    ProjectORM,
    QualityDiscoveryRunORM,
    RequirementORM,
    utc_now,
)
from app.persistence.models import (
    TestCaseORM as _TestCaseORM,
)
from app.persistence.models import (
    TestDesignORM as _TestDesignORM,
)
from app.persistence.models import (
    TestExecutionORM as _TestExecutionORM,
)
from app.persistence.models import (
    TestRunORM as _TestRunORM,
)
from app.ports.browser_runtime import BrowserRuntimeSession, BrowserSnapshot
from app.services import quality_discovery_service as discovery_module
from app.services.decision_service import DecisionService
from app.services.quality_discovery_service import (
    DiscoveryRunCreate,
    DiscoveryStatus,
    QualityDiscoveryService,
)
from app.settings import settings
from project_model.models import (
    AutomationBindingCreate,
    AutomationBindingStatus,
    DecisionResult,
    FrameworkType,
)
from qa_core.ai.models import AICompletionResponse, CodeAssistantResponse
from qa_core.ai.models import TestCaseGenerationItem as _TestCaseGenerationItem

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "quality-discovery"
SITE = json.loads((FIXTURE_DIR / "site.json").read_text(encoding="utf-8"))["pages"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("linked_requirement", "workspace_matches", "observed_url", "expected"),
    [
        (False, True, "https://www.gu-global.com/us/en/", "PARTIAL"),
        (True, True, None, "AUTOMATED"),
        (True, False, "https://www.gu-global.com/us/en/", "AUTOMATED"),
        (True, True, "http://demo-shop.example.test/", "AUTOMATED"),
        (True, True, "https://www.gu-global.com/us/en/products", "VERIFIED"),
    ],
    ids=["unlinked-explore", "unknown-site", "other-workspace", "demo-site", "matching-site"],
)
async def test_discovery_coverage_requires_explicit_source_and_execution_site(
    test_db_session, linked_requirement, workspace_matches, observed_url, expected
):
    target = "https://www.gu-global.com/us/en/"
    nodeid = "tests/test_demo_shop.py::test_search"
    async with test_db_session() as session:
        session.add(ProjectORM(id="project_scope", name="Demo project"))
        session.add(RequirementORM(id="requirement_scope", project_id="project_scope", title="Search"))
        session.add(
            _TestCaseORM(
                id="case_scope",
                project_id="project_scope",
                requirement_id="requirement_scope",
                title="Search",
                tags=["Search"],
                automation_status="AUTOMATED",
            )
        )
        await session.flush()
        session.add(
            AutomationBindingORM(
                id="binding_scope",
                test_case_id="case_scope",
                workspace_id="project_scope",
                nodeid=nodeid,
                file_path="tests/test_demo_shop.py",
                status="ACTIVE",
            )
        )
        run = _TestRunORM(
            id="run_scope",
            project_id="project_scope",
            status="PASSED",
            workspace_id="project_scope" if workspace_matches else "other_workspace",
            executions=[_TestExecutionORM(id="execution_scope", nodeid=nodeid, status="PASSED")],
        )
        session.add(run)
        await session.flush()
        if observed_url:
            session.add(
                BrowserSessionORM(
                    id="browser_scope",
                    run_id=run.id,
                    case_execution_id="execution_scope",
                    browser_session_id="session_scope",
                    page_id="page_scope",
                    nodeid=nodeid,
                    current_url=observed_url,
                    status="closed",
                )
            )
        session.add(
            QualityDiscoveryRunORM(
                id="discovery_scope",
                project_id="project_scope",
                requested_by="fixture",
                mode="EXPLORE",
                start_url=target,
                requirement_id="requirement_scope" if linked_requirement else None,
                requirement_text="",
                allowed_domains=[],
                status="COMPLETED",
                progress={},
                result={
                    "requirements": [
                        {
                            "id": "requirement_scope:REQ-001",
                            "source_id": "requirement_scope",
                            "feature": "Search",
                            "expected_behavior": "Search products",
                            "checks": [],
                        }
                    ]
                    if linked_requirement
                    else [],
                    "features": [
                        {
                            "feature_id": "feature_search",
                            "name": "Search",
                            "status": "OBSERVED",
                            "evidence_ids": ["evidence_gu_search"],
                            "state_ids": [],
                            "requirement_ids": [],
                        }
                    ],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "gaps": [],
                },
            )
        )
        await session.commit()
    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    await service._build_quality_map("discovery_scope")
    row = await service.get("discovery_scope")
    feature = row.result["features"][0]
    assert feature["coverage_status"] == expected
    assert feature["status"] == "OBSERVED"
    assert feature["evidence_ids"] == ["evidence_gu_search"]
    if not linked_requirement:
        assert await service._requirement_input(row) is None
        assert row.result["requirements"] == []
        assert feature["test_case_ids"] == []
        assert feature["automation"] == []
        assert feature["test_case_candidates"][0]["mapping_status"] == "NEEDS_REVIEW"
    elif expected != "VERIFIED":
        assert feature["automation"][0]["last_run_id"] is None


@pytest.fixture
def tmp_path(request):
    # This managed Windows workspace cannot enumerate the system temp root; keep fixture state
    # inside the task's isolated evidence folder instead of changing pytest's global configuration.
    path = (
        Path(__file__).parents[3]
        / ".ai-runs"
        / "2026-10-09-quality-discovery"
        / "test-work"
        / f"{request.node.name}-{uuid4().hex}"
    )
    path.mkdir(parents=True, exist_ok=False)
    return path


class DiscoveryFixtureAI:
    provider_name = "quality-discovery-golden"
    model = "fixture-v1"

    def __init__(self):
        self.calls = 0
        self.suggestions = []

    async def complete(self, request):
        self.calls += 1
        prompt = json.loads(request.prompt)
        if request.prompt_id == "quality_discovery_requirements":
            data = {
                "requirements": [
                    {
                        "feature": "Search",
                        "expected_behavior": "“Search results for qa sample” are displayed after submitting the query.",
                        "acceptance_criteria": [
                            "“Search results for qa sample” are displayed after submitting the query."
                        ],
                        "checks": [
                            {
                                "target": "Search results for qa sample",
                                "attribute": "visible",
                                "expected": True,
                                "when": "after_action",
                                "criterion": "“Search results for qa sample” are displayed after submitting the query.",
                            }
                        ],
                        "ambiguous": False,
                    }
                ],
                "ambiguities": [],
            }
        else:
            url = urlparse(prompt["observation"]["url"])
            candidates = prompt["candidates"]
            observed_text = prompt["observation"]["visible_text"]
            if url.path == "/search" and "Search results for qa sample" in observed_text:
                data = {
                    "page_type": "search_results",
                    "features": [],
                    "candidate_ids": [],
                    "done": True,
                    "reason_summary": "The search transition was observed.",
                }
            elif url.path == "/" or url.path == "/search":
                controls = prompt["observation"]["controls"]
                target = next((item for item in controls if item.get("type") == "search"), None)
                self.suggestions.append([item["candidate_id"] for item in candidates[:1]])
                data = {
                    "page_type": "home" if url.path == "/" else "search",
                    "features": (
                        [
                            {
                                "name": "Search",
                                "description": "Search products",
                                "target_id": f"el_{target['index']}",
                                "evidence_text": "",
                            }
                        ]
                        if target
                        else []
                    ),
                    "candidate_ids": [item["candidate_id"] for item in candidates[:1]],
                    "done": False,
                    "reason_summary": "Explore the observed search journey.",
                }
            else:
                data = {
                    "page_type": "search_results",
                    "features": [],
                    "candidate_ids": [],
                    "done": True,
                    "reason_summary": "The search transition was observed.",
                }
        return AICompletionResponse(
            content=json.dumps(data),
            structured_data=data,
            provider=self.provider_name,
            model=self.model,
            input_tokens=80,
            output_tokens=40,
        )


class DiscoveryFixtureBrowserRuntime:
    """Deterministic BrowserRuntime contract for the API and Jev golden test."""

    _png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1WQAAAAASUVORK5CYII="
    )

    def __init__(self):
        self.sessions = {}
        self.executed_operations = []
        self.closed = False

    async def create_session(self, **_kwargs):
        session = BrowserRuntimeSession(id=uuid4().hex)
        self.sessions[session.id] = {"url": "about:blank", "search": ""}
        return session

    async def restrict_navigation(self, session_id, allowed_hosts):
        self.sessions[session_id]["allowed_hosts"] = set(allowed_hosts)

    async def navigate(self, session_id, url, **_kwargs):
        self.sessions[session_id]["url"] = url
        return 200

    async def get_page(self, session_id):
        runtime = self

        class Page:
            @property
            def url(self):
                return runtime.sessions[session_id]["url"]

            async def evaluate(self, _expression):
                return {"y": 0, "height": 500, "viewport": 720}

        return Page()

    async def snapshot(self, session_id, *, include_screenshot=True, **_kwargs):
        state = self.sessions[session_id]
        parsed = urlparse(state["url"])
        page_html = SITE.get(parsed.path, "")
        if parsed.path == "/search" and parse_qs(parsed.query).get("q"):
            page_html = page_html.replace("Search products", "Search results for qa sample")
        title_match = re.search(r"<title>(.*?)</title>", page_html, re.I | re.S)
        title = title_match.group(1) if title_match else "Unknown"
        text = re.sub(r"<[^>]+>", " ", page_html)
        if parsed.path == "/":
            controls = [
                {
                    "index": 0,
                    "tag": "a",
                    "role": "link",
                    "name": "Search",
                    "href": "/search",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "index": 1,
                    "tag": "a",
                    "role": "link",
                    "name": "Products",
                    "href": "/products",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "index": 2,
                    "tag": "a",
                    "role": "link",
                    "name": "Cart",
                    "href": "/cart",
                    "visible": True,
                    "enabled": True,
                },
            ]
        else:
            controls = [
                {
                    "index": 0,
                    "tag": "input",
                    "type": "search",
                    "role": "textbox",
                    "name": "Search",
                    "placeholder": "Search",
                    "visible": True,
                    "enabled": True,
                },
                {"index": 1, "tag": "button", "role": "button", "name": "Search", "visible": True, "enabled": True},
            ]
        return BrowserSnapshot(
            session_id=session_id,
            url=state["url"],
            title=title,
            accessibility_tree=text,
            text=text,
            controls=controls,
            screenshot=self._png if include_screenshot else None,
            console=[],
            network=[],
        )

    async def verify_locator(self, _session_id, _candidate, _event):
        return {"verified": True}

    async def execute_action(self, session_id, candidate, action):
        state = self.sessions[session_id]
        operation = action["type"]
        self.executed_operations.append(operation)
        if operation == "click" and candidate.get("kind") == "role" and candidate.get("value") == "link":
            state["url"] = "http://shop.example.test/search"
        elif operation == "fill":
            state["search"] = action["value"]
        elif operation == "press" and action.get("value") == "Enter":
            from urllib.parse import urlencode

            state["url"] = f"http://shop.example.test/search?{urlencode({'q': state['search']})}"
        return None

    async def close_session(self, session_id):
        self.sessions.pop(session_id, None)
        self.closed = True


@pytest.mark.asyncio
async def test_discovery_api_runs_browserruntime_contract_and_jev_choice_selects_executed_candidate(
    client, test_db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    ai = DiscoveryFixtureAI()
    runtime = DiscoveryFixtureBrowserRuntime()
    decisions = []

    async def fixture_jev(_service, request, **_kwargs):
        assert "多步验收标准应按步骤逐步验证" in request.instructions
        candidates = request.state["candidates"]
        if not decisions:
            assert len(candidates) >= 3
            matches = [item for item in candidates if item["target"] == "Products" and item["target_role"] == "link"]
        else:
            matches = [
                item for item in candidates if item["target_role"] == "textbox" and item.get("operation") is None
            ]
        if not matches:
            raise AssertionError(f"Jev fixture could not find its expected candidate: {candidates}")
        chosen = matches[0]
        decisions.append(chosen["key"])
        return DecisionResult(
            choice=chosen["key"],
            provider="jev-golden-fixture",
            model="decision-v1",
            confidence=0.99,
            probabilities={chosen["key"]: 0.99},
            reason="Choose the highest-value safe, observed candidate.",
        )

    monkeypatch.setattr(DecisionService, "choose", fixture_jev)
    discovery = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime,
        decisions=DecisionService(),
        provider_factory=lambda: ai,
    )
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: discovery
    try:
        project_response = await client.post(
            "/api/projects", json={"name": "Quality Discovery Golden", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        created = await client.post(
            "/api/discovery/runs",
            json={"project_id": project_id, "start_url": "http://shop.example.test/", "mode": "EXPLORE"},
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]

        for _ in range(400):
            response = await client.get(f"/api/discovery/runs/{run_id}")
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Quality Discovery did not reach a terminal state within 20 seconds")
        task = discovery._tasks.get(run_id)
        if task is not None:
            await task

        assert run["status"] == DiscoveryStatus.COMPLETED.value, run.get("error")
        assert run["result"]["ai"]["provider"] == ai.provider_name
        assert run["result"]["jev"]["provider"] == "jev-golden-fixture"
        assert run["result"]["ai"]["calls"] == ai.calls == 3
        assert run["result"]["ai"]["input_tokens"] == 240
        assert run["result"]["ai"]["output_tokens"] == 120
        assert run["result"]["jev"]["decisions"] == len(decisions) == 2
        assert run["result"]["jev"]["fallbacks"] == 0
        assert len(decisions) == 2
        assert decisions[0] != ai.suggestions[0][0]
        assert len(run["result"]["states"]) == 3
        assert len(run["result"]["edges"]) == 2
        assert run["result"]["frontier"]
        assert {item["status"] for item in run["result"]["frontier"]} <= {
            "PENDING",
            "EXECUTED",
            "SKIPPED",
            "BLOCKED_BY_POLICY",
        }
        executed_candidates = {
            item["candidate_id"] for item in run["result"]["frontier"] if item["status"] == "EXECUTED"
        }
        assert {action["candidate_id"] for action in run["result"]["actions"]} <= executed_candidates
        assert all(item["status"] != "SELECTED" for item in run["result"]["frontier"])
        assert {state["page_type"] for state in run["result"]["states"]} == {"home", "search", "search_results"}
        assert all(action["jev_choice"] == action["candidate_id"] for action in run["result"]["actions"])
        decisions_by_id = {item["decision_id"]: item for item in run["result"]["decisions"]}
        assert len(decisions_by_id) == len(decisions)
        assert all(item["candidate_count"] == len(item["candidate_ids"]) for item in decisions_by_id.values())
        assert all(item["selected_candidate_id"] in item["candidate_ids"] for item in decisions_by_id.values())
        assert all(
            decisions_by_id[action["jev_decision_id"]]["selected_candidate_id"] == action["candidate_id"]
            for action in run["result"]["actions"]
        )
        assert [action["jev_choice"] for action in run["result"]["actions"]] == decisions
        assert runtime.executed_operations == ["click", "fill", "press"]
        assert runtime.closed is True
        feature = next(item for item in run["result"]["features"] if item["name"] == "Search")
        assert feature["status"] == "VERIFIED"
        assert feature["verified_by_action_id"] in {action["candidate_id"] for action in run["result"]["actions"]}
        assert feature["verification_state_ids"]
        assert feature["evidence_ids"]
        assert feature["trust"] == "VERIFIED"
        assert feature["observed_transition_action_ids"]
        assert feature["evidence_ids"]
        features_response = await client.get(f"/api/discovery/runs/{run_id}/features")
        gaps_response = await client.get(f"/api/discovery/runs/{run_id}/gaps")
        coverage = await client.get(f"/api/discovery/runs/{run_id}/coverage")
        assert features_response.status_code == 200 and features_response.json()
        assert gaps_response.status_code == 200
        assert coverage.status_code == 200
        assert coverage.json()
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "jev_enabled"), [("fake", True), ("openai-compatible", False)])
async def test_runtime_preflight_blocks_without_calling_browser_or_ai(
    client, test_db_session, monkeypatch, provider, jev_enabled
):
    from pydantic import SecretStr

    base = discovery_module.get_config()
    runtime_config = base.model_copy(
        update={
            "ai": base.ai.model_copy(
                update={
                    "provider": provider,
                    "api_key": SecretStr("test-only-not-used" if provider != "fake" else ""),
                }
            ),
            "jev": base.jev.model_copy(
                update={"enabled": jev_enabled, "api_key": SecretStr("test-only-not-used" if jev_enabled else "")}
            ),
            "discovery": base.discovery.model_copy(update={"enabled": True, "require_ai": True, "require_jev": True}),
        }
    )
    monkeypatch.setattr(discovery_module, "get_config", lambda: runtime_config)
    browser = DiscoveryFixtureBrowserRuntime()
    discovery = QualityDiscoveryService(test_db_session, browser_runtime=browser)
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: discovery
    try:
        project_response = await client.post(
            "/api/projects", json={"name": "Discovery Runtime Preflight", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        created = await client.post(
            "/api/discovery/runs",
            json={
                "project_id": project_response.json()["id"],
                "start_url": "http://shop.example.test/",
                "mode": "EXPLORE",
            },
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]

        for _ in range(100):
            response = await client.get(f"/api/discovery/runs/{run_id}")
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Runtime preflight did not stop the run")
        task = discovery._tasks.get(run_id)
        if task is not None:
            await task

        assert run["status"] == DiscoveryStatus.BLOCKED.value
        assert browser.sessions == {}
        assert (run["result"].get("ai") or {}).get("calls", 0) == 0
        assert (run["result"].get("jev") or {}).get("decisions", 0) == 0
        assert "test-only-not-used" not in json.dumps(run["result"])
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


@pytest.mark.asyncio
async def test_jev_fallback_after_real_choice_preserves_provider_and_blocks_next_candidate(
    client, test_db_session, monkeypatch
):
    base = discovery_module.get_config()
    config = base.model_copy(update={"discovery": base.discovery.model_copy(update={"require_jev": True})})
    monkeypatch.setattr(discovery_module, "get_config", lambda: config)
    ai = DiscoveryFixtureAI()
    runtime = DiscoveryFixtureBrowserRuntime()
    real_choices = []

    async def decision_then_fallback(_service, request, **_kwargs):
        candidate = request.options[0].key
        if not real_choices:
            real_choices.append(candidate)
            return DecisionResult(
                choice=candidate,
                provider="jev",
                model="jev-1.13.0",
                confidence=0.99,
                probabilities={candidate: 0.99},
                reason="Choose the first safe candidate.",
            )
        return DecisionResult(
            choice=candidate,
            provider="fallback",
            attempted_provider="jev",
            attempted_model="jev-1.13.0",
            attempted_choice=candidate,
            confidence=0.5,
            probabilities={candidate: 0.5},
            reason="Low confidence fallback.",
            fallback_used=True,
        )

    monkeypatch.setattr(DecisionService, "choose", decision_then_fallback)
    discovery = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime,
        decisions=DecisionService(),
        provider_factory=lambda: ai,
    )
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: discovery
    try:
        project_response = await client.post(
            "/api/projects", json={"name": "Discovery Jev Fallback", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        created = await client.post(
            "/api/discovery/runs",
            json={
                "project_id": project_response.json()["id"],
                "start_url": "http://shop.example.test/",
                "mode": "EXPLORE",
            },
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]

        for _ in range(200):
            response = await client.get(f"/api/discovery/runs/{run_id}")
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Fallback decision did not stop exploration")
        task = discovery._tasks.get(run_id)
        if task is not None:
            await task

        assert run["status"] == DiscoveryStatus.BLOCKED.value
        assert run["result"]["jev"]["fallbacks"] == 1
        assert run["result"]["jev"]["provider"] == "jev"
        assert run["result"]["jev"]["model"] == "jev-1.13.0"
        assert [item["fallback_used"] for item in run["result"]["decisions"]] == [False, True]
        assert run["result"]["decisions"][1]["attempted_provider"] == "jev"
        assert run["result"]["decisions"][1]["attempted_model"] == "jev-1.13.0"
        assert run["result"]["decisions"][1]["selected_candidate_id"] is None
        assert run["result"]["decisions"][1]["attempted_choice"] in run["result"]["decisions"][1]["candidate_ids"]
        assert run["result"]["decisions"][1]["probabilities"]
        assert len(runtime.executed_operations) == 1
        assert run["result"]["actions"][0]["candidate_id"] == real_choices[0]
        frontier_statuses = {item["status"] for item in run["result"]["frontier"]}
        assert "EXECUTED" in frontier_statuses
        assert "BLOCKED" in frontier_statuses

        async def fallback_only(_service, request, **_kwargs):
            return DecisionResult(
                choice=None,
                provider="fallback",
                attempted_provider="jev",
                attempted_model="jev-1.13.0",
                confidence=0.5,
                fallback_used=True,
                reason="Provider abstained.",
            )

        monkeypatch.setattr(DecisionService, "choose", fallback_only)
        fallback_run_response = await client.post(
            "/api/discovery/runs",
            json={
                "project_id": project_response.json()["id"],
                "start_url": "http://shop.example.test/",
                "mode": "EXPLORE",
            },
        )
        assert fallback_run_response.status_code == 202, fallback_run_response.text
        fallback_run_id = fallback_run_response.json()["id"]
        for _ in range(200):
            fallback_response = await client.get(f"/api/discovery/runs/{fallback_run_id}")
            assert fallback_response.status_code == 200, fallback_response.text
            fallback_run = fallback_response.json()
            if fallback_run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Fallback-only decision did not stop exploration")
        task = discovery._tasks.get(fallback_run_id)
        if task is not None:
            await task
        assert fallback_run["status"] == DiscoveryStatus.BLOCKED.value
        assert fallback_run["result"]["jev"]["provider"] == "fallback"
        assert fallback_run["result"]["jev"]["model"] is None
        fallback_decision = fallback_run["result"]["decisions"][0]
        assert fallback_decision["attempted_provider"] == "jev"
        assert fallback_decision["attempted_model"] == "jev-1.13.0"
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


@pytest.mark.asyncio
async def test_low_confidence_jev_candidate_is_skipped_and_discovery_continues(client, test_db_session, monkeypatch):
    base = discovery_module.get_config()
    config = base.model_copy(update={"discovery": base.discovery.model_copy(update={"require_jev": True})})
    monkeypatch.setattr(discovery_module, "get_config", lambda: config)
    ai = DiscoveryFixtureAI()
    runtime = DiscoveryFixtureBrowserRuntime()
    attempted_candidates = []

    async def low_confidence_then_select(_service, request, **_kwargs):
        candidate = request.options[0].key
        attempted_candidates.append(candidate)
        if len(attempted_candidates) == 1:
            return DecisionResult(
                choice=None,
                provider="fallback",
                attempted_provider="jev",
                attempted_model="jev-1.13.0",
                attempted_choice=candidate,
                confidence=0.46,
                minimum_confidence=0.7,
                probabilities={candidate: 0.57},
                fallback_used=True,
                reason="below_minimum_confidence",
            )
        return DecisionResult(
            choice=candidate,
            provider="jev",
            model="jev-1.13.0",
            confidence=0.9,
            minimum_confidence=0.7,
            probabilities={candidate: 0.9},
            reason="Choose a confident safe candidate.",
        )

    monkeypatch.setattr(DecisionService, "choose", low_confidence_then_select)
    discovery = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime,
        decisions=DecisionService(),
        provider_factory=lambda: ai,
    )
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: discovery
    try:
        project_response = await client.post(
            "/api/projects", json={"name": "Discovery Low Confidence", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        created = await client.post(
            "/api/discovery/runs",
            json={
                "project_id": project_response.json()["id"],
                "start_url": "http://shop.example.test/",
                "mode": "EXPLORE",
            },
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]

        for _ in range(400):
            response = await client.get(f"/api/discovery/runs/{run_id}")
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Discovery did not continue after skipping a low-confidence candidate")
        task = discovery._tasks.get(run_id)
        if task is not None:
            await task

        skipped_candidate = attempted_candidates[0]
        assert run["status"] == DiscoveryStatus.COMPLETED.value, run.get("error")
        assert len(attempted_candidates) >= 2
        assert attempted_candidates[1] != skipped_candidate
        assert run["result"]["decisions"][0]["reason"] == "below_minimum_confidence"
        assert run["result"]["decisions"][0]["selected_candidate_id"] is None
        assert all(action["candidate_id"] != skipped_candidate for action in run["result"]["actions"])
        skipped = next(item for item in run["result"]["frontier"] if item["candidate_id"] == skipped_candidate)
        assert skipped["status"] == "SKIPPED"
        assert "置信度" in skipped["reason"]
        assert any(action["candidate_id"] != skipped_candidate for action in run["result"]["actions"])
        assert runtime.closed is True
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


@pytest.mark.asyncio
async def test_gap_action_rejects_actions_outside_the_gap_category(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    now = utc_now()
    gaps = [
        {"id": "gap-test-missing", "category": "TEST_MISSING", "item_id": "feature-search"},
        {"id": "gap-undocumented", "category": "UNDOCUMENTED_FEATURE", "item_id": "feature-wishlist"},
        {"id": "gap-automation-missing", "category": "AUTOMATION_MISSING", "item_id": "feature-search"},
    ]
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Gap Action Validation",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="test",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result={"gaps": gaps, "features": [], "gap_actions": {}},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    for gap_id, action in (
        ("gap-test-missing", "generate_automation"),
        ("gap-undocumented", "generate_tests"),
        ("gap-automation-missing", "create_requirement_draft"),
    ):
        with pytest.raises(ValueError, match="not available for"):
            await service.act_on_gap(run_id, gap_id, action)

    run = await service.get(run_id)
    assert run.result["gap_actions"] == {}


@pytest.mark.asyncio
async def test_ai_done_skips_every_safe_candidate_across_candidate_batches(
    client, test_db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    config = discovery_module.get_config()
    config = config.model_copy(update={"discovery": config.discovery.model_copy(update={"max_candidates": 1})})
    monkeypatch.setattr(discovery_module, "get_config", lambda: config)

    class DoneAI:
        provider_name = "quality-discovery-done-fixture"
        model = "fixture-v1"

        async def complete(self, request):
            data = {
                "page_type": "home",
                "features": [],
                "candidate_ids": [],
                "done": True,
                "reason_summary": "No remaining actions are meaningful.",
            }
            return AICompletionResponse(
                content=json.dumps(data),
                structured_data=data,
                provider=self.provider_name,
                model=self.model,
                input_tokens=10,
                output_tokens=5,
            )

    runtime = DiscoveryFixtureBrowserRuntime()
    discovery = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime,
        decisions=DecisionService(),
        provider_factory=DoneAI,
    )
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: discovery
    try:
        project = await client.post(
            "/api/projects", json={"name": "Discovery Candidate Batches", "bootstrap_workspace": False}
        )
        assert project.status_code == 201, project.text
        created = await client.post(
            "/api/discovery/runs",
            json={"project_id": project.json()["id"], "start_url": "http://shop.example.test/", "mode": "EXPLORE"},
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        for _ in range(400):
            response = await client.get(f"/api/discovery/runs/{run_id}")
            assert response.status_code == 200, response.text
            run = response.json()
            if run["status"] in QualityDiscoveryService.TERMINAL:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Quality Discovery did not finish batching skipped candidates")
        task = discovery._tasks.get(run_id)
        if task is not None:
            await task

        frontier = run["result"]["frontier"]
        assert run["status"] == DiscoveryStatus.COMPLETED.value
        assert {item["target"] for item in frontier} == {"Search", "Products", "Cart"}
        assert len(frontier) == 3
        assert all(item["status"] == "SKIPPED" for item in frontier)
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


def test_requirement_analysis_chunks_preserve_context_and_bound_criteria_per_call():
    text = "\n".join(
        [
            "Product search and cart",
            "A shopper searches for products and reviews cart contents.",
            "AC-001: Search results match the product name.",
            "AC-002: Search ignores letter case.",
            "AC-003: A shopper can select a color and size.",
            "AC-004: The cart shows the selected variant.",
            "AC-005: No matches show an empty state.",
        ]
    )

    chunks = QualityDiscoveryService._requirement_analysis_chunks(text)

    assert len(chunks) == 3
    assert all("Product search and cart" in chunk for chunk in chunks)
    assert all(len(re.findall(r"(?m)^AC-\d+:", chunk)) <= 2 for chunk in chunks)
    assert [line for chunk in chunks for line in chunk.splitlines() if line.startswith("AC-")] == [
        line for line in text.splitlines() if line.startswith("AC-")
    ]


def test_explicit_empty_state_and_repeat_merge_criteria_do_not_need_literal_copy_or_quantity():
    empty_state = "AC-005: 无匹配商品时显示明确空状态，无商品卡片。"
    repeated_variant = "AC-006: 重复加入相同规格时合并数量，重新计算金额。"
    amount_rule = "AC-004: 购物车金额符合商品价格乘数量。"

    assert QualityDiscoveryService._is_explicit_acceptance_criterion(empty_state)
    assert QualityDiscoveryService._is_explicit_acceptance_criterion(repeated_variant, amount_rule)
    assert not QualityDiscoveryService._is_explicit_acceptance_criterion(repeated_variant)


@pytest.mark.asyncio
async def test_requirement_analysis_corrects_only_explicit_criterion_ambiguity(monkeypatch):
    criteria = [
        "AC-004: 购物车金额符合商品价格乘数量。",
        "AC-005: 无匹配商品时显示明确空状态，无商品卡片。",
        "AC-006: 重复加入相同规格时合并数量，重新计算金额。",
    ]

    class FixtureProvider:
        async def complete(self, request):
            chunk = json.loads(request.prompt)["text"]
            chunk_criteria = [line for line in chunk.splitlines() if line.startswith("AC-")]
            payload = {
                "requirements": [
                    {
                        "feature": f"Feature {criterion[:6]}",
                        "expected_behavior": criterion,
                        "acceptance_criteria": [criterion],
                        "checks": [],
                        "risk": "medium",
                        "ambiguous": True,
                    }
                    for criterion in chunk_criteria
                ],
                "ambiguities": [f"{criterion[:6]}: missing a literal expected value." for criterion in chunk_criteria],
            }
            return AICompletionResponse(
                content=json.dumps(payload),
                structured_data=payload,
                provider="fixture",
                model="fixture-v1",
                input_tokens=20,
                output_tokens=10,
            )

    service = QualityDiscoveryService(
        None,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        provider_factory=FixtureProvider,
    )

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_record_ai", noop)
    monkeypatch.setattr(service, "_event", noop)
    result = await service._analyze_requirements(
        "run-fixture",
        {
            "source_id": "req-fixture",
            "text": "购物车金额以商品价格乘数量计算。\n" + "\n".join(criteria),
        },
    )

    by_criterion = {
        item["acceptance_criteria"][0][:6]: item for item in result["requirements"] if item["acceptance_criteria"]
    }
    assert by_criterion["AC-005"]["ambiguous"] is False
    assert by_criterion["AC-006"]["ambiguous"] is False
    assert by_criterion["AC-004"]["ambiguous"] is True
    assert all(not item.startswith(("AC-005", "AC-006")) for item in result["ambiguities"])


def test_deepseek_quality_discovery_disables_reasoning_token_mode(monkeypatch):
    monkeypatch.setattr(
        discovery_module,
        "get_config",
        lambda: SimpleNamespace(ai=SimpleNamespace(model="deepseek-flash")),
    )

    assert QualityDiscoveryService._provider_thinking_mode() == "disabled"

    monkeypatch.setattr(
        discovery_module,
        "get_config",
        lambda: SimpleNamespace(ai=SimpleNamespace(model="gpt-4o-mini")),
    )
    assert QualityDiscoveryService._provider_thinking_mode() is None


@pytest.mark.asyncio
async def test_requirement_checks_stay_in_discovery_model_not_shared_requirement_contract(monkeypatch):
    payload = {
        "requirements": [
            {
                "feature": "Search",
                "expected_behavior": "Matching results are displayed.",
                "acceptance_criteria": ["AC-001: Matching results are displayed."],
                "checks": [
                    {
                        "target": "Search results",
                        "attribute": "visible",
                        "expected": True,
                        "when": "after_action",
                        "criterion": "AC-001: Matching results are displayed.",
                    }
                ],
                "risk": "medium",
                "ambiguous": False,
            }
        ],
        "ambiguities": [],
    }

    class FixtureProvider:
        async def complete(self, _request):
            return AICompletionResponse(
                content=json.dumps(payload),
                structured_data=payload,
                provider="fixture",
                model="fixture-v1",
                input_tokens=20,
                output_tokens=10,
            )

    service = QualityDiscoveryService(
        None, browser_runtime=DiscoveryFixtureBrowserRuntime(), provider_factory=FixtureProvider
    )

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_record_ai", noop)
    monkeypatch.setattr(service, "_event", noop)
    result = await service._analyze_requirements(
        "run-fixture", {"source_id": "req-fixture", "text": "AC-001: Matching results are displayed."}
    )

    assert result["requirements"][0]["checks"][0]["target"] == "Search results"
    assert result["requirement_model"]["features"][0]["feature"] == "Search"
    assert "checks" not in result["requirement_model"]["features"][0]


@pytest.mark.asyncio
async def test_quality_map_golden_compares_requirements_tests_automation_and_latest_runs(test_db_session):
    requirements_fixture = json.loads((FIXTURE_DIR / "requirements.json").read_text(encoding="utf-8"))
    coverage_fixture = json.loads((FIXTURE_DIR / "coverage.json").read_text(encoding="utf-8"))
    project_id = f"project-{uuid4().hex[:12]}"
    requirement_ids = {
        item["feature"]: f"req-{item['feature'].lower().replace(' ', '-')}-{uuid4().hex[:5]}"
        for item in requirements_fixture["requirements"]
    }
    now = utc_now()
    requirements = [
        RequirementORM(
            id=requirement_ids[item["feature"]],
            project_id=project_id,
            title=item["feature"],
            description=item["expected_behavior"],
            acceptance_criteria="\n".join(item["acceptance_criteria"]),
            created_at=now,
            updated_at=now,
        )
        for item in requirements_fixture["requirements"]
    ]
    feature_names = ["Search", "Filter", "Sort", "Product detail", "Cart", "Checkout", "Wishlist"]
    structured_requirements = [
        {
            **item,
            "id": f"{requirement_ids[item['feature']]}:REQ-{index:03d}",
            "source_id": requirement_ids[item["feature"]],
        }
        for index, item in enumerate(requirements_fixture["requirements"], start=1)
    ]
    features = []
    for name in feature_names:
        feature_id = f"feature-{name.lower().replace(' ', '-')}"
        features.append(
            {
                "feature_id": feature_id,
                "name": name,
                "description": name,
                "status": "VERIFIED" if name in {"Search", "Wishlist"} else "OBSERVED",
                "evidence_ids": [f"evidence-{name.lower().replace(' ', '-')}"],
                "state_ids": [],
                "requirement_ids": [],
                "target_ids": [],
                "mapping_confidence": 0,
                "mapping_status": "UNMAPPED",
            }
        )
    case_ids = {item["feature"]: f"case-{item['feature'].lower()}" for item in coverage_fixture["test_cases"]}
    test_cases = [
        _TestCaseORM(
            id=case_ids[item["feature"]],
            project_id=project_id,
            requirement_id=requirement_ids[item["feature"]],
            title=item["title"],
            preconditions="",
            steps=["Run the controlled fixture scenario"],
            expected_result="Feature behavior is correct",
            priority="P1",
            automation_status="AUTOMATED",
            tags=[item["feature"]],
            created_at=now,
            updated_at=now,
        )
        for item in coverage_fixture["test_cases"]
    ]
    bindings = [
        AutomationBindingORM(
            id=f"binding-{item['feature'].lower()}",
            test_case_id=case_ids[item["feature"]],
            workspace_id="fixture-workspace",
            nodeid=item["nodeid"],
            file_path="tests/test_shop.py",
            framework="playwright_python",
            status="DRAFT" if item["feature"] == "Checkout" else "ACTIVE",
            created_at=now,
            updated_at=now,
        )
        for item in coverage_fixture["test_cases"]
    ]
    runs = []
    for index, item in enumerate(coverage_fixture["test_cases"], start=1):
        if item["last_run_status"] is None:
            continue
        run_id = f"fixture-run-{item['feature'].lower()}"
        runs.append(
            _TestRunORM(
                id=run_id,
                project_id=project_id,
                workspace_id="fixture-workspace",
                status="COMPLETED",
                requested_by="golden-fixture",
                runner_type="LOCAL",
                environment={},
                browser="chromium",
                parallel_workers=1,
                markers=[],
                nodeids=[item["nodeid"]],
                total=1,
                passed=int(item["last_run_status"] == "PASSED"),
                failed=int(item["last_run_status"] == "FAILED"),
                skipped=0,
                cancelled=0,
                duration_ms=10,
                created_at=now.replace(microsecond=min(999999, now.microsecond + index)),
                executions=[
                    _TestExecutionORM(
                        id=f"execution-{item['feature'].lower()}",
                        nodeid=item["nodeid"],
                        status=item["last_run_status"],
                        duration_ms=10,
                        retry_count=0,
                        artifact_paths=[],
                    )
                ],
            )
        )

    extra_filter_cases = [
        {
            "id": "case-filter-later-failure",
            "title": "Filter handles an empty result set",
            "nodeid": "tests/test_filter.py::test_filter_empty_results",
            "status": "FAILED",
            "run_id": "fixture-run-filter-later-failure",
            "created_at": now + timedelta(seconds=1),
        },
        {
            "id": "case-filter-latest-pass",
            "title": "Filter can be cleared",
            "nodeid": "tests/test_filter.py::test_filter_can_be_cleared",
            "status": "PASSED",
            "run_id": "fixture-run-filter-latest-pass",
            "created_at": now + timedelta(seconds=2),
        },
    ]
    for item in extra_filter_cases:
        test_cases.append(
            _TestCaseORM(
                id=item["id"],
                project_id=project_id,
                requirement_id=requirement_ids["Filter"],
                title=item["title"],
                preconditions="",
                steps=["Run the controlled filter scenario"],
                expected_result="Filter behavior matches the selected criteria.",
                priority="P1",
                automation_status="AUTOMATED",
                tags=["Filter"],
                created_at=item["created_at"],
                updated_at=item["created_at"],
            )
        )
        bindings.append(
            AutomationBindingORM(
                id=f"binding-{item['id']}",
                test_case_id=item["id"],
                workspace_id="fixture-workspace",
                nodeid=item["nodeid"],
                file_path="tests/test_filter.py",
                framework="playwright_python",
                status="ACTIVE",
                created_at=item["created_at"],
                updated_at=item["created_at"],
            )
        )
        runs.append(
            _TestRunORM(
                id=item["run_id"],
                project_id=project_id,
                workspace_id="fixture-workspace",
                status="COMPLETED",
                requested_by="golden-fixture",
                runner_type="LOCAL",
                environment={},
                browser="chromium",
                parallel_workers=1,
                markers=[],
                nodeids=[item["nodeid"]],
                total=1,
                passed=int(item["status"] == "PASSED"),
                failed=int(item["status"] == "FAILED"),
                skipped=0,
                cancelled=0,
                duration_ms=10,
                created_at=item["created_at"],
                executions=[
                    _TestExecutionORM(
                        id=f"execution-{item['id']}",
                        nodeid=item["nodeid"],
                        status=item["status"],
                        duration_ms=10,
                        retry_count=0,
                        artifact_paths=[],
                    )
                ],
            )
        )

    for run in runs:
        run.browser_sessions = [
            BrowserSessionORM(
                id=f"browser-{uuid4().hex[:12]}",
                case_execution_id=execution.id,
                browser_session_id=f"session-{uuid4().hex[:12]}",
                page_id=f"page-{uuid4().hex[:12]}",
                nodeid=execution.nodeid,
                current_url="http://127.0.0.1:1/",
                status="closed",
            )
            for execution in run.executions
        ]

    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Quality Discovery Map Golden",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(requirements + test_cases + bindings + runs)
        discovery = QualityDiscoveryRunORM(
            id=f"qd-{uuid4().hex[:12]}",
            project_id=project_id,
            requested_by="golden-fixture",
            mode="AUDIT",
            start_url="http://127.0.0.1:1/",
            requirement_id=None,
            requirement_text="",
            allowed_domains=["127.0.0.1"],
            status="COMPLETED",
            progress={},
            result={
                "requirements": structured_requirements,
                "states": [
                    {
                        "state_id": "state-search-form",
                        "main_content": "Search products",
                        "controls": [
                            {"name": "Search", "tag": "button", "enabled": True, "selected": False, "checked": False}
                        ],
                    },
                    {
                        "state_id": "state-search-results",
                        "evidence_id": "evidence-search-ui",
                        "main_content": "Search results for qa sample",
                        "controls": [],
                    },
                ],
                "edges": [
                    {
                        "from_state_id": "state-search-form",
                        "to_state_id": "state-search-results",
                        "action": "search",
                        "label": "Search",
                    }
                ],
                "actions": [{"status": "FAILED", "target": "Filter"}],
                "features": features,
                "gaps": [],
                "coverage": [],
            },
            created_at=now,
            updated_at=now,
        )
        session.add(discovery)
        await session.commit()
        run_id = discovery.id

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    await service._build_quality_map(run_id)
    mapped = await service.get(run_id)
    result = mapped.result
    actual_requirements = {item["feature"]: item["status"] for item in result["requirements"]}
    actual_features = {item["name"]: item for item in result["features"]}
    expected = coverage_fixture["expected"]

    for feature_name in ("Search", "Filter", "Sort", "Checkout", "Size Guide"):
        assert actual_requirements[feature_name] == expected[feature_name]["requirement"]
    assert actual_features["Search"]["coverage_status"] == expected["Search"]["coverage"]
    assert actual_features["Filter"]["coverage_status"] == expected["Filter"]["coverage"]
    filter_coverage = next(
        item for item in result["coverage"] if item["feature_id"] == actual_features["Filter"]["feature_id"]
    )
    assert filter_coverage["last_run_status"] == "PASSED"
    assert filter_coverage["last_run_id"] == "fixture-run-filter-latest-pass"
    assert actual_features["Sort"]["coverage_status"] == expected["Sort"]["coverage"]
    assert actual_features["Checkout"]["coverage_status"] == expected["Checkout"]["coverage"]
    assert any(
        gap["category"] == "AUTOMATION_MISSING" and gap["item_id"] == actual_features["Checkout"]["feature_id"]
        for gap in result["gaps"]
    )
    assert actual_features["Wishlist"]["mapping_status"] == expected["Wishlist"]["requirement"]
    assert any(
        gap["category"] == "FUNCTION_BROKEN" and gap["item_id"] == requirement_ids["Filter"] + ":REQ-002"
        for gap in result["gaps"]
    )
    broken_gap = next(
        gap
        for gap in result["gaps"]
        if gap["category"] == "FUNCTION_BROKEN" and gap["item_id"] == requirement_ids["Filter"] + ":REQ-002"
    )
    assert broken_gap["requirement"] == "Filter"
    assert broken_gap["expected"]
    assert broken_gap["observed"]
    failing_gap = next(
        gap
        for gap in result["gaps"]
        if gap["category"] == "AUTOMATION_FAILING" and gap["item_id"] == actual_features["Filter"]["feature_id"]
    )
    failure_action = await service.act_on_gap(run_id, failing_gap["id"], "open_failure")
    assert failure_action["run_id"] == "fixture-run-filter-later-failure"
    assert failure_action["automation"]["test_case_id"] == "case-filter-later-failure"
    quality_map_broken_gap = next(gap for gap in result["quality_map"]["gaps"] if gap["id"] == broken_gap["id"])
    assert quality_map_broken_gap["requirement"] == "Filter"
    assert quality_map_broken_gap["expected"]
    assert quality_map_broken_gap["observed"]
    assert any(
        gap["category"] == "IMPLEMENTATION_MISSING" and gap["item_id"].startswith(requirement_ids["Size Guide"])
        for gap in result["gaps"]
    )
    sort_gaps = {gap["category"] for gap in result["gaps"] if gap["item_id"] == actual_features["Sort"]["feature_id"]}
    assert set(expected["Sort"]["gaps"]).issubset(sort_gaps)
    assert any(
        gap["category"] == "UNDOCUMENTED_FEATURE" and gap["item_id"] == actual_features["Wishlist"]["feature_id"]
        for gap in result["gaps"]
    )
    wishlist_gap = next(
        gap
        for gap in result["gaps"]
        if gap["category"] == "UNDOCUMENTED_FEATURE" and gap["item_id"] == actual_features["Wishlist"]["feature_id"]
    )
    assert wishlist_gap["requirement"] is None
    assert wishlist_gap["observed"]


@pytest.mark.asyncio
async def test_gap_action_lock_serializes_calls_and_releases_entries_after_cancellation(test_db_session):
    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    key = ("run-lock-test", "gap-lock-test", "generate_tests")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock():
        async with service._gap_action_lock(key):
            entered.set()
            await release.wait()

    async def wait_for_lock():
        async with service._gap_action_lock(key):
            pytest.fail("Cancelled waiter must not acquire the action lock.")

    holder = asyncio.create_task(hold_lock())
    await entered.wait()
    waiter = asyncio.create_task(wait_for_lock())
    await asyncio.sleep(0)
    assert service._gap_action_locks[key].users == 2
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert service._gap_action_locks[key].users == 1
    release.set()
    await holder
    assert key not in service._gap_action_locks

    active = 0
    peak_active = 0

    async def run_same_action():
        nonlocal active, peak_active
        async with service._gap_action_lock(key):
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0.001)
            active -= 1

    await asyncio.gather(*(run_same_action() for _ in range(12)))
    assert peak_active == 1
    assert service._gap_action_locks == {}


def test_discovery_domain_policy_blocks_unsafe_external_and_disabled_actions():
    with pytest.raises(ValueError):
        DiscoveryRunCreate(project_id="project", start_url="https://shop.example.test/?access_token=hidden")
    with pytest.raises(ValueError):
        DiscoveryRunCreate(project_id="project", start_url="https://shop.example.test/?state=secret#checkout")
    assert (
        QualityDiscoveryService._safe_url("https://shop.example.test/search?state=secret#checkout")
        == "https://shop.example.test/search"
    )
    assert (
        QualityDiscoveryService._safe_url("https://user:password@shop.example.test/search")
        == "https://shop.example.test/search"
    )
    assert "state=secret" not in QualityDiscoveryService._safe_error(
        RuntimeError("failed at https://shop.example.test/search?state=secret#checkout")
    )
    assert not QualityDiscoveryService._host_allowed("https://outside.example.test/", {"shop.example.test"})
    assert not QualityDiscoveryService._host_allowed("https://user:password@shop.example.test/", {"shop.example.test"})
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    candidates = service._candidate_actions(
        {
            "state_id": "state-start",
            "controls": [
                {
                    "index": 0,
                    "name": "Delete account",
                    "tag": "button",
                    "role": "button",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "index": 1,
                    "name": "External help",
                    "tag": "a",
                    "role": "link",
                    "href": "https://outside.example.test/help",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "index": 2,
                    "name": "Disabled Filter",
                    "tag": "button",
                    "role": "button",
                    "visible": True,
                    "enabled": False,
                },
                {
                    "index": 3,
                    "name": "Help",
                    "tag": "a",
                    "role": "link",
                    "href": "/help",
                    "visible": True,
                    "enabled": True,
                },
            ],
            "scroll": {"height": 500, "viewport": 720},
        },
        {"shop.example.test"},
        5,
    )
    assert [item["target"] for item in candidates] == ["Help"]
    assert candidates[0]["expected_effect"] == "打开站内链接“Help”，检查目标页面标题、内容或状态。"
    assert (
        service._candidate_actions(
            {"state_id": "deep", "controls": [], "scroll": {"height": 1600, "viewport": 720}},
            {"shop.example.test"},
            5,
            depth_limited=True,
        )
        == []
    )
    assert (
        QualityDiscoveryService._state_depth(
            {
                "states": [{"state_id": "root", "depth": 0}, {"state_id": "child", "depth": 1}],
                "edges": [
                    {"from_state_id": "root", "to_state_id": "child"},
                    {"from_state_id": "child", "to_state_id": "root"},
                ],
            },
            "root",
        )
        == 0
    )


def test_search_navigation_link_is_not_treated_as_a_submitted_query():
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    candidates = service._candidate_actions(
        {
            "state_id": "home",
            "url": "https://shop.example.test/",
            "controls": [
                {"index": 0, "name": "Search", "tag": "a", "role": "link", "href": "/search", "enabled": True}
            ],
            "scroll": {"height": 500, "viewport": 720},
        },
        {"shop.example.test"},
        5,
    )

    assert len(candidates) == 1
    assert candidates[0]["action_type"] == "click"
    assert candidates[0]["target"] == "Search"


def test_candidate_expected_effects_describe_observable_outcomes():
    expected = QualityDiscoveryService._candidate_expected_effect

    assert expected("search", "Search products", {}) == "提交安全搜索词，观察匹配商品列表或无匹配空状态。"
    assert "筛选状态变化" in expected("filter", "Category filter", {})
    assert "控件选中状态" in expected("select", "Size", {})
    assert "数量和金额" in expected("click", "Shopping bag", {})
    assert "商品详情" in expected("click", "View product", {})
    assert "加入购物车" in expected("click", "Add to cart", {})


def test_discovery_selects_a_new_option_and_suppresses_repeated_search():
    value = QualityDiscoveryService._safe_select_value
    assert (
        QualityDiscoveryService._safe_search_value(
            {"controls": [{"name": "View Everyday Tee"}, {"name": "Search products"}]}
        )
        == "Everyday Tee"
    )
    assert QualityDiscoveryService._safe_search_value({"controls": [{"name": "Search products"}]}) == "qa sample"
    assert (
        value(
            {
                "value": "navy",
                "options": [
                    {"value": "navy", "enabled": True},
                    {"value": "white", "enabled": True},
                ],
            }
        )
        == "white"
    )
    assert (
        value({"value": "", "options": [{"value": "", "enabled": True}, {"value": "small", "enabled": True}]})
        == "small"
    )
    assert value({"value": "only", "options": [{"value": "only", "enabled": True}]}) == ""

    candidates = [
        {"candidate_id": "search", "action_type": "search"},
        {"candidate_id": "details", "action_type": "click"},
    ]
    assert QualityDiscoveryService._filter_repeated_search_candidates(candidates, []) == candidates
    assert QualityDiscoveryService._filter_repeated_search_candidates(
        candidates, [{"action_type": "search", "status": "EXECUTED"}]
    ) == [candidates[1]]
    assert QualityDiscoveryService._filter_repeated_search_candidates(
        [
            {"candidate_id": "positive", "action_type": "search", "value": "Everyday Tee"},
            {"candidate_id": "negative", "action_type": "search", "value": "zzqa-no-matching-item"},
            candidates[1],
        ],
        [{"action_type": "search", "status": "EXECUTED", "search_value": "Everyday Tee"}],
    ) == [
        {"candidate_id": "negative", "action_type": "search", "value": "zzqa-no-matching-item"},
        candidates[1],
    ]

    select_candidates = [
        {"candidate_id": "color", "action_type": "select", "target": "Color"},
        {"candidate_id": "size", "action_type": "select", "target": "Size"},
        {"candidate_id": "back", "action_type": "click", "target": "Back to products"},
    ]
    filtered = QualityDiscoveryService._filter_repeated_select_candidates(
        select_candidates,
        [{"action_type": "select", "target": "Color", "status": "EXECUTED", "from_state_id": "detail"}],
        [{"state_id": "detail", "url": "https://shop.example.test/products/tee"}],
        {"url": "https://shop.example.test/products/tee"},
    )
    assert filtered == select_candidates[1:]


def test_active_discovery_goal_includes_its_linked_requirement_context():
    goal = QualityDiscoveryService._active_goal_context(
        {
            "goals": [
                {
                    "title": "Open a matching product",
                    "feature": "Product detail",
                    "priority": "HIGH",
                    "rationale": "Needed before variant selection.",
                    "requirement_id": "req-1:REQ-002",
                }
            ]
        },
        [
            {
                "id": "req-1:REQ-002",
                "feature": "Product detail",
                "expected_behavior": "Show product name and price.",
                "acceptance_criteria": ["AC-002: Show product name and price."],
            }
        ],
    )

    assert goal == {
        "title": "Open a matching product",
        "feature": "Product detail",
        "priority": "HIGH",
        "rationale": "Needed before variant selection.",
        "requirement_id": "req-1:REQ-002",
        "expected_behavior": "Show product name and price.",
        "acceptance_criteria": ["AC-002: Show product name and price."],
    }
    assert QualityDiscoveryService._active_goal_context({"goals": []}, []) is None


def test_search_value_follows_active_requirement_and_avoids_repeating_queries():
    requirements = [
        {
            "id": "req-1:REQ-001",
            "expected_behavior": "Show only matching products.",
            "acceptance_criteria": ["AC-001: Search by product name."],
        },
        {
            "id": "req-1:REQ-006",
            "expected_behavior": "Show an empty state when no products match.",
            "acceptance_criteria": ["AC-005: Show a no-match empty state."],
        },
    ]
    state = {"controls": [{"name": "Search products"}]}

    no_match_value = QualityDiscoveryService._search_value_for_goal(
        state,
        {"goals": [{"title": "Verify no-match empty state", "requirement_id": "req-1:REQ-006"}]},
        requirements,
        [{"action_type": "search", "status": "EXECUTED", "search_value": "Everyday Tee"}],
        [{"controls": [{"name": "View Everyday Tee"}]}],
    )
    matching_value = QualityDiscoveryService._search_value_for_goal(
        state,
        {"goals": [{"title": "Open matching product", "requirement_id": "req-1:REQ-002"}]},
        requirements,
        [{"action_type": "search", "status": "EXECUTED", "search_value": "zzqa-no-matching-item"}],
        [{"controls": [{"name": "View Everyday Tee"}]}],
    )

    assert no_match_value == "zzqa-no-matching-item"
    assert matching_value == "Everyday Tee"

    case_insensitive_value = QualityDiscoveryService._search_value_for_goal(
        {"controls": [{"name": "View Everyday Tee"}]},
        {"goals": [{"title": "Search and ignore case", "requirement_id": "req-1:REQ-001"}]},
        requirements,
        [],
        [],
    )
    assert case_insensitive_value == "everyday tee"


def test_active_goal_advances_to_uncovered_search_scenario():
    plan = {
        "goals": [
            {"title": "Search a matching product", "requirement_id": "req-1:REQ-001"},
            {"title": "Verify no-match empty state", "requirement_id": "req-1:REQ-006"},
            {"title": "Open product details", "requirement_id": "req-1:REQ-002"},
        ]
    }
    requirements = [
        {"id": "req-1:REQ-001", "expected_behavior": "Show matching product."},
        {"id": "req-1:REQ-006", "expected_behavior": "Show empty state if no products match."},
        {"id": "req-1:REQ-002", "expected_behavior": "Show product details."},
    ]
    positive_search = [{"action_type": "search", "status": "EXECUTED", "search_value": "everyday tee"}]
    both_searches = positive_search + [
        {"action_type": "search", "status": "EXECUTED", "search_value": "zzqa-no-matching-item"}
    ]

    assert QualityDiscoveryService._active_goal_context(plan, requirements, positive_search)["requirement_id"] == (
        "req-1:REQ-006"
    )
    assert QualityDiscoveryService._active_goal_context(plan, requirements, both_searches)["requirement_id"] == (
        "req-1:REQ-002"
    )


def test_discovery_collapses_duplicate_search_trigger_and_allows_read_only_cart_view():
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    candidates = service._candidate_actions(
        {
            "state_id": "listing",
            "controls": [
                {"index": 0, "name": "Cart (0)", "tag": "button", "role": "button", "enabled": True},
                {"index": 1, "name": "Search products", "tag": "input", "type": "text", "role": "textbox"},
                {"index": 2, "name": "Search", "tag": "button", "role": "button"},
                {"index": 3, "name": "View Everyday Tee", "tag": "button", "role": "button"},
            ],
            "scroll": {"height": 500, "viewport": 720},
        },
        {"shop.example.test"},
        5,
    )

    assert [item["target"] for item in candidates] == ["Cart (0)", "Search products", "View Everyday Tee"]
    assert candidates[0]["risk"] == "READ_ONLY"
    assert candidates[0]["expected_effect"] == "打开购物车，检查商品条目、数量和金额。"
    assert [item["action_type"] for item in candidates].count("search") == 1
    assert next(item for item in candidates if item["action_type"] == "search")["value"] == "Everyday Tee"

    cart_candidates = service._candidate_actions(
        {
            "state_id": "cart",
            "title": "Northstar · Demo Shop",
            "main_content": "Shopping cart Your cart is empty. Total: $0.00 Continue shopping",
            "controls": [
                {"index": 0, "name": "Cart (0)", "tag": "button", "role": "button", "enabled": True},
                {"index": 1, "name": "Continue shopping", "tag": "button", "role": "button", "enabled": True},
            ],
            "scroll": {"height": 500, "viewport": 720},
        },
        {"shop.example.test"},
        5,
    )
    assert [item["target"] for item in cart_candidates] == ["Continue shopping"]


def test_cart_mutation_requires_explicit_requirement_intent_and_never_unblocks_purchase():
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    state = {
        "state_id": "product-detail",
        "controls": [
            {"index": 0, "name": "Add to cart", "tag": "button", "role": "button", "enabled": True},
            {"index": 1, "name": "Place order", "tag": "button", "role": "button", "enabled": True},
            {"index": 2, "name": "Delete account", "tag": "button", "role": "button", "enabled": True},
        ],
        "scroll": {"height": 500, "viewport": 720},
    }

    explore_candidates = service._candidate_actions(state, {"shop.example.test"}, 5)
    assert explore_candidates == []
    assert {item["target"] for item in service._blocked_candidates(state, {"shop.example.test"})} == {
        "Add to cart",
        "Place order",
        "Delete account",
    }

    assert service._requirement_allows_cart_mutation("购买流程：将所选商品加入购物车并检查数量")
    assert service._requirement_allows_cart_mutation("Add the selected product to cart")
    assert not service._requirement_allows_cart_mutation("Review the product details")
    validate_candidates = service._candidate_actions(state, {"shop.example.test"}, 5, allow_cart_mutation=True)
    assert [item["target"] for item in validate_candidates] == ["Add to cart"]
    assert validate_candidates[0]["risk"] == "SAFE_INTERACTION"
    assert {
        item["target"] for item in service._blocked_candidates(state, {"shop.example.test"}, allow_cart_mutation=True)
    } == {"Place order", "Delete account"}


def test_cart_mutation_waits_for_ordered_variant_selection():
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    state = {
        "state_id": "detail-default",
        "url": "https://shop.example.test/products/tee",
        "controls": [
            {
                "index": 0,
                "name": "Color",
                "tag": "select",
                "role": "combobox",
                "value": "Navy",
                "options": [{"value": "Navy", "enabled": True}, {"value": "White", "enabled": True}],
            },
            {
                "index": 1,
                "name": "Size",
                "tag": "select",
                "role": "combobox",
                "value": "S",
                "options": [{"value": "S", "enabled": True}, {"value": "M", "enabled": True}],
            },
            {"index": 2, "name": "Cart (0)", "tag": "button", "role": "button", "enabled": True},
            {"index": 3, "name": "Back to products", "tag": "button", "role": "button", "enabled": True},
            {"index": 4, "name": "Add to cart", "tag": "button", "role": "button", "enabled": True},
        ],
        "scroll": {"height": 500, "viewport": 720},
    }
    candidates = service._candidate_actions(state, {"shop.example.test"}, 5, allow_cart_mutation=True)
    states = [{"state_id": "detail-default", "url": state["url"]}]

    assert [item["target"] for item in candidates] == ["Color", "Size", "Cart (0)", "Back to products", "Add to cart"]
    assert [
        item["target"] for item in service._prioritize_variant_actions_before_cart(candidates, [], states, state)
    ] == ["Color"]

    color_selected = [
        {"action_type": "select", "target": "Color", "status": "EXECUTED", "from_state_id": "detail-default"}
    ]
    assert [
        item["target"]
        for item in service._prioritize_variant_actions_before_cart(candidates, color_selected, states, state)
    ] == ["Size"]

    both_selected = color_selected + [
        {"action_type": "select", "target": "Size", "status": "EXECUTED", "from_state_id": "detail-default"}
    ]
    assert service._prioritize_variant_actions_before_cart(candidates, both_selected, states, state) == candidates

    fixed_option_state = {
        **state,
        "controls": [
            {
                "index": 0,
                "name": "Size",
                "tag": "select",
                "role": "combobox",
                "value": "One size",
                "options": [{"value": "One size", "enabled": True}],
            },
            state["controls"][2],
            state["controls"][4],
        ],
    }
    fixed_option_candidates = service._candidate_actions(
        fixed_option_state, {"shop.example.test"}, 5, allow_cart_mutation=True
    )
    assert [
        item["target"]
        for item in service._prioritize_variant_actions_before_cart(
            fixed_option_candidates, [], states, fixed_option_state
        )
    ] == ["Cart (0)", "Add to cart"]


def test_cart_add_allows_one_explicit_same_variant_repeat_then_requires_verification():
    candidates = [
        {"candidate_id": "cart", "action_type": "click", "target": "Cart (1)"},
        {"candidate_id": "back", "action_type": "click", "target": "Back to products"},
        {
            "candidate_id": "add",
            "action_type": "click",
            "target": "Add to cart",
            "cart_variant_key": "white-m",
        },
    ]
    actions = [
        {
            "action_type": "click",
            "target": "Add to cart",
            "status": "EXECUTED",
            "cart_variant_key": "white-m",
            "finished_at": "2026-10-10T04:00:00+00:00",
        }
    ]

    verify_first_add = QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates,
        {"page_type": "product_detail"},
        actions,
        [],
    )
    assert verify_first_add == [candidates[0]]

    repeat_same_variant = QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates,
        {"page_type": "product_detail"},
        actions,
        [],
        allow_repeat_same_variant=True,
    )
    assert repeat_same_variant == [candidates[2]]

    different_variant = [{**candidates[2], "cart_variant_key": "navy-s"}]
    assert QualityDiscoveryService._prioritize_cart_verification_after_add(
        [candidates[0], *different_variant],
        {"page_type": "product_detail"},
        actions,
        [],
        allow_repeat_same_variant=True,
    ) == [candidates[0]]

    two_adds = [*actions, {**actions[0], "candidate_id": "second-add", "finished_at": "2026-10-10T04:01:00+00:00"}]
    assert QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates,
        {"page_type": "product_detail"},
        two_adds,
        [],
        allow_repeat_same_variant=True,
    ) == [candidates[0]]

    cart_inspected = QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates,
        {"page_type": "product_detail"},
        actions,
        [
            {
                "page_type": "cart",
                "main_content": "Everyday Tee White · M · Quantity: 1 $29.00 Total: $29.00",
                "observed_at": "2026-10-10T04:00:01+00:00",
            }
        ],
        allow_repeat_same_variant=True,
    )
    assert cart_inspected == [candidates[2]]

    after_second_add = QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates,
        {"page_type": "product_detail"},
        two_adds,
        [
            {
                "page_type": "cart",
                "main_content": "Everyday Tee White · M · Quantity: 1 $29.00 Total: $29.00",
                "observed_at": "2026-10-10T04:00:01+00:00",
            }
        ],
        allow_repeat_same_variant=True,
    )
    assert after_second_add == [candidates[0]]

    assert (
        QualityDiscoveryService._prioritize_cart_verification_after_add(
            candidates,
            {"main_content": "Cart (1) Everyday Tee · White · M Added to cart: Everyday Tee · White · M"},
            [],
            [],
        )
        == candidates
    )

    without_cart_view = QualityDiscoveryService._prioritize_cart_verification_after_add(
        candidates[1:],
        {"main_content": "Cart (1) Added to cart: Everyday Tee · White · M"},
        actions,
        [],
    )
    assert without_cart_view == [candidates[1]]


def test_variant_deduplication_is_scoped_to_product_heading_not_only_url():
    url = "https://shop.example.test/product"
    tee = {
        "state_id": "tee",
        "url": url,
        "page_type": "product_detail",
        "landmarks": '- heading "Everyday Tee" [level=1]',
        "controls": [
            {
                "name": "Color",
                "tag": "select",
                "value": "Navy",
                "options": [{"value": "Navy", "enabled": True}, {"value": "White", "enabled": True}],
            },
            {
                "name": "Size",
                "tag": "select",
                "value": "S",
                "options": [{"value": "S", "enabled": True}, {"value": "M", "enabled": True}],
            },
        ],
    }
    tote = {
        "state_id": "tote",
        "url": url,
        "page_type": "product_detail",
        "landmarks": '- heading "Canvas Tote" [level=1]',
        "controls": tee["controls"],
    }
    candidates = [
        {"candidate_id": "color", "action_type": "select", "target": "Color", "value": "White"},
        {"candidate_id": "size", "action_type": "select", "target": "Size", "value": "M"},
    ]
    prior_color = [
        {
            "action_type": "select",
            "target": "Color",
            "selected_value": "White",
            "status": "EXECUTED",
            "from_state_id": "tee",
        }
    ]

    assert (
        QualityDiscoveryService._filter_repeated_select_candidates(candidates, prior_color, [tee, tote], tote)
        == candidates
    )
    assert QualityDiscoveryService._filter_repeated_select_candidates(candidates, prior_color, [tee, tote], tee) == [
        candidates[1]
    ]
    assert [
        item["target"]
        for item in QualityDiscoveryService._prioritize_variant_actions_before_cart(
            [*candidates, {"candidate_id": "add", "action_type": "click", "target": "Add to cart"}],
            prior_color,
            [tee, tote],
            tote,
        )
    ] == ["Color"]


def test_repeat_cart_mutation_requires_same_variant_and_quantity_merge_intent():
    allows_repeat = QualityDiscoveryService._requirement_allows_repeat_cart_mutation

    assert allows_repeat("AC-006: 重复加入相同规格时合并数量并重新计算金额。")
    assert allows_repeat("Add the same variant again and merge quantities.")
    assert not allows_repeat("Add the selected variant to the cart and check it.")
    assert not allows_repeat("Repeatedly add different products to cart.")


def test_feature_is_verified_only_when_executed_transition_state_has_evidence():
    feature = {
        "name": "Add to cart",
        "status": "OBSERVED",
        "target_ids": ["detail:el_3"],
        "evidence_ids": ["before-evidence"],
    }
    state = {"state_id": "cart", "fingerprint": "after-fingerprint", "evidence_id": "after-evidence"}
    result = {
        "features": [feature],
        "actions": [
            {
                "candidate_id": "candidate-add",
                "from_state_id": "detail",
                "target_id": "el_3",
                "status": "EXECUTED",
                "state_changed": True,
                "to_fingerprint": "after-fingerprint",
            }
        ],
    }

    QualityDiscoveryService._verify_features_for_state(result, state)

    assert feature["status"] == "VERIFIED"
    assert feature["verified_by_action_id"] == "candidate-add"
    assert feature["verification_state_ids"] == ["cart"]
    assert feature["verification_action_ids"] == ["candidate-add"]
    assert feature["evidence_ids"] == ["before-evidence", "after-evidence"]

    unchanged = {**feature, "status": "OBSERVED", "verified_by_action_id": None, "verification_state_ids": []}
    result["features"] = [unchanged]
    result["actions"][0]["state_changed"] = False
    QualityDiscoveryService._verify_features_for_state(result, state)
    assert unchanged["status"] == "OBSERVED"


def test_repeat_cart_merge_requirement_uses_fresh_cart_quantity_and_total_evidence():
    requirement = {
        "acceptance_criteria": ["AC-006: 重复加入相同规格时合并数量并重新计算金额。"],
        "checks": [],
    }
    actions = [
        {
            "candidate_id": "add-one",
            "from_state_id": "detail",
            "action_type": "click",
            "target": "Add to cart",
            "cart_variant_key": "white-m",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:00:00+00:00",
        },
        {
            "candidate_id": "add-two",
            "from_state_id": "detail",
            "action_type": "click",
            "target": "Add to cart",
            "cart_variant_key": "white-m",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:01:00+00:00",
        },
    ]
    states = [
        {"state_id": "detail", "page_type": "product_detail", "main_content": "Everyday Tee $29.00"},
        {
            "state_id": "cart-after-two",
            "page_type": "cart",
            "main_content": "Everyday Tee White · M · Quantity: 2 $29.00 Total: $58.00",
            "evidence_id": "cart-evidence",
            "observed_at": "2026-10-10T04:01:02+00:00",
        },
    ]

    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, states, [], actions)

    assert status == "PASS"
    assert results[0]["status"] == "PASS"
    assert results[0]["expected"]["total"] == "58.00"
    assert results[0]["actual"]["quantity"] == 2
    assert results[0]["evidence_id"] == "cart-evidence"

    wrong_total_states = [
        {**states[0]},
        {**states[1], "main_content": "Everyday Tee White · M · Quantity: 2 $29.00 Total: $57.99"},
    ]
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, wrong_total_states, [], actions)
    assert status == "FAIL"
    assert results[0]["status"] == "FAIL"

    before_second_add = [{**states[0]}, {**states[1], "observed_at": "2026-10-10T04:00:30+00:00"}]
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, before_second_add, [], actions)
    assert status == "NOT_VERIFIED"
    assert results[0]["status"] == "NOT_VERIFIED"

    no_cart_evidence = [{**states[0]}, {**states[1], "evidence_id": None}]
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, no_cart_evidence, [], actions)
    assert status == "NOT_VERIFIED"
    assert results[0]["status"] == "NOT_VERIFIED"

    assert QualityDiscoveryService._timestamp_after("2026-10-10T04:01:02", "2026-10-10T04:01:00+00:00")
    assert not QualityDiscoveryService._timestamp_after("invalid", "2026-10-10T04:01:00+00:00")


def test_explicit_shop_criteria_are_evaluated_from_real_state_and_action_evidence():
    criteria = [
        "AC-001: 按商品名称搜索，仅显示匹配商品；忽略大小写。",
        "AC-002: 打开商品详情，显示商品名称、价格与加入购物车按钮。",
        "AC-003: 选择颜色与尺码，加入购物车后保留所选规格。",
        "AC-004: 购物车显示商品、规格、数量，金额符合价格乘数量。",
        "AC-005: 无匹配商品时显示明确空状态，无商品卡片。",
        "AC-006: 重复加入相同规格时合并数量，重新计算金额。",
    ]
    requirement = {"acceptance_criteria": criteria, "checks": []}
    common_detail = {
        "url": "http://127.0.0.1/products/everyday-tee",
        "landmarks": 'heading "Everyday Tee" [level=1]',
        "main_content": "Everyday Tee $29.00 Color White Size M Add to cart",
        "controls": [
            {"name": "Add to cart", "enabled": True},
            {"name": "Color", "tag": "select", "selected": "White"},
            {"name": "Size", "tag": "select", "selected": "M"},
        ],
        "evidence_id": "detail-evidence",
    }
    states = [
        {
            "state_id": "matching-results",
            "fingerprint": "matching-fp",
            "main_content": "Search results for everyday tee. Everyday Tee $29.00",
            "controls": [{"name": "View Everyday Tee", "tag": "button", "enabled": True}],
            "evidence_id": "matching-evidence",
            "observed_at": "2026-10-10T04:00:02+00:00",
        },
        {
            "state_id": "empty-results",
            "fingerprint": "empty-fp",
            "main_content": "No products found. Try another search.",
            "controls": [],
            "evidence_id": "empty-evidence",
            "observed_at": "2026-10-10T04:00:04+00:00",
        },
        {"state_id": "detail-color", **common_detail},
        {"state_id": "detail-size", **common_detail},
        {"state_id": "detail-selected", **common_detail},
        {
            "state_id": "cart-after-adds",
            "fingerprint": "cart-fp",
            "title": "Shopping cart",
            "page_type": "unknown",
            "main_content": "Everyday Tee White · M · Quantity: 2 $58.00 Total: $58.00",
            "controls": [],
            "evidence_id": "cart-evidence",
            "observed_at": "2026-10-10T04:00:20+00:00",
        },
    ]
    actions = [
        {
            "candidate_id": "search-match",
            "action_type": "search",
            "search_value": "everyday tee",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:00:01+00:00",
            "to_fingerprint": "matching-fp",
        },
        {
            "candidate_id": "search-empty",
            "action_type": "search",
            "search_value": "zzqa-no-matching-item",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:00:03+00:00",
            "to_fingerprint": "empty-fp",
        },
        {
            "candidate_id": "select-color",
            "from_state_id": "detail-color",
            "action_type": "select",
            "target": "Color",
            "selected_value": "White",
            "status": "EXECUTED",
        },
        {
            "candidate_id": "select-size",
            "from_state_id": "detail-size",
            "action_type": "select",
            "target": "Size",
            "selected_value": "M",
            "status": "EXECUTED",
        },
        {
            "candidate_id": "add-one",
            "from_state_id": "detail-selected",
            "action_type": "click",
            "target": "Add to cart",
            "cart_variant_key": "white-m",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:00:10+00:00",
        },
        {
            "candidate_id": "add-two",
            "from_state_id": "detail-selected",
            "action_type": "click",
            "target": "Add to cart",
            "cart_variant_key": "white-m",
            "status": "EXECUTED",
            "finished_at": "2026-10-10T04:00:19+00:00",
            "to_fingerprint": "cart-fp",
        },
    ]
    edges = [
        {"candidate_id": "search-match", "to_state_id": "matching-results"},
        {"candidate_id": "search-empty", "to_state_id": "empty-results"},
        {"candidate_id": "add-two", "from_state_id": "detail-selected", "to_state_id": "cart-after-adds"},
    ]

    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, states, edges, actions)

    assert status == "PASS"
    assert {item["check"] for item in results if item.get("status") == "PASS"} == {
        "case_insensitive_product_search",
        "product_detail_purchase_controls",
        "selected_variant_retained_in_cart",
        "cart_amount_matches_price_times_quantity",
        "empty_search_state",
        "same_variant_quantity_merge",
    }
    assert all(item.get("evidence_id") for item in results if item.get("status") == "PASS")
    assert QualityDiscoveryService._all_acceptance_criteria_passed([requirement], states, edges, actions)


def test_shop_criterion_does_not_pass_without_evidence_or_actual_search_results():
    criterion = "AC-001: 按商品名称搜索，仅显示匹配商品；忽略大小写。"
    requirement = {"acceptance_criteria": [criterion], "checks": []}
    action = {
        "candidate_id": "search",
        "action_type": "search",
        "search_value": "everyday tee",
        "status": "EXECUTED",
        "finished_at": "2026-10-10T04:00:01+00:00",
        "to_fingerprint": "results-fp",
    }
    state = {
        "state_id": "results",
        "fingerprint": "results-fp",
        "main_content": "Everyday Tee",
        "controls": [{"name": "View Everyday Tee"}],
        "observed_at": "2026-10-10T04:00:02+00:00",
    }
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, [state], [], [action])
    assert status == "NOT_VERIFIED"
    assert results[0]["status"] == "NOT_VERIFIED"


def test_requirement_check_requires_evidence_reference_for_pass():
    criterion = "“Search results for qa sample” are displayed after submitting the query."
    requirement = {
        "expected_behavior": criterion,
        "acceptance_criteria": [criterion],
        "checks": [
            {
                "target": "Search results for qa sample",
                "attribute": "visible",
                "expected": True,
                "when": "after_action",
                "criterion": criterion,
            }
        ],
    }
    state = {"state_id": "search-results", "main_content": "Search results for qa sample", "controls": []}
    status, results = QualityDiscoveryService._evaluate_requirement_checks(
        requirement,
        [state],
        [{"from_state_id": "search-form", "to_state_id": "search-results", "action": "search"}],
    )
    assert status == "NOT_VERIFIED"
    assert results[0]["status"] == "NOT_VERIFIED"


def test_discovery_uses_observed_in_app_returns_and_never_unverified_browser_back():
    service = QualityDiscoveryService.__new__(QualityDiscoveryService)
    result = {
        "states": [
            {
                "state_id": "listing",
                "url": "https://shop.example.test/",
                "url_navigable": True,
            },
            {
                "state_id": "detail",
                "url": "https://shop.example.test/products/tee",
                "url_navigable": True,
            },
        ],
        "edges": [{"from_state_id": "listing", "to_state_id": "detail"}],
    }

    candidate = service._back_candidate(
        result,
        {"state_id": "detail", "url": "https://shop.example.test/products/tee"},
        {"shop.example.test"},
    )
    assert candidate is not None
    assert candidate["value"] == "https://shop.example.test/"

    same_url = {**result["states"][0], "state_id": "same-url", "url": "https://shop.example.test/"}
    no_history_result = {
        "states": [result["states"][0], same_url],
        "edges": [{"from_state_id": "listing", "to_state_id": "same-url"}],
    }
    assert service._back_candidate(no_history_result, same_url, {"shop.example.test"}) is None

    external_parent = {**result["states"][0], "url": "https://outside.example.test/"}
    external_result = {
        "states": [external_parent, result["states"][1]],
        "edges": [{"from_state_id": "listing", "to_state_id": "detail"}],
    }
    assert (
        service._back_candidate(
            external_result,
            result["states"][1],
            {"shop.example.test"},
        )
        is None
    )


def test_state_fingerprint_tracks_select_and_checked_control_state():
    snapshot = BrowserSnapshot(
        session_id="fixture",
        url="https://shop.example.test/product?state=secret#details",
        title="Product",
        accessibility_tree="Product",
        text="Product",
        controls=[],
        screenshot=None,
        console=[],
        network=[],
    )
    scroll = {"y": 0, "height": 800, "viewport": 720}
    red = QualityDiscoveryService._safe_controls(
        [
            {"tag": "select", "name": "Color", "value": "red", "visible": True, "enabled": True},
            {"tag": "input", "name": "Gift wrap", "checked": False, "visible": True},
        ]
    )
    blue_checked = QualityDiscoveryService._safe_controls(
        [
            {"tag": "select", "name": "Color", "value": "blue", "visible": True, "enabled": True},
            {"tag": "input", "name": "Gift wrap", "checked": True, "visible": True},
        ]
    )
    _, red_fingerprint = QualityDiscoveryService._state_fingerprint(snapshot, red, scroll)
    _, blue_fingerprint = QualityDiscoveryService._state_fingerprint(snapshot, blue_checked, scroll)
    assert red_fingerprint != blue_fingerprint
    assert "state=secret" not in json.dumps(red)
    region_one = QualityDiscoveryService._safe_controls(
        [{"tag": "select", "name": "Region", "value": "north", "visible": True}]
    )
    region_two = QualityDiscoveryService._safe_controls(
        [{"tag": "select", "name": "Region", "value": "south", "visible": True}]
    )
    assert region_one[0]["value"] == region_two[0]["value"] == ""
    assert region_one[0]["selection_fingerprint"] != region_two[0]["selection_fingerprint"]
    _, region_one_fingerprint = QualityDiscoveryService._state_fingerprint(snapshot, region_one, scroll)
    _, region_two_fingerprint = QualityDiscoveryService._state_fingerprint(snapshot, region_two, scroll)
    assert region_one_fingerprint != region_two_fingerprint


@pytest.mark.asyncio
async def test_failed_requirement_check_maps_to_function_broken_with_state_evidence(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    now = utc_now()
    states = []
    for index, cart_enabled in enumerate((False, True), start=1):
        states.append(
            {
                "state_id": f"state-{index}",
                "evidence_id": f"evidence-{index}",
                "controls": [
                    {"name": "Size", "tag": "select", "value": "", "selected": False, "checked": False},
                    {
                        "name": "Add To Cart",
                        "tag": "button",
                        "enabled": cart_enabled,
                        "selected": False,
                        "checked": False,
                    },
                ],
            }
        )
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Requirement Check Golden",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="VALIDATE",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="Add To Cart must be disabled until a size is selected.",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result={
                    "requirements": [
                        {
                            "id": "PASTED:REQ-001",
                            "source_id": "PASTED",
                            "feature": "Add To Cart",
                            "expected_behavior": "Add To Cart must be disabled until a size is selected.",
                            "acceptance_criteria": ["Add To Cart must be disabled until a size is selected."],
                            "checks": [
                                {
                                    "target": "Add To Cart",
                                    "attribute": "enabled",
                                    "expected": False,
                                    "when": "size_unselected",
                                    "criterion": "Add To Cart must be disabled until a size is selected.",
                                }
                            ],
                        }
                    ],
                    "states": states,
                    "edges": [],
                    "actions": [],
                    "features": [],
                    "gaps": [],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    await service._build_quality_map(run_id)
    mapped = await service.get(run_id)
    requirement = mapped.result["requirements"][0]
    assert requirement["status"] == "IMPLEMENTED_BROKEN"
    assert requirement["check_status"] == "FAIL"
    assert [item["actual"] for item in requirement["check_results"][0]["observations"]] == [False, True]
    assert requirement["check_results"][0]["state_id"] == "state-2"
    assert "evidence-2" in requirement["evidence_ids"]
    assert any(
        gap["category"] == "FUNCTION_BROKEN" and gap["item_id"] == "PASTED:REQ-001" for gap in mapped.result["gaps"]
    )


@pytest.mark.asyncio
async def test_resume_requeues_orphaned_running_run_after_service_restart(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    now = utc_now()
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Resume Golden",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="EXPLORE",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="RUNNING",
                progress={},
                result={"states": [], "actions": [], "features": [], "requirements": [], "edges": []},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    executed = asyncio.Event()

    async def resumed(run_to_resume):
        assert run_to_resume == run_id
        executed.set()

    service._execute = resumed
    row = await service.resume(run_id)
    assert row.status == "RUNNING"
    await asyncio.wait_for(executed.wait(), timeout=2)


@pytest.mark.asyncio
async def test_concurrent_discovery_result_updates_preserve_both_changes(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    now = utc_now()
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Concurrent Writes",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="EXPLORE",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="RUNNING",
                progress={},
                result={"events": []},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())

    def append_event(event_id):
        return lambda result: result.setdefault("events", []).append(event_id)

    await asyncio.gather(
        service._change_result(run_id, append_event("first")),
        service._change_result(run_id, append_event("second")),
    )
    row = await service.get(run_id)
    assert set(row.result["events"]) == {"first", "second"}


@pytest.mark.asyncio
async def test_low_confidence_requirement_link_does_not_confirm_test_coverage(test_db_session, monkeypatch):
    from types import SimpleNamespace

    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    requirement_id = f"req-{uuid4().hex[:12]}"
    low_confidence_subitem_id = f"{requirement_id}:REQ-001"
    high_confidence_subitem_id = f"{requirement_id}:REQ-002"
    now = utc_now()
    feature = {
        "feature_id": "feature-search-history",
        "name": "Search history",
        "description": "Recent searches are displayed.",
        "status": "OBSERVED",
        "evidence_ids": ["evidence-search-history"],
        "state_ids": [],
        "requirement_ids": [],
        "target_ids": [],
    }
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Low Confidence Mapping",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            RequirementORM(
                id=requirement_id,
                project_id=project_id,
                title="Search filter history",
                description="Recent search filters are stored.",
                acceptance_criteria="Recent search filters are stored.",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            _TestCaseORM(
                id=f"case-{uuid4().hex[:12]}",
                project_id=project_id,
                requirement_id=requirement_id,
                title="Search filter history persists",
                preconditions="",
                steps=["Search and inspect history"],
                expected_result="Recent filters are stored",
                priority="P1",
                automation_status="MANUAL",
                tags=[],
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result={
                    "requirements": [
                        {
                            "id": low_confidence_subitem_id,
                            "source_id": requirement_id,
                            "feature": "Search filter history",
                            "expected_behavior": "Recent search filters are stored.",
                            "acceptance_criteria": ["Recent search filters are stored."],
                            "checks": [],
                        },
                        {
                            "id": high_confidence_subitem_id,
                            "source_id": requirement_id,
                            "feature": "Search history",
                            "expected_behavior": "Recent searches are displayed.",
                            "acceptance_criteria": ["Recent searches are displayed."],
                            "checks": [],
                        },
                    ],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "features": [feature],
                    "gaps": [],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    monkeypatch.setattr(
        discovery_module,
        "get_config",
        lambda: SimpleNamespace(discovery=SimpleNamespace(feature_mapping_confidence=0.75)),
    )
    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    await service._build_quality_map(run_id)
    mapped = await service.get(run_id)
    actual_feature = mapped.result["features"][0]
    coverage = mapped.result["coverage"][0]

    requirements_by_id = {item["id"]: item for item in mapped.result["requirements"]}
    assert requirements_by_id[low_confidence_subitem_id]["mapping_status"] == "NEEDS_REVIEW"
    assert requirements_by_id[high_confidence_subitem_id]["mapping_status"] == "MAPPED"
    assert actual_feature["mapping_status"] == "MAPPED"
    assert actual_feature["test_case_ids"] == []
    assert actual_feature["test_case_candidates"][0]["mapping_status"] == "NEEDS_REVIEW"
    assert actual_feature["coverage_status"] == "PARTIAL"
    assert coverage["test_status"] == "NEEDS_REVIEW"
    assert any(gap["category"] == "TEST_INCOMPLETE" for gap in mapped.result["gaps"]), mapped.result["gaps"]


@pytest.mark.asyncio
async def test_create_requirement_draft_gap_action_persists_and_is_idempotent(client, test_db_session, monkeypatch):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    feature_id = "feature-wishlist"
    gap_id = "gap-undocumented-feature-wishlist"
    now = utc_now()
    feature = {
        "feature_id": feature_id,
        "name": "Wishlist",
        "description": "Save a product for later.",
        "status": "OBSERVED",
        "trust": "OBSERVED",
        "page_type": "product",
        "evidence_ids": ["evidence-wishlist"],
        "state_ids": ["state-wishlist"],
        "requirement_ids": [],
    }
    gap = {
        "id": gap_id,
        "category": "UNDOCUMENTED_FEATURE",
        "item_id": feature_id,
        "title": "Wishlist",
        "risk": "MEDIUM",
        "confidence": 0.0,
        "evidence_ids": ["evidence-wishlist"],
        "suggested_action": "Create Requirement Draft",
    }
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Gap Action",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result={
                    "requirements": [
                        {
                            "id": "PASTED:REQ-001",
                            "source_id": "PASTED",
                            "feature": "Wishlist",
                            "expected_behavior": "Wishlist behavior from the summary.",
                            "acceptance_criteria": ["A customer can save a product for later."],
                        }
                    ],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "features": [feature],
                    "gaps": [gap],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    quality_map_rebuilds = 0
    original_build_quality_map = service._build_quality_map

    async def count_quality_map_rebuilds(current_run_id):
        nonlocal quality_map_rebuilds
        quality_map_rebuilds += 1
        await original_build_quality_map(current_run_id)

    monkeypatch.setattr(service, "_build_quality_map", count_quality_map_rebuilds)
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: service
    try:
        responses = await asyncio.gather(
            client.post(f"/api/discovery/runs/{run_id}/gaps/{gap_id}/actions/create_requirement_draft"),
            client.post(f"/api/discovery/runs/{run_id}/gaps/{gap_id}/actions/create_requirement_draft"),
        )
        assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
        created = responses[0].json()
        assert created["created"] is True
        assert created["status"] == "DRAFT"
        assert responses[1].json()["requirement_id"] == created["requirement_id"]

        previous_rebuilds = quality_map_rebuilds
        second = await client.post(f"/api/discovery/runs/{run_id}/gaps/{gap_id}/actions/create_requirement_draft")
        assert second.status_code == 200, second.text
        assert second.json() == created
        assert quality_map_rebuilds > previous_rebuilds

        async with test_db_session() as session:
            requirement = await session.get(RequirementORM, created["requirement_id"])
            updated_run = await session.get(QualityDiscoveryRunORM, run_id)
            from app.repositories.requirement_repo import RequirementRepository

            assert requirement is not None and requirement.status == "DRAFT"
            assert len(await RequirementRepository(session).list_by_project(project_id)) == 1
            assert requirement.acceptance_criteria == "A customer can save a product for later."
            assert requirement.acceptance_criteria != "Wishlist behavior from the summary."
            assert updated_run.result["requirement_drafts"][feature_id] == requirement.id
            assert (
                f"{requirement.id}:REQ-001" in updated_run.result["functional_spec"]["features"][0]["requirement_ids"]
            )
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


@pytest.mark.asyncio
async def test_workspace_test_scan_failure_marks_automation_coverage_unverified(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    feature_id = "feature-search"
    now = utc_now()

    class FailingWorkspaceService:
        async def collect_tests(self, _project_id):
            raise RuntimeError("workspace path should not be exposed")

    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Workspace Scan Failure",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result={
                    "requirements": [],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "features": [
                        {
                            "feature_id": feature_id,
                            "name": "Search",
                            "description": "Search products.",
                            "status": "OBSERVED",
                            "evidence_ids": [],
                            "state_ids": [],
                            "requirement_ids": [],
                        }
                    ],
                    "gaps": [],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        workspace_service=FailingWorkspaceService(),
    )
    await service._build_quality_map(run_id)
    mapped = await service.get(run_id)
    feature = mapped.result["features"][0]
    coverage = mapped.result["coverage"][0]

    assert mapped.result["workspace_test_scan"] == {
        "status": "UNAVAILABLE",
        "tests_collected": None,
        "message": "无法读取项目自动化工作区；自动化覆盖结果未验证。",
    }
    assert feature["coverage_status"] == "NOT_VERIFIED"
    assert feature["automation_scan_status"] == "UNAVAILABLE"
    assert coverage["automation_status"] == "NOT_VERIFIED"
    assert coverage["automation_scan_status"] == "UNAVAILABLE"
    assert not any(
        gap["category"] == "AUTOMATION_MISSING" and gap["item_id"] == feature_id for gap in mapped.result["gaps"]
    )


@pytest.mark.asyncio
async def test_generate_tests_gap_action_commits_cases_and_idempotency_record_together(test_db_session, monkeypatch):
    from app.services.ai_service import AIService

    project_id = f"project-{uuid4().hex[:12]}"
    requirement_id = f"req-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    feature_id = "feature-search"
    gap_id = "gap-test-missing-search"
    design_id = f"design-{uuid4().hex[:12]}"
    now = utc_now()
    feature = {
        "feature_id": feature_id,
        "name": "Search",
        "description": "Find products by query.",
        "status": "VERIFIED",
        "trust": "VERIFIED",
        "page_type": "search",
        "evidence_ids": ["evidence-search"],
        "state_ids": ["state-search"],
        "requirement_ids": [f"{requirement_id}:REQ-001"],
        "test_case_ids": [],
        "automation": [],
    }
    gap = {
        "id": gap_id,
        "category": "TEST_MISSING",
        "item_id": feature_id,
        "title": "Search has no test cases",
        "risk": "MEDIUM",
        "confidence": 0.9,
        "evidence_ids": ["evidence-search"],
    }
    async with test_db_session() as session:
        session.add(
            ProjectORM(id=project_id, name="Discovery Test Generation", description="", created_at=now, updated_at=now)
        )
        session.add(
            RequirementORM(
                id=requirement_id,
                project_id=project_id,
                title="Search products",
                description="Customers can find products.",
                acceptance_criteria="Matching products are shown.",
                status="APPROVED",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            _TestDesignORM(
                id=design_id,
                requirement_id=requirement_id,
                title="Discovery — Search",
                category="FUNCTIONAL",
                description="Grounded search coverage.",
                risk="Medium",
                status="DRAFT",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=requirement_id,
                requirement_text="Customers can find products.",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={"states": 1, "actions": 1, "features": 1},
                result={
                    "requirements": [
                        {
                            "id": f"{requirement_id}:REQ-001",
                            "source_id": requirement_id,
                            "feature": "Search",
                            "expected_behavior": "Matching products are shown.",
                            "acceptance_criteria": ["Matching products are shown."],
                        }
                    ],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "features": [feature],
                    "gaps": [gap],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    proposals = [
        _TestCaseGenerationItem(
            title="Search returns matching products",
            steps=["Search for a product name"],
            expected_result="Matching products are displayed.",
            priority="P1",
            tags=["search"],
        ),
        _TestCaseGenerationItem(
            title="Search with no matches shows an empty state",
            steps=["Search for an unknown product"],
            expected_result="An empty state is displayed.",
            priority="P2",
            tags=["search", "negative"],
        ),
    ]
    ai_calls = 0

    async def generate_test_cases(_self, _design_id):
        nonlocal ai_calls
        ai_calls += 1
        return proposals

    monkeypatch.setattr(AIService, "generate_test_cases", generate_test_cases)
    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    monkeypatch.setattr(service, "_assert_real_ai_available", lambda: None)
    rebuild_calls = 0
    rebuild = service._build_quality_map

    async def fail_first_rebuild(target_run_id):
        nonlocal rebuild_calls
        rebuild_calls += 1
        if rebuild_calls == 1:
            raise RuntimeError("simulated response-loss window after the action transaction committed")
        await rebuild(target_run_id)

    monkeypatch.setattr(service, "_build_quality_map", fail_first_rebuild)
    with pytest.raises(RuntimeError, match="response-loss window"):
        await service.act_on_gap(run_id, gap_id, "generate_tests")

    retried = await service.act_on_gap(run_id, gap_id, "generate_tests")
    assert ai_calls == 1
    assert len(retried["test_case_ids"]) == 2
    assert rebuild_calls == 2

    async with test_db_session() as session:
        from app.repositories.test_case_repo import TestCaseRepository

        cases = await TestCaseRepository(session).list_by_requirement(requirement_id, project_id=project_id)
        persisted_run = await session.get(QualityDiscoveryRunORM, run_id)
        assert {case.id for case in cases} == set(retried["test_case_ids"])
        assert len(cases) == 2
        assert (
            persisted_run.result["gap_actions"][gap_id]["generate_tests"]["test_case_ids"] == retried["test_case_ids"]
        )
        assert sum(event["type"] == "gap.tests_generated" for event in persisted_run.result["events"]) == 1


@pytest.mark.asyncio
async def test_generate_automation_gap_action_commits_binding_and_idempotency_record_together(
    test_db_session, monkeypatch
):
    from app.repositories.automation_binding_repo import AutomationBindingRepository
    from app.services.automation_binding_service import AutomationBindingService

    project_id = f"project-{uuid4().hex[:12]}"
    requirement_id = f"req-{uuid4().hex[:12]}"
    case_id = f"case-{uuid4().hex[:12]}"
    run_id = f"qd-{uuid4().hex[:12]}"
    feature_id = "feature-search"
    gap_id = "gap-automation-missing-search"
    now = utc_now()
    feature = {
        "feature_id": feature_id,
        "name": "Search",
        "description": "Find products by query.",
        "status": "VERIFIED",
        "trust": "VERIFIED",
        "evidence_ids": ["evidence-search"],
        "state_ids": ["state-search"],
        "requirement_ids": [requirement_id],
        "test_case_ids": [case_id],
        "automation": [],
    }
    gap = {
        "id": gap_id,
        "category": "AUTOMATION_MISSING",
        "item_id": feature_id,
        "title": "Search has no automation",
        "risk": "MEDIUM",
        "confidence": 0.9,
        "evidence_ids": ["evidence-search"],
    }
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id, name="Discovery Automation Idempotency", description="", created_at=now, updated_at=now
            )
        )
        session.add(
            RequirementORM(
                id=requirement_id,
                project_id=project_id,
                title="Search",
                description="Search products",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            _TestCaseORM(
                id=case_id,
                project_id=project_id,
                requirement_id=requirement_id,
                title="Search returns products",
                preconditions="",
                steps=["Search for a product"],
                expected_result="Matching products are displayed.",
                priority="P1",
                automation_status="MANUAL",
                tags=["search"],
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="golden-fixture",
                mode="AUDIT",
                start_url="http://shop.example.test/",
                requirement_id=requirement_id,
                requirement_text="Search products",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={"states": 1, "actions": 1, "features": 1},
                result={
                    "requirements": [],
                    "states": [],
                    "edges": [],
                    "actions": [],
                    "features": [feature],
                    "gaps": [gap],
                    "coverage": [],
                },
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    generation_calls = 0
    action_keys = []

    async def generate_draft(self, test_case_id, *, idempotency_key=None):
        nonlocal generation_calls
        generation_calls += 1
        action_keys.append(idempotency_key)
        binding = await self.bind_test_case(
            AutomationBindingCreate(
                test_case_id=test_case_id,
                workspace_id=project_id,
                nodeid="tests/test_discovery_search.py::test_search",
                file_path="tests/test_discovery_search.py",
                framework=FrameworkType.PLAYWRIGHT_PYTHON,
                status=AutomationBindingStatus.DRAFT,
            )
        )
        return binding, "def test_search():\n    assert True\n"

    monkeypatch.setattr(AutomationBindingService, "generate_automation_draft", generate_draft)
    service = QualityDiscoveryService(test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime())
    monkeypatch.setattr(service, "_assert_real_ai_available", lambda: None)
    rebuild_calls = 0

    async def fail_first_rebuild(_target_run_id):
        nonlocal rebuild_calls
        rebuild_calls += 1
        if rebuild_calls == 1:
            raise RuntimeError("simulated response-loss window after the action transaction committed")

    monkeypatch.setattr(service, "_build_quality_map", fail_first_rebuild)
    with pytest.raises(RuntimeError, match="response-loss window"):
        await service.act_on_gap(run_id, gap_id, "generate_automation")

    retried = await service.act_on_gap(run_id, gap_id, "generate_automation")
    assert generation_calls == 1
    assert action_keys == [f"{run_id}:{gap_id}:{case_id}"]
    assert retried["binding"]["test_case_id"] == case_id
    assert rebuild_calls == 2

    async with test_db_session() as session:
        bindings = await AutomationBindingRepository(session).list_by_project(project_id)
        persisted_run = await session.get(QualityDiscoveryRunORM, run_id)
        assert len(bindings) == 1
        assert persisted_run.result["gap_actions"][gap_id]["generate_automation"]["binding"]["id"] == bindings[0].id
        assert sum(event["type"] == "gap.automation_generated" for event in persisted_run.result["events"]) == 1


@pytest.mark.asyncio
async def test_automation_draft_reuses_action_marked_file_after_write_before_database_commit(tmp_path, monkeypatch):
    from app.services import automation_binding_service as binding_module
    from app.services.automation_binding_service import AutomationBindingService
    from app.services.workspace_service import WorkspaceService

    case_id = f"case-{uuid4().hex[:12]}"
    project_id = f"project-{uuid4().hex[:12]}"
    case = SimpleNamespace(
        id=case_id,
        project_id=project_id,
        title="Search returns matching products",
        preconditions="",
        steps=["Search for a product"],
        expected_result="Matching products are displayed.",
        test_model=None,
    )

    class CaseRepository:
        async def get_by_id(self, _test_case_id):
            return case

        async def update(self, _test_case_id, _patch):
            return case

    class WorkspaceRepository:
        async def get_by_project_id(self, _project_id):
            return object()

    class BindingRepository:
        binding = None

        async def create_or_update(self, data):
            if self.binding is None:
                self.binding = AutomationBindingORM(
                    id=f"binding-{uuid4().hex[:12]}",
                    test_case_id=data.test_case_id,
                    workspace_id=data.workspace_id,
                    nodeid=data.nodeid,
                    file_path=data.file_path,
                    framework=data.framework.value,
                    status=data.status.value,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            return self.binding

    ai_calls = 0

    class FixtureOrchestrator:
        async def assist_code_chat(self, **_kwargs):
            nonlocal ai_calls
            ai_calls += 1
            return CodeAssistantResponse(
                reply="Grounded fixture draft.",
                suggested_code="def test_discovery_search():\n    assert 1 == 1\n",
                provider="configured-test-provider",
                model="fixture-model",
            )

    monkeypatch.setattr(binding_module, "build_ai_orchestrator", FixtureOrchestrator)
    workspace_service = WorkspaceService(tmp_path / "workspace")
    workspace_service.get_workspace_dir(project_id).mkdir(parents=True, exist_ok=True)
    service = AutomationBindingService(BindingRepository(), CaseRepository(), WorkspaceRepository(), workspace_service)
    action_key = f"run-{uuid4().hex}:{case_id}"

    first_binding, first_code = await service.generate_automation_draft(case_id, idempotency_key=action_key)
    second_binding, second_code = await service.generate_automation_draft(case_id, idempotency_key=action_key)

    assert ai_calls == 1
    assert first_binding.id == second_binding.id
    assert first_binding.file_path == second_binding.file_path
    assert first_code == second_code
    assert "Quality Discovery action:" in second_code
    assert (workspace_service.get_workspace_dir(project_id) / first_binding.file_path).is_file()


def test_requirement_check_does_not_pass_when_criteria_are_unsupported_or_uncovered():
    requirement = {
        "acceptance_criteria": ["Search returns matching products.", "The result count updates."],
        "checks": [
            {
                "target": "Search",
                "attribute": "enabled",
                "expected": True,
                "criterion": "Search returns matching products.",
            }
        ],
    }
    state = {"state_id": "search", "controls": [{"name": "Search", "enabled": True}]}
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, [state])
    assert status == "NOT_VERIFIED"
    assert results[-1]["uncovered_criteria"] == ["Search returns matching products.", "The result count updates."]


def test_requirement_check_rejects_enabled_button_as_proof_of_business_result():
    criterion = "Adding to cart increases the cart item count."
    requirement = {
        "expected_behavior": criterion,
        "acceptance_criteria": [criterion],
        "checks": [
            {
                "target": "Add To Cart",
                "attribute": "enabled",
                "expected": True,
                "criterion": criterion,
            }
        ],
    }
    state = {"state_id": "product", "controls": [{"name": "Add To Cart", "enabled": True}]}
    status, results = QualityDiscoveryService._evaluate_requirement_checks(requirement, [state])
    assert status == "NOT_VERIFIED"
    assert results[0]["reason"] == "The rule does not directly prove its linked requirement criterion."


def test_visible_search_results_can_pass_with_direct_state_evidence():
    criterion = "“Search results for qa sample” are displayed after submitting the query."
    requirement = {
        "expected_behavior": criterion,
        "acceptance_criteria": [criterion],
        "checks": [
            {
                "target": "Search results for qa sample",
                "attribute": "visible",
                "expected": True,
                "when": "after_action",
                "criterion": criterion,
            }
        ],
    }
    state = {
        "state_id": "search-results",
        "evidence_id": "evidence-search-results",
        "main_content": "Search results for qa sample",
        "controls": [],
    }
    status, results = QualityDiscoveryService._evaluate_requirement_checks(
        requirement,
        [state],
        [{"from_state_id": "search-form", "to_state_id": "search-results", "action": "search"}],
    )
    assert status == "PASS"
    assert results[0]["evidence_id"] == "evidence-search-results"


def test_visible_search_requirement_requires_a_matching_search_transition():
    criterion = "“Search results for qa sample” are displayed after submitting the query."
    requirement = {
        "expected_behavior": criterion,
        "acceptance_criteria": [criterion],
        "checks": [
            {
                "target": "Search results for qa sample",
                "attribute": "visible",
                "expected": True,
                "when": "after_action",
                "criterion": criterion,
            }
        ],
    }
    state = {
        "state_id": "search-results",
        "main_content": "Search results for qa sample",
        "controls": [],
    }
    status, _results = QualityDiscoveryService._evaluate_requirement_checks(
        requirement,
        [state],
        [{"from_state_id": "home", "to_state_id": "search-results", "action": "click", "label": "Products"}],
    )
    assert status == "NOT_VERIFIED"


def test_visible_check_does_not_claim_a_count_increased():
    state = {
        "state_id": "search-results",
        "main_content": "Search results count appears: 4",
        "controls": [],
    }
    for criterion, target in (
        ("“Search results count appears” after the query and increases.", "Search results count appears"),
        (
            "“Search results count appears” after the query and is twice its previous value.",
            "Search results count appears",
        ),
        ("“Search results count” doubles after the query.", "Search results count"),
        ("“Search results count appears” after query with a minimum of 5.", "Search results count appears"),
        ("“Search result count” is accurate.", "Search result count"),
    ):
        requirement = {
            "expected_behavior": criterion,
            "acceptance_criteria": [criterion],
            "checks": [
                {
                    "target": target,
                    "attribute": "visible",
                    "expected": True,
                    "when": "after_action",
                    "criterion": criterion,
                }
            ],
        }
        status, results = QualityDiscoveryService._evaluate_requirement_checks(
            requirement,
            [state],
            [{"from_state_id": "search", "to_state_id": "search-results", "action": "search"}],
        )
        assert status == "NOT_VERIFIED"
        assert results[0]["reason"] == "The rule does not directly prove its linked requirement criterion."


def test_visible_check_does_not_claim_accuracy_when_target_repeats_the_criterion():
    for criterion, target in (
        ("“Search result count is accurate.”", "Search result count is accurate."),
        ("Trustworthy search results are displayed.", "Trustworthy search results"),
        ("“Trustworthy search results” are displayed.", "Trustworthy search results"),
        ("Search results count", "Search results count"),
    ):
        requirement = {
            "expected_behavior": criterion,
            "acceptance_criteria": [criterion],
            "checks": [{"target": target, "attribute": "visible", "expected": True, "criterion": criterion}],
        }
        state = {"state_id": "results", "main_content": criterion, "controls": []}
        status, _results = QualityDiscoveryService._evaluate_requirement_checks(requirement, [state])
        assert status == "NOT_VERIFIED"


def test_page_title_redacts_embedded_url_query_and_fragment():
    title = "Catalog https://shop.example.test/products?token=secret#private"
    safe = QualityDiscoveryService._safe_title(title)
    assert safe == "Catalog https://shop.example.test/products"
    assert "secret" not in safe
    assert "private" not in safe
    assert QualityDiscoveryService._safe_title("Search /catalog?q=private#results") == "Search /catalog"
    assert QualityDiscoveryService._safe_title("Search catalog?q=private#results") == "Search catalog"
    assert QualityDiscoveryService._safe_title("Search ?q=private#results") == "Search"
    assert (
        QualityDiscoveryService._safe_title("Search //shop.example.test/catalog?q=private#results")
        == "Search //shop.example.test/catalog"
    )


@pytest.mark.asyncio
async def test_jev_score_reorders_discovery_candidates_only_as_a_ranking_recommendation(test_db_session):
    class ScoreDecisions:
        async def ask_score(self, request, *, run_id, daily_request_reserve):
            assert daily_request_reserve == 1
            candidate_id = request.state["candidate"]["candidate_id"]
            return DecisionResult(
                provider="jev",
                model="test-score",
                score={"candidate_1": 0.35, "candidate_2": 0.92}[candidate_id],
                confidence=0.95,
            )

        async def choose(self, _request, **_kwargs):
            raise AssertionError("Scoring must not replace the deterministic candidate choice step")

    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        decisions=ScoreDecisions(),
    )
    score_events = []

    async def record_event(_run_id, event_type, _message, metadata):
        score_events.append((event_type, metadata))

    service._event = record_event
    choices = {
        "candidate_1": {"candidate_id": "candidate_1", "action_type": "click", "target": "Search"},
        "candidate_2": {"candidate_id": "candidate_2", "action_type": "click", "target": "Continue"},
    }

    ranked = await service._score_candidate_priority(
        "discovery-score-test",
        state={"state_id": "home", "goal": "EXPLORE"},
        choices=choices,
        priority_ids=["candidate_1", "candidate_2"],
    )

    assert ranked == ["candidate_2", "candidate_1"]
    assert len(score_events) == 2
    assert all(event_type == "decision.score_recommendation" for event_type, _metadata in score_events)
    assert all(metadata["advisory_only"] is True for _event_type, metadata in score_events)


@pytest.mark.asyncio
async def test_discovery_ignores_low_confidence_score_recommendations(test_db_session):
    class LowConfidenceScores:
        async def ask_score(self, _request, **_kwargs):
            return DecisionResult(provider="jev", score=0.99, confidence=0.2)

    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        decisions=LowConfidenceScores(),
    )
    ranked = await service._score_candidate_priority(
        "discovery-low-score-confidence",
        state={},
        choices={
            "candidate_1": {"candidate_id": "candidate_1", "action_type": "click", "target": "Search"},
            "candidate_2": {"candidate_id": "candidate_2", "action_type": "click", "target": "Continue"},
        },
        priority_ids=["candidate_1", "candidate_2"],
    )

    assert ranked == ["candidate_1", "candidate_2"]


def _replayable_discovery_result(*, final_state_overrides=None):
    start_state = {
        "state_id": "state-home",
        "fingerprint": "fingerprint-home",
        "url": "https://shop.example.test/",
        "url_navigable": True,
        "title": "Shop",
        "main_content": "Search products",
        "landmarks": 'heading "Shop" [level=1]',
        "controls": [
            {
                "index": 3,
                "tag": "input",
                "type": "search",
                "role": "searchbox",
                "name": "Search products",
                "id": "product-search",
                "test_id": "product-search",
                "visible": True,
                "enabled": True,
            }
        ],
        "evidence_id": "evidence-home",
    }
    final_state = {
        "state_id": "state-results",
        "fingerprint": "fingerprint-results",
        "url": "https://shop.example.test/search",
        "url_navigable": True,
        "title": "Search results",
        "main_content": "Search results for camera",
        "landmarks": 'heading "Search results for camera" [level=1]',
        "controls": [],
        "evidence_id": "evidence-results",
        **(final_state_overrides or {}),
    }
    return {
        "requirements": [],
        "features": [],
        "gaps": [],
        "edges": [
            {
                "from_state_id": "state-home",
                "to_state_id": "state-results",
                "action": "search",
                "label": "Search products",
                "candidate_id": "candidate-search",
            }
        ],
        "actions": [
            {
                "candidate_id": "candidate-search",
                "from_state_id": "state-home",
                "target_id": "el_3",
                "action_type": "search",
                "target": "Search products",
                "status": "EXECUTED",
                "state_changed": True,
                "to_fingerprint": "fingerprint-results",
                "search_value": "camera",
                "expected_effect": "Observe matching search results.",
            }
        ],
        "states": [start_state, final_state],
        "journeys": [
            {
                "journey_id": "journey-1",
                "steps": [
                    {"state_id": "state-home", "title": "Shop", "evidence_ids": ["evidence-home"]},
                    {
                        "state_id": "state-results",
                        "title": "Search results",
                        "action": "Search products",
                        "evidence_ids": ["evidence-results"],
                    },
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_discovery_journey_creates_replayable_create_test_draft_without_browser_input(test_db_session):
    from project_model.task_models import TaskType

    project_id = f"project-{uuid4().hex[:12]}"
    run_id = str(uuid4())
    now = utc_now()
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Draft",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="test",
                mode="EXPLORE",
                start_url="https://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={"states": 2, "actions": 1, "features": 0},
                result=_replayable_discovery_result(),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    class CaptureTasks:
        data = None
        owner_id = None

        async def create(self, data, owner_id):
            self.data = data
            self.owner_id = owner_id
            return SimpleNamespace(id="task-draft", status="PENDING")

    tasks = CaptureTasks()
    service = QualityDiscoveryService(
        test_db_session, browser_runtime=DiscoveryFixtureBrowserRuntime(), task_commands=tasks
    )
    task = await service.create_pytest_draft(run_id, "journey-1", "owner-1")

    assert task.id == "task-draft"
    assert tasks.owner_id == "owner-1"
    assert tasks.data.type == TaskType.CREATE_TEST
    assert tasks.data.project_id == project_id and tasks.data.workspace_id == project_id
    assert "url" not in tasks.data.inputs and "recorder_session_id" not in tasks.data.inputs
    assert tasks.data.inputs["assertion_bypass_check"] is True
    steps = tasks.data.inputs["recorded_steps"]
    assert [step["action"] for step in steps] == ["navigate", "fill", "press", "assert_text"]
    assert steps[1]["locator"]["kind"] == "role"
    assert steps[1]["value"] == "camera"
    assert steps[2]["key"] == "Enter"
    assert steps[-1]["locator"]["name"] == "Search results for camera"


@pytest.mark.asyncio
async def test_discovery_journey_draft_rejects_non_replayable_or_unassertable_journeys(test_db_session):
    project_id = f"project-{uuid4().hex[:12]}"
    run_id = str(uuid4())
    now = utc_now()
    result = _replayable_discovery_result(final_state_overrides={"title": "", "landmarks": "", "main_content": ""})
    async with test_db_session() as session:
        session.add(
            ProjectORM(
                id=project_id,
                name="Discovery Draft Evidence",
                description="",
                default_branch="main",
                framework_type="playwright_python",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="test",
                mode="EXPLORE",
                start_url="https://shop.example.test/",
                requirement_id=None,
                requirement_text="",
                allowed_domains=["shop.example.test"],
                status="COMPLETED",
                progress={},
                result=result,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    class CaptureTasks:
        async def create(self, *_args, **_kwargs):
            pytest.fail("A draft must not be created without grounded assertion evidence")

    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        task_commands=CaptureTasks(),
    )
    with pytest.raises(ValueError, match="assertion|observable"):
        await service.create_pytest_draft(run_id, "journey-1", "owner-1")

    run = await service.get(run_id)
    non_replayable = _replayable_discovery_result()
    with pytest.raises(ValueError, match="transition"):
        service._journey_recording_steps(
            run,
            non_replayable,
            {"journey_id": "journey-1", "steps": non_replayable["journeys"][0]["steps"][:1]},
        )
    unverified = _replayable_discovery_result()
    unverified["actions"][0]["status"] = "FAILED"
    with pytest.raises(ValueError, match="successfully executed and verified"):
        service._journey_recording_steps(run, unverified, unverified["journeys"][0])

    non_text_search = {
        "action_type": "search",
        "target_id": "el_3",
        "target": "Search",
    }
    button_state = {
        "controls": [{"index": 3, "tag": "button", "role": "button", "name": "Search", "visible": True}],
    }
    with pytest.raises(ValueError, match="replayable text input"):
        service._append_replay_action([], non_text_search, button_state)
    with pytest.raises(ValueError, match="observed-control evidence"):
        service._append_replay_action([], non_text_search, {"controls": None})


@pytest.mark.asyncio
async def test_discovery_draft_api_waits_for_approval_before_workspace_write(client, test_db_session):
    from app.container import get_task_runtime_service
    from app.services.workspace_service import WorkspaceService

    task_scheduler_service = get_task_runtime_service().scheduler

    async def serve_page(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            path = request.split(b" ", 2)[1]
            if path.startswith(b"/search"):
                title, body = "Search results", "<h1>Search results for camera</h1>"
            else:
                title, body = (
                    "Shop",
                    (
                        "<h1>Shop</h1><form action='/search' method='get'>"
                        "<input type='search' name='q' aria-label='Search products'></form>"
                    ),
                )
            content = f"<html><head><title>{title}</title></head><body>{body}</body></html>".encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\nContent-Length: "
                + str(len(content)).encode()
                + b"\r\n\r\n"
                + content
            )
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    project = await client.post("/api/projects", json={"name": "Discovery Draft API", "bootstrap_workspace": True})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    server = await asyncio.start_server(serve_page, "127.0.0.1", 0)
    start_url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    run_id = str(uuid4())
    now = utc_now()
    async with test_db_session() as session:
        session.add(
            QualityDiscoveryRunORM(
                id=run_id,
                project_id=project_id,
                requested_by="test",
                mode="EXPLORE",
                start_url=start_url,
                requirement_id=None,
                requirement_text="",
                allowed_domains=["127.0.0.1"],
                status="COMPLETED",
                progress={"states": 2, "actions": 1, "features": 0},
                result=_replayable_discovery_result(),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    await task_scheduler_service.start()
    try:
        response = await client.post(f"/api/discovery/runs/{run_id}/journeys/journey-1/pytest-draft")
        assert response.status_code == 202, response.text
        task_id = response.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            detail = await client.get(f"/api/tasks/{task_id}")
            if detail.json()["status"] in {"WAITING", "FAILED", "BLOCKED"}:
                break
        waiting = detail.json()
        assert waiting["status"] == "WAITING", waiting.get("failure_reason")
        assert "url" not in waiting["inputs"]
        assert waiting["inputs"]["assertion_bypass_check"] is True
        assert all(
            next(step for step in waiting["steps"] if step["key"] == key)["status"] == "SKIPPED"
            for key in ("inspect", "decide", "act")
        )
        generated = next(step for step in waiting["steps"] if step["key"] == "generate")["outputs"]["suggested_code"]
        assert "to_contain_text" in generated
        file_path = waiting["inputs"]["file_path"]
        workspace_file = WorkspaceService().get_workspace_dir(project_id) / file_path
        assert not workspace_file.exists()

        rejected = await client.post(
            f"/api/tasks/{task_id}/approval",
            json={"approved": False, "comment": "Keep this as a draft"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "BLOCKED"
        assert not workspace_file.exists()

        adopted = await client.post(f"/api/discovery/runs/{run_id}/journeys/journey-1/pytest-draft")
        assert adopted.status_code == 202, adopted.text
        adopted_id = adopted.json()["id"]
        for _ in range(150):
            await asyncio.sleep(0.2)
            adopted_detail = await client.get(f"/api/tasks/{adopted_id}")
            if adopted_detail.json()["status"] in {"WAITING", "FAILED", "BLOCKED"}:
                break
        assert adopted_detail.json()["status"] == "WAITING", adopted_detail.json().get("failure_reason")
        approved = await client.post(
            f"/api/tasks/{adopted_id}/approval",
            json={"approved": True, "comment": "Adopt the reviewed Discovery journey"},
        )
        assert approved.status_code == 200, approved.text
        for _ in range(600):
            await asyncio.sleep(0.2)
            adopted_detail = await client.get(f"/api/tasks/{adopted_id}")
            if adopted_detail.json()["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
                break
        assert adopted_detail.json()["status"] == "COMPLETED", adopted_detail.json().get("failure_reason")
        assert workspace_file.exists()
        run_step = next(step for step in adopted_detail.json()["steps"] if step["key"] == "run")
        assert run_step["outputs"]["status"] == "PASSED"
    finally:
        await task_scheduler_service.stop()
        server.close()
        await server.wait_closed()
