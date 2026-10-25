from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import uvicorn
from app.container import (
    get_ai_service,
    get_browser_runtime,
    get_platform_health_service,
    get_quality_discovery_service,
)
from app.main import app
from app.persistence.models import FailureRecordORM, TestExecutionORM, TestRunORM
from app.services.ai_service import AIService
from app.services.decision_service import DecisionService
from app.services.quality_discovery_service import QualityDiscoveryService
from app.services.workspace_service import WorkspaceService
from app.settings import settings
from project_model.models import (
    AIProviderOperationalState,
    AIProviderRuntimeState,
    AIProviderStatus,
    AIStatusResponse,
    DecisionResult,
)
from qa_core.ai.models import TestCaseGenerationItem as _TestCaseGenerationItem
from test_quality_discovery import DiscoveryFixtureAI

EVIDENCE_ROOT = Path(
    os.environ.get(
        "AI_QA_E2E_EVIDENCE_DIR",
        str(Path(__file__).resolve().parents[3] / ".ai-runs/night-continuation"),
    )
)
BROWSER_CHANNEL = os.environ.get("AI_QA_ACCEPTANCE_BROWSER_CHANNEL") or None


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def _goto_app(page, url: str) -> None:
    """Cold Vite loads occasionally serve an empty shell; reload until the SPA mounts."""
    for attempt in range(3):
        await page.goto(url, wait_until="commit")
        try:
            await page.wait_for_function("() => document.body.innerText.trim().length > 20", timeout=20000)
            return
        except Exception:
            if attempt == 2:
                raise


async def _shot(page, *, path: str, full_page: bool = True) -> None:
    """Full-page capture occasionally stalls waiting for webfonts; retry the same shot."""
    for attempt in range(3):
        try:
            await page.screenshot(path=path, full_page=full_page)
            return
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(1)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_real_browser_discovery_to_playwright_coverage_e2e(client, test_db_session, tmp_path, monkeypatch):
    """Exercise persisted Discovery and the complete test-to-coverage path against real Chromium."""
    pytest.importorskip("playwright")
    html = {
        "home": "<main><h1>QA Shop</h1><a href='/search'>Products</a></main>",
        "search": (
            "<main><h1>Search products</h1><form action='/search'>"
            "<label for='q'>Search</label><input id='q' name='q' type='search' role='textbox' placeholder='Search'>"
            "<button type='submit'>Search</button></form></main>"
        ),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query).get("q", [""])[0]
            if parsed.path == "/" or parsed.path == "/index.html":
                body = html["home"]
            elif parsed.path == "/search" and query:
                body = f"<main><h1>Search results for {query}</h1><p>Canvas tote</p></main>"
            else:
                body = html["search"]
            payload = f"<!doctype html><html><head><title>QA Shop</title></head><body>{body}</body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    website = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    website_thread = threading.Thread(target=website.serve_forever, daemon=True)
    website_thread.start()
    target = f"http://127.0.0.1:{website.server_port}/"
    workspace_dir = tmp_path / "workspaces"
    workspace_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "workspace_storage_dir", workspace_dir)
    monkeypatch.setattr(settings, "runtime_dir", tmp_path / "runtime")
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    ai = DiscoveryFixtureAI()
    decisions = []

    async def choose_candidate(_service, request, **_kwargs):
        candidates = request.state["candidates"]
        if not decisions:
            matches = [item for item in candidates if item["target"] == "Products" and item["target_role"] == "link"]
        else:
            matches = [
                item
                for item in candidates
                if item["target_role"] in {"textbox", "button"}
                and item.get("operation") is None
                and (item["target_role"] != "button" or item["target"] == "Search")
            ]
        assert matches, f"expected a safe observed search action after {decisions}, got {candidates}"
        chosen = matches[0]
        decisions.append(chosen["key"])
        return DecisionResult(
            choice=chosen["key"],
            provider="jev-controlled-fixture",
            model="local-acceptance",
            confidence=0.99,
            probabilities={chosen["key"]: 0.99},
            reason="Choose a read-only navigation/search action from observed controls.",
        )

    monkeypatch.setattr(DecisionService, "choose", choose_candidate)
    monkeypatch.setattr(DecisionService, "ask_score", lambda *_args, **_kwargs: None)
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=get_browser_runtime(),
        decisions=DecisionService(),
        provider_factory=lambda: ai,
        workspace_service=WorkspaceService(base_dir=workspace_dir),
    )
    monkeypatch.setattr(service, "_assert_real_ai_available", lambda: None)
    app.dependency_overrides[get_quality_discovery_service] = lambda: service
    real_generate = AIService.generate_test_cases

    class LocalAIStatus:
        async def get_status(self):
            return AIStatusResponse(
                provider="fixture",
                status=AIProviderRuntimeState.UNAVAILABLE,
                health_status=AIProviderStatus.UNAVAILABLE,
                operational_state=AIProviderOperationalState.UNAVAILABLE,
            )

    class LocalPlatformHealth:
        async def check(self, refresh=False):
            return {"status": "healthy", "components": [], "refresh": refresh}

    app.dependency_overrides[get_ai_service] = LocalAIStatus
    app.dependency_overrides[get_platform_health_service] = LocalPlatformHealth
    proposals = [
        _TestCaseGenerationItem(
            title="Search returns the requested product",
            steps=["Open Products", "Search for qa sample"],
            expected_result="Search results for qa sample are displayed.",
            priority="P1",
            tags=["search"],
        )
    ]

    async def generate_fixture_cases(_self, _design_id):
        return proposals

    monkeypatch.setattr(AIService, "generate_test_cases", generate_fixture_cases)
    api_server = None
    api_task = None
    vite_process = None
    vite_log = None
    try:
        project_response = await client.post("/api/projects", json={"name": "Round 3 local discovery"})
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        created = await client.post(
            "/api/discovery/runs", json={"project_id": project_id, "start_url": target, "mode": "EXPLORE"}
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        run = created.json()
        for _ in range(300):
            if run["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.1)
            run = (await client.get(f"/api/discovery/runs/{run_id}")).json()
        assert run["status"] == "COMPLETED", {key: run.get(key) for key in ("status", "error", "progress", "result")}
        assert run["project_id"] == project_id and run["start_url"] == target
        assert len(run["result"]["states"]) >= 2
        assert run["result"]["actions"] and run["result"]["features"]
        assert all(
            state.get("evidence_id") and state.get("screenshot_evidence_id") for state in run["result"]["states"]
        )
        assert decisions and ai.calls >= 2
        assert all(item["provider"] == "jev-controlled-fixture" for item in run["result"]["decisions"])
        missing = next(gap for gap in run["result"]["gaps"] if gap["category"] == "TEST_MISSING")
        feature_id = missing["item_id"]
        api_port = _free_port()
        api_server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=api_port, lifespan="off", log_level="error")
        )
        api_task = asyncio.create_task(api_server.serve())
        vite_port = _free_port()
        repository_root = Path(__file__).resolve().parents[3]
        evidence_dir = EVIDENCE_ROOT / "round-3/evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        vite_env = {**os.environ, "VITE_DEV_API_TARGET": f"http://127.0.0.1:{api_port}"}
        vite_log = (evidence_dir / "vite.log").open("w", encoding="utf-8")
        vite_process = subprocess.Popen(
            [
                "node",
                str(repository_root / "apps/web/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(vite_port),
                "--strictPort",
            ],
            cwd=repository_root / "apps/web",
            env=vite_env,
            stdout=vite_log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if api_server.started and vite_process.poll() is None:
                try:
                    await asyncio.to_thread(
                        lambda: (
                            __import__("urllib.request", fromlist=["urlopen"])
                            .urlopen(f"http://127.0.0.1:{vite_port}", timeout=1)
                            .close()
                        )
                    )
                    break
                except OSError:
                    pass
            await asyncio.sleep(0.1)
        else:
            vite_log.flush()
            raise AssertionError(
                f"API/Vite servers did not become ready; API task={api_task.done()}, "
                f"Vite exit={vite_process.poll()}, log={vite_log.name}"
            )
        vite_log.close()

        from playwright.async_api import async_playwright, expect

        evidence_dir = EVIDENCE_ROOT / "round-3/evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
            context = await browser.new_context()
            for font_host in ("https://fonts.googleapis.com/**", "https://fonts.gstatic.com/**"):
                await context.route(font_host, lambda route: route.abort())
            token = client.headers["Authorization"].removeprefix("Bearer ")
            await context.add_init_script(
                f"localStorage.setItem('ai-qa.auth-token', {json.dumps(token)}); "
                "localStorage.setItem('ai-qa.language', 'en');"
            )
            page = await context.new_page()
            page_diagnostics = []
            page.on("request", lambda request: page_diagnostics.append(f"request: {request.url}"))
            page.on("response", lambda response: page_diagnostics.append(f"response: {response.status} {response.url}"))
            page.on("pageerror", lambda error: page_diagnostics.append(f"pageerror: {error}"))
            page.on(
                "console",
                lambda message: (
                    page_diagnostics.append(f"console: {message.text}") if message.type == "error" else None
                ),
            )
            page.on(
                "requestfailed",
                lambda request: page_diagnostics.append(f"requestfailed: {request.url} {request.failure}"),
            )
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/")
            await page.get_by_text("平台总览", exact=True).wait_for(timeout=45000)
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover")
            try:
                await page.get_by_label("应用起始 URL").wait_for(timeout=30000)
            except Exception as error:
                raise AssertionError(
                    f"Discovery form absent at {page.url}; body={(await page.locator('body').inner_text())[:1200]}; "
                    f"browser={page_diagnostics[-40:]}; "
                    f"document={await page.evaluate('({state: document.readyState, html: document.documentElement.outerHTML.slice(0, 1500)})')}"
                ) from error
            await page.get_by_role("button", name="需求与覆盖差距").click()
            async with page.expect_response(
                lambda response: (
                    f"/discovery/runs/{run_id}/gaps/{missing['id']}/actions/create_requirement_draft" in response.url
                )
            ) as draft_response:
                await page.get_by_role("button", name="创建需求草稿").click()
            draft_result = await draft_response.value
            assert draft_result.status == 200
            draft_action = await draft_result.json()
            draft_id = draft_action["requirement_id"]
            draft_detail = (await client.get(f"/api/requirements/{draft_id}")).json()
            scenario_title = draft_detail["qa_model"]["analysis"]["scenarios"][0]["title"]
            assert "view=discover" in page.url
            await page.get_by_role("button", name="打开草稿").click()
            await page.wait_for_function("new URL(location.href).searchParams.get('view') === 'requirement'")
            await _shot(page, path=str(evidence_dir / "requirement-draft-review.png"), full_page=True)
            await page.get_by_role("button", name="场景设计").click()
            await page.get_by_text(scenario_title, exact=False).wait_for(timeout=10000)
            await page.get_by_text(f"Derived from Discovery run {run_id}", exact=False).wait_for(timeout=10000)
            await _shot(page, path=str(evidence_dir / "scenario-review.png"), full_page=True)
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover")
            await page.get_by_role("button", name="需求与覆盖差距").click()
            generate_button = page.get_by_role("button", name="生成测试用例")
            await generate_button.wait_for(state="visible", timeout=10000)
            await expect(generate_button).to_be_enabled(timeout=10000)
            async with page.expect_response(
                lambda response: f"/discovery/runs/{run_id}/gaps/{missing['id']}/actions/generate_tests" in response.url
            ) as generation_response:
                await generate_button.click(force=True)
            generated_response = await generation_response.value
            assert generated_response.status == 200, await generated_response.text()
            generated_run = (await client.get(f"/api/discovery/runs/{run_id}")).json()
            case_id = generated_run["result"]["gap_actions"][missing["id"]]["generate_tests"]["test_case_ids"][0]
            await page.wait_for_function("new URL(location.href).searchParams.get('view') === 'cases'")
            await page.wait_for_function(
                "caseId => new URL(location.href).searchParams.get('caseId') === caseId",
                arg=case_id,
            )
            await expect(page.get_by_text("Search returns the requested product", exact=True)).to_have_count(2)
            await expect(page.get_by_text("Search for qa sample", exact=True)).to_be_visible()
            await _shot(page, path=str(evidence_dir / "test-case-review.png"), full_page=True)
            run = (await client.get(f"/api/discovery/runs/{run_id}")).json()
            gap_actions = run["result"]["gap_actions"][missing["id"]]
            requirement_id = gap_actions["create_requirement_draft"]["requirement_id"]
            requirement_response = await client.get(f"/api/requirements/{requirement_id}")
            assert requirement_response.status_code == 200, requirement_response.text
            requirement_data = requirement_response.json()
            requirement_scenarios = requirement_data["qa_model"]["analysis"]["scenarios"]
            requirement_risks = requirement_data["qa_model"]["analysis"]["risks"]
            generated_action = gap_actions["generate_tests"]
            case_id = generated_action["test_case_ids"][0]
            case = next(item for item in generated_action["test_cases"] if item["id"] == case_id)
            assert case["requirement_id"] == requirement_id and case["project_id"] == project_id
            assert case["test_design_id"] == generated_action["test_design_id"]
            design_response = await client.get(f"/api/test-designs/{generated_action['test_design_id']}")
            assert design_response.status_code == 200, design_response.text
            design = design_response.json()
            scenario = design["scenario_model"]
            assert design["requirement_id"] == requirement_id
            assert scenario["id"].startswith("SCN-") and scenario["actions"] and scenario["expected_outcomes"]
            assert scenario["id"] in {item["id"] for item in requirement_scenarios}
            assert scenario["coverage"]["risk_ids"] == [requirement_risks[0]["id"]]
            assert run_id in scenario["rationale"] and missing["id"] in scenario["rationale"]
            file_path = "tests/test_discovered_search.py"
            nodeid = f"{file_path}::test_discovered_search"
            source = f"""from playwright.sync_api import sync_playwright


def test_discovered_search():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        try:
            page = browser.new_page()
            page.goto({target!r})
            page.get_by_role("link", name="Products", exact=True).click()
            page.get_by_role("textbox", name="Search").fill("qa sample")
            page.get_by_role("button", name="Search", exact=True).click()
            assert page.get_by_role("heading", name="Search results for qa sample", exact=True).is_visible()
        finally:
            browser.close()
"""
            saved = await client.put(f"/api/workspaces/{project_id}/file", json={"path": file_path, "content": source})
            assert saved.status_code == 200, saved.text
            await page.locator("details.workspace-case-automation > summary").click()
            await page.get_by_role("button", name="配置绑定").click()
            modal_inputs = page.locator(".modal-dialog input[type='text']")
            await modal_inputs.nth(0).fill(file_path)
            await modal_inputs.nth(1).fill(nodeid)
            await page.locator(".modal-dialog select").select_option("ACTIVE")
            async with page.expect_response(
                lambda response: f"/test-cases/{case_id}/binding" in response.url and response.request.method == "POST"
            ) as binding_response:
                await page.get_by_role("button", name="保存绑定").click()
            response = await binding_response.value
            assert response.status == 200, await response.text()
            binding = await response.json()
            await expect(page.get_by_text(file_path, exact=True).first).to_be_visible(timeout=10000)
            await _shot(page, path=str(evidence_dir / "automation-binding-review.png"), full_page=True)
            await page.locator(".workspace-mode-tab").nth(1).click()
            await expect(page.locator(".monaco-editor")).to_be_visible(timeout=30000)
            run_file_button = page.locator(".studio-editor-tabs button.studio-tool.is-primary")
            await expect(run_file_button).to_be_enabled(timeout=10000)
            async with page.expect_response(
                lambda response: response.url.endswith("/api/runs") and response.request.method == "POST"
            ) as run_response:
                await run_file_button.click()
            started_response = await run_response.value
            assert started_response.status == 201, await started_response.text()
            test_run = await started_response.json()
        assert binding["workspace_id"] == project_id
        for _ in range(300):
            if test_run["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.1)
            test_run = (await client.get(f"/api/runs/{test_run['id']}")).json()
        assert test_run["status"] == "PASSED", {
            key: test_run.get(key) for key in ("status", "log_output", "executions")
        }
        assert test_run["browser_sessions"] and test_run["external_artifacts"]
        foreign_project = await client.post("/api/projects", json={"name": "Round 3 isolated project"})
        assert foreign_project.status_code == 201, foreign_project.text
        foreign_id = foreign_project.json()["id"]
        assert (await client.get("/api/discovery/runs", params={"project_id": foreign_id})).json() == []
        assert (await client.get("/api/discovery/runs", params={"project_id": project_id})).json()[0]["id"] == run_id
        foreign_binding = await client.post(
            f"/api/test-cases/{case_id}/binding",
            json={
                "test_case_id": case_id,
                "workspace_id": foreign_id,
                "nodeid": nodeid,
                "file_path": file_path,
                "status": "ACTIVE",
            },
        )
        assert foreign_binding.status_code == 422

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
            context = await browser.new_context()
            for font_host in ("https://fonts.googleapis.com/**", "https://fonts.gstatic.com/**"):
                await context.route(font_host, lambda route: route.abort())
            token = client.headers["Authorization"].removeprefix("Bearer ")
            await context.add_init_script(
                f"localStorage.setItem('ai-qa.auth-token', {json.dumps(token)}); "
                "localStorage.setItem('ai-qa.language', 'en');"
            )
            page = await context.new_page()
            debug_session_responses = []
            debug_api_events = []
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(f"pageerror: {error}"))
            page.on(
                "console",
                lambda message: page_errors.append(f"console: {message.text}") if message.type == "error" else None,
            )
            page.on(
                "requestfailed",
                lambda request: page_errors.append(f"requestfailed: {request.url} {request.failure}"),
            )
            page.on(
                "request",
                lambda request: (
                    debug_api_events.append(f"{request.method} {request.url}") if "/debug/" in request.url else None
                ),
            )
            page.on(
                "response",
                lambda response: (
                    debug_session_responses.append(response)
                    if "/debug/sessions" in response.url and response.request.method == "POST"
                    else None
                ),
            )
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover")
            try:
                await page.get_by_role("button", name="Quality Map").wait_for(timeout=20000)
            except Exception as error:
                raise AssertionError(
                    f"Quality Map UI absent at {page.url}; body={(await page.locator('body').inner_text())[:1200]}"
                ) from error
            await page.get_by_role("button", name="Quality Map").click()
            async with page.expect_response(
                lambda response: f"/discovery/runs/{run_id}/coverage/refresh" in response.url
            ):
                await page.get_by_role("button", name="刷新覆盖率").click()
            await page.get_by_text("已根据最新测试和自动化结果刷新覆盖率。").wait_for(timeout=10000)
            refreshed = (await client.get(f"/api/discovery/runs/{run_id}")).json()
            row = next(item for item in refreshed["result"]["coverage"] if item["feature_id"] == feature_id)
            automation = next(item for item in row["automation"] if item["automation_binding_id"] == binding["id"])
            assert case_id in row["test_case_ids"]
            assert row["last_run_id"] == test_run["id"] and row["last_run_status"] == "PASSED"
            assert row["coverage_status"] == "VERIFIED"
            assert automation["last_run_id"] == test_run["id"] and automation["last_run_status"] == "PASSED"
            evidence_dir = EVIDENCE_ROOT / "round-3/evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            await _shot(page, path=str(evidence_dir / "quality-map-verified.png"), full_page=True)
            await page.reload(wait_until="commit")
            await page.get_by_role("button", name="Quality Map").click()
            verified_row = page.locator(".qd-coverage-table tbody tr").filter(has_text="Search").first
            await verified_row.get_by_text("已验证", exact=True).wait_for(timeout=15000)
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/workspace/{foreign_id}?view=discover")
            await page.get_by_label("应用起始 URL").wait_for(timeout=15000)
            assert await page.locator(".qd-run-card").count() == 0
            assert not await page.get_by_text(run_id, exact=True).count()
            await _shot(page, path=str(evidence_dir / "isolated-project-empty.png"), full_page=True)

            # Round 4 baseline review: tour the existing product routes with persisted project data.
            from datetime import UTC, datetime

            screenshot_phase = os.environ.get("ROUND4_SCREENSHOT_PHASE", "before")
            assert screenshot_phase in {"before", "after"}
            round4_evidence = EVIDENCE_ROOT / "round-4/evidence" / screenshot_phase
            round4_evidence.mkdir(parents=True, exist_ok=True)
            # Ids must stay within the 36-character column contract the PostgreSQL schema enforces.
            failed_run_id, failed_execution_id = (f"r4-{uuid4().hex}" for _ in range(2))
            failure_id = f"r4-{uuid4().hex}"
            now = datetime.now(UTC)
            async with test_db_session() as session:
                session.add(
                    TestRunORM(
                        id=failed_run_id,
                        project_id=project_id,
                        workspace_id=project_id,
                        status="FAILED",
                        total=1,
                        failed=1,
                        nodeids=[nodeid],
                        started_at=now,
                        finished_at=now,
                    )
                )
                session.add(
                    TestExecutionORM(
                        id=failed_execution_id,
                        run_id=failed_run_id,
                        nodeid=nodeid,
                        status="FAILED",
                        error_message="AssertionError: expected checkout to succeed",
                        stack_trace="AssertionError: expected checkout to succeed\\n  at test_failure.py:12",
                        failure_category="ASSERTION_ERROR",
                        started_at=now,
                        finished_at=now,
                    )
                )
                session.add(
                    FailureRecordORM(
                        id=failure_id,
                        run_id=failed_run_id,
                        execution_id=failed_execution_id,
                        test_nodeid=nodeid,
                        test_name="test_search_product",
                        classification="ASSERTION_ERROR",
                        exception_type="AssertionError",
                        error_message="expected checkout to succeed",
                        stack_trace="AssertionError: expected checkout to succeed\\n  at test_failure.py:12",
                        failing_locator='get_by_role("button", name="Checkout")',
                    )
                )
                await session.commit()
            persisted_failures = await client.get(f"/api/failures?project_id={project_id}&limit=8")
            assert persisted_failures.status_code == 200
            assert any(item["id"] == failure_id for item in persisted_failures.json())

            viewport_matrix = [
                ("1920x1080", 1920, 1080),
                ("1440x900", 1440, 900),
                ("1366x768", 1366, 768),
                ("390x844", 390, 844),
            ]
            page_routes = [
                ("dashboard", "/"),
                ("projects", "/projects"),
                ("project-overview", f"/projects/{project_id}?tab=overview"),
                ("project-knowledge", f"/projects/{project_id}?tab=knowledge"),
                ("project-coverage", f"/projects/{project_id}?tab=coverage"),
                ("requirements", f"/projects/{project_id}/requirements"),
                (
                    "requirement-workspace",
                    f"/workspace/{project_id}?view=requirement&requirementId={requirement_id}",
                ),
                ("quality-discovery", f"/workspace/{project_id}?view=discover"),
                ("test-cases", f"/workspace/{project_id}?view=cases&caseId={case_id}"),
                ("automation-studio", f"/workspace/{project_id}?view=code&caseId={case_id}&file={file_path}"),
                ("live-browser", f"/workspace/{project_id}?view=browser&caseId={case_id}"),
                (
                    "debugger",
                    f"/workspace/{project_id}?view=debug&stage=automation&caseId={case_id}&failureId={failure_id}&file={file_path}&nodeid={nodeid}",
                ),
                (
                    "run-result",
                    f"/workspace/{project_id}?view=results&stage=result&runId={test_run['id']}&caseId={case_id}",
                ),
                (
                    "failure-repair",
                    f"/workspace/{project_id}?view=results&stage=failure&runId={failed_run_id}&failureId={failure_id}&caseId={case_id}",
                ),
            ]
            await _goto_app(page, f"http://127.0.0.1:{vite_port}/")
            await page.get_by_text("平台总览", exact=True).wait_for(timeout=45000)
            await page.get_by_role("link", name="项目管理").click()
            await page.wait_for_url("**/projects")
            await page.get_by_role("heading", name="QA 项目").first.wait_for(timeout=15000)
            await _shot(page, path=str(round4_evidence / "project-navigation-click.png"), full_page=True)
            route_metrics = []
            error_surfaces_seen: list[str] = []
            for name, path in page_routes:
                print(f"ROUND4_ROUTE={name}", flush=True)
                await page.set_viewport_size({"width": 1440, "height": 900})
                await _goto_app(page, f"http://127.0.0.1:{vite_port}{path}")
                await page.locator("body").wait_for(state="visible")
                await page.wait_for_function(
                    """() => !["正在读取项目上下文…", "正在读取项目数据", "正在加载代码工作台…", "正在加载浏览器录制器…", "正在加载文件内容...", "正在加载...", "正在加载…", "加载中…", "加载中...", "Loading…", "Loading..."].some((label) => document.body.innerText.includes(label))""",
                    timeout=20000,
                )
                if name == "run-result":
                    await page.get_by_text("PASSED", exact=True).first.wait_for(timeout=15000)
                elif name == "failure-repair":
                    await (
                        page.locator(".failure-error-detail")
                        .filter(has_text="expected checkout to succeed")
                        .wait_for(state="visible", timeout=15000)
                    )
                    await page.locator("details.failure-raw-details").first.locator("summary").wait_for(timeout=15000)
                    await _shot(
                        page,
                        path=str(round4_evidence / "failure-repair-1440x900.png"),
                        full_page=True,
                    )
                    raw_error = page.locator("details.failure-raw-details").first
                    await raw_error.locator("summary").click()
                    await (
                        raw_error.locator("pre.failure-evidence-code")
                        .filter(has_text="expected checkout to succeed")
                        .wait_for(state="visible", timeout=10000)
                    )
                    await _shot(
                        page,
                        path=str(round4_evidence / "failure-repair-evidence-expanded-1440x900.png"),
                        full_page=True,
                    )
                text = (await page.locator("body").inner_text())[:500]
                dimensions = await page.evaluate(
                    "({width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight})"
                )
                assert dimensions["scrollWidth"] <= dimensions["width"], f"Horizontal overflow on {name}: {dimensions}"
                studio_auto_loaded = None
                debug_session = None
                if name == "debugger":
                    for _ in range(150):
                        if debug_session_responses:
                            break
                        await asyncio.sleep(0.1)
                    assert debug_session_responses, (
                        f"Failure deep link did not start a debugger session at {page.url}; "
                        f"body={(await page.locator('body').inner_text())[:1200]}; "
                        f"debug network={debug_api_events}"
                    )
                    debug_response = debug_session_responses[-1]
                    assert debug_response.status == 200, await debug_response.text()
                    debug_session = await debug_response.json()
                    assert debug_session["workspace_id"] == project_id
                    assert debug_session["nodeid"] == nodeid
                    assert debug_session["failure_id"] == failure_id
                if name == "automation-studio":
                    try:
                        await page.wait_for_function(
                            """() => (document.querySelector('.monaco-editor .view-lines')?.textContent ?? '').replace(/[\\s\\u00a0]+/g, '').includes('deftest_discovered_search():')""",
                            timeout=5000,
                        )
                        studio_auto_loaded = True
                    except Exception:
                        studio_auto_loaded = False
                route_metrics.append(
                    {
                        "page": name,
                        "path": page.url,
                        "body_sample": text,
                        **dimensions,
                        "file_loaded_without_click": studio_auto_loaded,
                        "debug_session_status": debug_session["status"] if debug_session else None,
                    }
                )
                if name != "failure-repair":
                    await _shot(page, path=str(round4_evidence / f"{name}-1440x900.png"), full_page=True)
                if name == "automation-studio":
                    file_contents = await client.get(f"/api/workspaces/{project_id}/file", params={"path": file_path})
                    assert file_contents.status_code == 200
                    assert "def test_discovered_search" in file_contents.json()["content"]
                    file_row = page.locator(".tree-node:not(.is-folder)").filter(has_text=Path(file_path).name).first
                    await file_row.wait_for(timeout=15000)
                    if not studio_auto_loaded:
                        await file_row.click()
                    try:
                        await page.wait_for_function(
                            """() => (document.querySelector('.monaco-editor .view-lines')?.textContent ?? '').replace(/[\\s\\u00a0]+/g, '').includes('deftest_discovered_search():')""",
                            timeout=20000,
                        )
                    except Exception as error:
                        editor_text = (
                            await page.locator(".monaco-editor").inner_text()
                            if await page.locator(".monaco-editor").count()
                            else "<missing>"
                        )
                        raise AssertionError(
                            f"Selected file was not rendered in Monaco; API content length="
                            f"{len(file_contents.json()['content'])}; editor={editor_text[:500]}"
                        ) from error
                    await _shot(
                        page,
                        path=str(round4_evidence / "automation-studio-file-opened.png"),
                        full_page=True,
                    )

            # Round 6: a failed request must not look like "no data". Each surface is forced
            # through a 500 and must show its own alert banner.
            error_surfaces = [
                ("runs", "/runs", "**/api/runs**", "测试运行列表加载失败"),
                ("failures", "/failures", "**/api/failures**", "测试失败记录加载失败"),
                ("security", "/security", "**/api/users**", "操作失败"),
            ]
            for surface, path, pattern, expected in error_surfaces:
                print(f"ROUND6_ERROR_SURFACE={surface}", flush=True)
                await page.set_viewport_size({"width": 1440, "height": 900})

                async def _fail(route, _pattern=pattern):
                    await route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"forced failure for the round 6 error-surface check"}',
                    )

                await page.route(pattern, _fail)
                try:
                    await _goto_app(page, f"http://127.0.0.1:{vite_port}{path}")
                    banner = page.locator('[role="alert"]').filter(has_text=expected).first
                    await banner.wait_for(state="visible", timeout=25000)
                    await _shot(
                        page,
                        path=str(round4_evidence / f"error-surface-{surface}-1440x900.png"),
                        full_page=True,
                    )
                    error_surfaces_seen.append(surface)
                finally:
                    await page.unroute(pattern)

            # Round 6: the release modal must explain a rejected write instead of closing silently.
            print("ROUND6_ERROR_SURFACE=release-create", flush=True)
            await page.set_viewport_size({"width": 1440, "height": 900})

            async def _fail_release(route):
                await route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"detail":"forced failure for the round 6 release check"}',
                )

            await page.route("**/api/releases", _fail_release)
            try:
                await _goto_app(page, f"http://127.0.0.1:{vite_port}/quality")
                await page.wait_for_selector("body")
                await page.locator(".tab-btn").filter(has_text="发布与门禁").first.click()
                await page.get_by_role("button", name="新建发布").first.click()
                modal = page.locator(".modal-overlay")
                await modal.wait_for(state="visible", timeout=15000)
                inputs = modal.locator("input")
                await inputs.nth(0).fill("v0.0.1-round6")
                await inputs.nth(1).fill("Round 6 forced failure")
                await modal.locator('button[type="submit"]').click()
                await (
                    modal.locator('[role="alert"]').filter(has_text="操作失败").wait_for(state="visible", timeout=15000)
                )
                await _shot(
                    page,
                    path=str(round4_evidence / "error-surface-release-create-1440x900.png"),
                    full_page=True,
                )
                error_surfaces_seen.append("release-create")
            finally:
                await page.unroute("**/api/releases")

            responsive_pages = [
                "dashboard",
                "project-overview",
                "requirement-workspace",
                "quality-discovery",
                "test-cases",
                "automation-studio",
                "live-browser",
                "debugger",
                "run-result",
                "failure-repair",
            ]
            for viewport_name, width, height in viewport_matrix:
                await page.set_viewport_size({"width": width, "height": height})
                for name in responsive_pages:
                    print(f"ROUND4_VIEWPORT={viewport_name} {name}", flush=True)
                    path = next(path for route_name, path in page_routes if route_name == name)
                    if name == "debugger":
                        # Responsive evidence uses the idle debugger; the deep link in the route pass starts a real session.
                        path = f"/workspace/{project_id}?view=debug&caseId={case_id}"
                    await _goto_app(page, f"http://127.0.0.1:{vite_port}{path}")
                    await page.locator("body").wait_for(state="visible")
                    await page.wait_for_function(
                        """() => !["正在读取项目上下文…", "正在读取项目数据", "正在加载代码工作台…", "正在加载浏览器录制器…", "正在加载文件内容...", "正在加载...", "正在加载…", "加载中…", "加载中...", "Loading…", "Loading..."].some((label) => document.body.innerText.includes(label))""",
                        timeout=20000,
                    )
                    if name == "run-result":
                        await page.get_by_text("PASSED", exact=True).first.wait_for(timeout=15000)
                    elif name == "automation-studio":
                        for attempt in range(2):
                            try:
                                await page.wait_for_function(
                                    """() => (document.querySelector('.monaco-editor .view-lines')?.textContent ?? '').replace(/[\\s\\u00a0]+/g, '').includes('deftest_discovered_search():')""",
                                    timeout=30000,
                                )
                                break
                            except Exception as error:
                                if attempt:
                                    raise AssertionError(
                                        f"Studio editor never rendered the saved file at {viewport_name}; "
                                        f"body={(await page.locator('body').inner_text())[:800]}; "
                                        f"monaco={await page.locator('.monaco-editor').count()}; "
                                        f"{page_errors[-8:]}"
                                    ) from error
                                await page.reload(wait_until="commit")
                    dimensions = await page.evaluate(
                        "({width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight})"
                    )
                    assert dimensions["scrollWidth"] <= dimensions["width"], (
                        f"Horizontal overflow on {name} at {viewport_name}: {dimensions}"
                    )
                    route_metrics.append({"page": name, "viewport": viewport_name, "path": page.url, **dimensions})
                    await _shot(
                        page,
                        path=str(round4_evidence / f"{name}-{viewport_name}-responsive.png"),
                        full_page=True,
                    )
                    if name == "requirement-workspace":
                        for graph_tab, graph_label in (
                            ("mind", "需求思维图"),
                            ("scenario", "场景关系图"),
                            ("knowledge", "知识关系"),
                        ):
                            await page.get_by_role("button", name=graph_label, exact=True).click()
                            if graph_tab == "knowledge":
                                await page.locator(".knowledge-viewport").wait_for(timeout=15000)
                            await page.wait_for_timeout(250)
                            await _shot(
                                page,
                                path=str(round4_evidence / f"requirement-{graph_tab}-{viewport_name}.png"),
                                full_page=True,
                            )

            requirement_tab_names = {
                "overview": "概览",
                "analysis": "分析与决策",
                "mind": "需求思维图",
                "scenario": "场景关系图",
                "knowledge": "知识关系",
                "coverage": "覆盖与缺口",
                "design": "场景设计",
            }
            for tab_name, label in requirement_tab_names.items():
                print(f"ROUND4_REQUIREMENT_TAB={tab_name}", flush=True)
                await page.set_viewport_size({"width": 1440, "height": 900})
                await _goto_app(
                    page,
                    f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=requirement&requirementId={requirement_id}",
                )
                await page.get_by_role("button", name=label, exact=True).click()
                await page.wait_for_timeout(250)
                route_metrics.append({"page": f"requirement-{tab_name}", "path": page.url})
                await _shot(
                    page,
                    path=str(round4_evidence / f"requirement-{tab_name}-1440x900.png"),
                    full_page=True,
                )

            graph_interactions = []
            await page.set_viewport_size({"width": 1440, "height": 900})
            await _goto_app(
                page,
                f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=requirement&requirementId={requirement_id}",
            )
            await page.get_by_role("button", name="知识关系", exact=True).click()
            await page.locator(".knowledge-viewport").wait_for(timeout=15000)
            await page.get_by_role("textbox", name="搜索 ID、内容或状态").fill("not-a-real-entity")
            await page.get_by_text("没有匹配的节点", exact=False).wait_for(timeout=5000)
            graph_interactions.append("knowledge graph search shows empty state")
            await page.get_by_role("textbox", name="搜索 ID、内容或状态").fill("")
            await page.get_by_label("筛选实体类型").select_option("requirement")
            assert await page.locator(".knowledge-node").count() > 0
            graph_interactions.append("knowledge graph kind filter returned requirement nodes")
            await page.get_by_label("筛选实体类型").select_option("")
            await page.get_by_role("button", name="适配画布").click()
            await page.locator(".knowledge-node-select").first.click()
            await page.locator("details.knowledge-source summary").click()
            graph_interactions.append("node focus, fit, details and upstream/downstream panel clicked")
            await _shot(page, path=str(round4_evidence / "knowledge-graph-controls-1440x900.png"), full_page=True)
            (round4_evidence / "page-matrix.json").write_text(
                json.dumps(
                    {"pages": route_metrics, "graph_interactions": graph_interactions}, ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
            await browser.close()

        report = {
            "discovery_run_id": run_id,
            "project_id": project_id,
            "target": target,
            "states": len(run["result"]["states"]),
            "actions": len(run["result"]["actions"]),
            "evidence_items": sum(
                bool(state.get("evidence_id")) + bool(state.get("screenshot_evidence_id"))
                for state in run["result"]["states"]
            ),
            "feature_id": feature_id,
            "requirement_id": requirement_id,
            "test_design_id": case["test_design_id"],
            "quality_risk_id": requirement_risks[0]["id"],
            "quality_risk_severity": requirement_risks[0]["severity"],
            "scenario_id": scenario["id"],
            "scenario_status": design["status"],
            "discovered_feature": True,
            "scenario_generated": True,
            "scenario_reviewed_in_ui": True,
            "test_case_created": True,
            "case_visible_and_selected_in_ui": True,
            "test_case_id": case_id,
            "automation_binding_id": binding["id"],
            "automation_binding_status": binding["status"],
            "automation_bound": binding["status"] == "ACTIVE",
            "binding_created_via_ui": True,
            "playwright_run_id": test_run["id"],
            "playwright_status": test_run["status"],
            "run_started_via_ui": True,
            "executed": bool(test_run["executions"]),
            "latest_execution_passed": row["last_run_status"] == "PASSED",
            "coverage_status": row["coverage_status"],
            "isolated_project_id": foreign_id,
            "isolated_project_discovery_runs": 0,
            "round6_error_surfaces": error_surfaces_seen,
        }
        (evidence_dir / "discovery-to-coverage.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("ROUND3_REAL_BROWSER_DISCOVERY_TO_COVERAGE=" + json.dumps(report, ensure_ascii=False))
    finally:
        app.dependency_overrides.pop(get_quality_discovery_service, None)
        app.dependency_overrides.pop(get_ai_service, None)
        app.dependency_overrides.pop(get_platform_health_service, None)
        monkeypatch.setattr(AIService, "generate_test_cases", real_generate)
        if vite_log and not vite_log.closed:
            vite_log.close()
        if vite_process and vite_process.poll() is None:
            vite_process.terminate()
            try:
                vite_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                vite_process.kill()
        if api_server and api_task and not api_task.done():
            api_server.should_exit = True
            try:
                await asyncio.wait_for(api_task, timeout=5)
            except TimeoutError:
                api_server.force_exit = True
                api_task.cancel()
                await asyncio.gather(api_task, return_exceptions=True)
        website.shutdown()
        website.server_close()
        website_thread.join(timeout=2)
