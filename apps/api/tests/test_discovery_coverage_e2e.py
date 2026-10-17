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

import pytest
import uvicorn
from app.container import (
    get_ai_service,
    get_browser_runtime,
    get_platform_health_service,
    get_quality_discovery_service,
)
from app.main import app
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


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


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
        evidence_dir = Path(__file__).resolve().parents[3] / ".ai-runs/night-continuation/round-3/evidence"
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

        evidence_dir = Path(__file__).resolve().parents[3] / ".ai-runs/night-continuation/round-3/evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
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
            await page.goto(f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover", wait_until="commit")
            try:
                await page.get_by_label("应用起始 URL").wait_for(timeout=20000)
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
            await page.screenshot(path=str(evidence_dir / "requirement-draft-review.png"), full_page=True)
            await page.get_by_role("button", name="场景设计").click()
            await page.get_by_text(scenario_title, exact=False).wait_for(timeout=10000)
            await page.get_by_text(f"Derived from Discovery run {run_id}", exact=False).wait_for(timeout=10000)
            await page.screenshot(path=str(evidence_dir / "scenario-review.png"), full_page=True)
            await page.goto(f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover", wait_until="commit")
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
            await page.screenshot(path=str(evidence_dir / "test-case-review.png"), full_page=True)
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
        browser = pw.chromium.launch(headless=True)
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
            await page.screenshot(path=str(evidence_dir / "automation-binding-review.png"), full_page=True)
            await page.get_by_role("button", name="结果").click()
            async with page.expect_response(
                lambda response: response.url.endswith("/api/runs") and response.request.method == "POST"
            ) as run_response:
                await page.get_by_role("button", name="开始运行").click()
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
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            token = client.headers["Authorization"].removeprefix("Bearer ")
            await context.add_init_script(
                f"localStorage.setItem('ai-qa.auth-token', {json.dumps(token)}); "
                "localStorage.setItem('ai-qa.language', 'en');"
            )
            page = await context.new_page()
            await page.goto(f"http://127.0.0.1:{vite_port}/workspace/{project_id}?view=discover", wait_until="commit")
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
            evidence_dir = Path(__file__).resolve().parents[3] / ".ai-runs/night-continuation/round-3/evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(evidence_dir / "quality-map-verified.png"), full_page=True)
            await page.reload(wait_until="commit")
            await page.get_by_role("button", name="Quality Map").click()
            verified_row = page.locator(".qd-coverage-table tbody tr").filter(has_text="Search").first
            await verified_row.get_by_text("已验证", exact=True).wait_for(timeout=15000)
            await page.goto(f"http://127.0.0.1:{vite_port}/workspace/{foreign_id}?view=discover", wait_until="commit")
            await page.get_by_label("应用起始 URL").wait_for(timeout=15000)
            assert await page.locator(".qd-run-card").count() == 0
            assert not await page.get_by_text(run_id, exact=True).count()
            await page.screenshot(path=str(evidence_dir / "isolated-project-empty.png"), full_page=True)
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
