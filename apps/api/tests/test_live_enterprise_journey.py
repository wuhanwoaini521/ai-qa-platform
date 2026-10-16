"""Opt-in acceptance against real providers and an isolated local test website."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from urllib.request import urlopen

import pytest
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_settings_service import AISettingsService
from test_live_locator_repair_acceptance import local_http_url as local_http_url

pytestmark = [pytest.mark.integration, pytest.mark.slow]

#: Bundled Playwright Chromium by default; hosts where it cannot execute (e.g. some macOS builds)
#: set AI_QA_ACCEPTANCE_BROWSER_CHANNEL=chrome to use an installed system browser.
BROWSER_CHANNEL = os.environ.get("AI_QA_ACCEPTANCE_BROWSER_CHANNEL") or None


@pytest.fixture(autouse=True)
def live_acceptance_only():
    if os.getenv("AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE") != "1":
        pytest.skip("set AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 for real-provider acceptance")
    assert importlib.metadata.version("playwright") == "1.62.0"


async def test_real_requirement_to_execution_and_evidence(client, local_http_url, tmp_path, monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    await AISettingsService(TaskRepositoryScopeFactory()).load_runtime_config()
    target = local_http_url(
        '<main><h1>Verification panel</h1><p id="status">Ready</p>'
        "<button onclick=\"document.querySelector('#status').textContent='Verified'\">Verify</button></main>"
    )
    project = await client.post("/api/projects", json={"name": "Enterprise live requirement acceptance"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    created = await client.post(
        "/api/requirements",
        json={
            "project_id": project_id,
            "title": "Verification panel status transition",
            "description": "A local verification panel initially shows Ready. Clicking Verify changes the status to Verified. No account or external writes are involved.",
            "acceptance_criteria": "AC-001: On load the status is Ready.\nAC-002: Clicking Verify changes the status to Verified.",
        },
    )
    assert created.status_code == 201, created.text
    requirement_id = created.json()["id"]
    analyzed = await client.post(f"/api/requirements/{requirement_id}/lifecycle/analyze/stream")
    assert analyzed.status_code == 200, analyzed.text
    requirement = (await client.get(f"/api/requirements/{requirement_id}")).json()
    document = requirement["qa_model"]
    history = document["history"][-1]
    assert history["status"] == "SUCCESS", {key: history.get(key) for key in ("status", "error_code", "error")}
    assert history["provider"] not in {"", "fake"}
    assert any(item["provider"] == "jev" and not item["fallback_used"] for item in history["decisions"]), history[
        "decisions"
    ]
    designs = await client.post(f"/api/requirements/{requirement_id}/lifecycle/designs")
    assert designs.status_code == 200 and designs.json(), designs.text
    positive = [item for item in designs.json() if (item.get("scenario_model") or {}).get("path_type") != "negative"]
    assert positive, "The model did not produce an executable positive scenario for the explicit acceptance criteria"
    design_id = positive[0]["id"]
    adopted = await client.post(f"/api/test-designs/{design_id}/lifecycle/case")
    assert adopted.status_code == 200, adopted.text
    test_case = adopted.json()
    assert test_case["requirement_id"] == requirement_id
    source = f"""from playwright.sync_api import sync_playwright

def test_verification_panel():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        try:
            page = browser.new_page()
            page.goto({target!r})
            assert page.locator("#status").inner_text() == "Ready"
            page.get_by_role("button", name="Verify", exact=True).click()
            assert page.locator("#status").inner_text() == "Verified"
        finally:
            browser.close()
"""
    file_path = "tests/test_verification_panel.py"
    nodeid = f"{file_path}::test_verification_panel"
    saved = await client.put(f"/api/workspaces/{project_id}/file", json={"path": file_path, "content": source})
    assert saved.status_code == 200, saved.text
    bound = await client.post(
        f"/api/test-cases/{test_case['id']}/binding",
        json={
            "test_case_id": test_case["id"],
            "workspace_id": project_id,
            "nodeid": nodeid,
            "file_path": file_path,
            "status": "ACTIVE",
        },
    )
    assert bound.status_code == 200, bound.text
    response = await client.post(
        "/api/runs", json={"project_id": project_id, "workspace_id": project_id, "nodeids": [nodeid]}
    )
    assert response.status_code == 201, response.text
    run = response.json()
    for _ in range(240):
        if run["status"] not in {"QUEUED", "RUNNING"}:
            break
        await asyncio.sleep(0.25)
        run = (await client.get(f"/api/runs/{run['id']}")).json()
    assert run["status"] == "PASSED", {key: run.get(key) for key in ("status", "log_output")}
    assert len(run["executions"]) == 1 and run["executions"][0]["nodeid"] == nodeid
    assert run["browser_sessions"] and run["external_artifacts"]
    graph = (
        await client.get(f"/api/projects/{project_id}/knowledge", params={"requirement_id": requirement_id})
    ).json()
    assert any(node["kind"] == "run" for node in graph["nodes"])
    assert any(node["kind"] == "case" and node["id"].endswith(test_case["id"]) for node in graph["nodes"])
    reopened = (await client.get(f"/api/requirements/{requirement_id}")).json()
    assert reopened["qa_model"]["history"][-1]["id"] == history["id"]
    print(
        "REAL_REQUIREMENT_JOURNEY="
        + json.dumps(
            {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "case_id": test_case["id"],
                "run_id": run["id"],
                "provider": history["provider"],
                "model": history["model"],
                "decisions": history["decisions"],
                "status": run["status"],
                "evidence_count": len(run["external_artifacts"]),
            },
            ensure_ascii=False,
        )
    )


async def test_real_local_discovery_preserves_target_and_project_scope(
    client, test_db_session, local_http_url, tmp_path, monkeypatch
):
    import app.settings as settings_module
    from app.container import get_browser_runtime, get_quality_discovery_service
    from app.main import app
    from app.services.decision_service import DecisionService
    from app.services.quality_discovery_service import QualityDiscoveryService
    from app.services.workspace_service import WorkspaceService

    workspace_dir = tmp_path / "workspaces"
    monkeypatch.setattr(settings_module.settings, "artifact_storage_dir", tmp_path / "artifacts")
    config = settings_module.get_config()
    monkeypatch.setattr(
        settings_module.config_manager,
        "_config",
        config.model_copy(
            update={
                "app": config.app.model_copy(update={"workspace_storage_dir": workspace_dir}),
                "discovery": config.discovery.model_copy(
                    update={"max_actions": 2, "max_states": 4, "max_runtime_minutes": 1}
                ),
            }
        ),
    )
    await AISettingsService(TaskRepositoryScopeFactory()).load_runtime_config()
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=get_browser_runtime(),
        decisions=DecisionService(repository_scope=TaskRepositoryScopeFactory()),
        workspace_service=WorkspaceService(base_dir=workspace_dir),
    )
    app.dependency_overrides[get_quality_discovery_service] = lambda: service
    target = local_http_url(
        "<main><h1>Product catalog</h1><p>Canvas tote</p>"
        "<button onclick=\"document.querySelector('#details').hidden=false\">Show product details</button>"
        '<section id="details" hidden><h2>Canvas tote details</h2><p>Price 20.00, available in blue.</p></section></main>'
    )
    project = (await client.post("/api/projects", json={"name": "Enterprise real browser discovery"})).json()
    created = await client.post(
        "/api/discovery/runs", json={"project_id": project["id"], "start_url": target, "mode": "EXPLORE"}
    )
    assert created.status_code == 202, created.text
    run = created.json()
    api_server = None
    api_task = None
    vite_process = None
    browser = None
    try:
        for _ in range(300):
            if run["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.5)
            run = (await client.get(f"/api/discovery/runs/{run['id']}")).json()
        assert run["status"] in {"COMPLETED", "BUDGET_EXHAUSTED"}, {
            key: run.get(key) for key in ("status", "error", "progress")
        }
        assert run["project_id"] == project["id"] and run["start_url"] == target
        assert run["result"]["states"] and any(item.get("evidence_id") for item in run["result"]["states"])
        assert run["result"]["ai"]["calls"] > 0 and run["result"]["ai"]["provider"] != "fake"
        assert any(
            item.get("provider") == "jev" and not item.get("fallback_used")
            for item in run["result"].get("decisions", [])
        )
        assert run["result"]["features"]
        assert isinstance(run["result"].get("quality_map"), dict)
        assert run["result"]["quality_map"]["coverage"] == run["result"]["coverage"]
        assert run["result"]["quality_map"]["workspace_test_scan"] == run["result"]["workspace_test_scan"]
        assert run["result"]["workspace_test_scan"]["status"] in {"AVAILABLE", "UNAVAILABLE", "NOT_CONFIGURED"}
        assert not any(feature.get("test_case_ids") for feature in run["result"]["features"])
        print(
            "REAL_BROWSER_DISCOVERY="
            + json.dumps(
                {
                    "run_id": run["id"],
                    "project_id": project["id"],
                    "start_url": target,
                    "status": run["status"],
                    "progress": run["progress"],
                    "ai": run["result"]["ai"],
                    "jev": run["result"]["jev"],
                },
                ensure_ascii=False,
            )
        )

        test_gap = next(gap for gap in run["result"]["gaps"] if gap["category"] == "TEST_MISSING")
        draft = await client.post(
            f"/api/discovery/runs/{run['id']}/gaps/{test_gap['id']}/actions/create_requirement_draft"
        )
        assert draft.status_code == 200, draft.text
        generated = await client.post(f"/api/discovery/runs/{run['id']}/gaps/{test_gap['id']}/actions/generate_tests")
        assert generated.status_code == 200, generated.text
        generated_cases = generated.json()["test_cases"]
        assert generated_cases
        case_id = generated.json()["test_case_ids"][0]
        usage = (await client.get("/api/ai/usage", params={"limit": 200, "feature": "test_case_generation"})).json()
        generation_invocation = next(item for item in usage["invocations"] if item["task"] == "test_case_generation")
        assert generation_invocation["provider"] not in {"", "fake"} and not generation_invocation["fallback_used"]

        nodeid = "tests/test_discovered_details.py::test_discovered_product_details"
        file_path = "tests/test_discovered_details.py"
        source = f"""from playwright.sync_api import sync_playwright


def test_discovered_product_details():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        try:
            page = browser.new_page()
            page.goto({target!r})
            page.get_by_role("button", name="Show product details", exact=True).click()
            assert page.get_by_role("heading", name="Canvas tote details", exact=True).is_visible()
        finally:
            browser.close()
"""
        saved = await client.put(f"/api/workspaces/{project['id']}/file", json={"path": file_path, "content": source})
        assert saved.status_code == 200, saved.text
        binding = await client.post(
            f"/api/test-cases/{case_id}/binding",
            json={
                "test_case_id": case_id,
                "workspace_id": project["id"],
                "nodeid": nodeid,
                "file_path": file_path,
                "status": "ACTIVE",
            },
        )
        assert binding.status_code == 200, binding.text
        created_run = await client.post(
            "/api/runs", json={"project_id": project["id"], "workspace_id": project["id"], "nodeids": [nodeid]}
        )
        assert created_run.status_code == 201, created_run.text
        test_run = created_run.json()
        for _ in range(240):
            if test_run["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.25)
            test_run = (await client.get(f"/api/runs/{test_run['id']}")).json()
        assert test_run["status"] == "PASSED", {key: test_run.get(key) for key in ("status", "log_output")}
        assert test_run["browser_sessions"] and test_run["external_artifacts"]
        refreshed = await client.post(f"/api/discovery/runs/{run['id']}/coverage/refresh")
        assert refreshed.status_code == 200, refreshed.text
        feature_coverage = next(
            row for row in refreshed.json()["result"]["coverage"] if row["feature_id"] == test_gap["item_id"]
        )
        assert case_id in feature_coverage["test_case_ids"]
        assert feature_coverage["last_run_id"] == test_run["id"]
        assert feature_coverage["last_run_status"] == "PASSED"
        assert feature_coverage["coverage_status"] == "VERIFIED"
        automation = next(
            item for item in feature_coverage["automation"] if item["automation_binding_id"] == binding.json()["id"]
        )
        assert automation["nodeid"] == nodeid
        assert automation["last_run_id"] == test_run["id"] and automation["last_run_status"] == "PASSED"
        print(
            "REAL_DISCOVERY_TO_COVERAGE="
            + json.dumps(
                {
                    "discovery_run_id": run["id"],
                    "feature_id": test_gap["item_id"],
                    "requirement_id": draft.json()["requirement_id"],
                    "test_case_id": case_id,
                    "ai_generation": generation_invocation,
                    "automation_binding_id": binding.json()["id"],
                    "nodeid": nodeid,
                    "test_run_id": test_run["id"],
                    "test_status": test_run["status"],
                    "coverage_status": feature_coverage["coverage_status"],
                    "discovery_ai": run["result"]["ai"],
                    "discovery_jev": run["result"]["jev"],
                },
                ensure_ascii=False,
            )
        )

        from app.main import app
        from playwright.async_api import async_playwright
        from uvicorn import Config, Server

        def free_port() -> int:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                return int(listener.getsockname()[1])

        api_port, vite_port = free_port(), free_port()
        api_server = Server(Config(app, host="127.0.0.1", port=api_port, lifespan="off", log_level="warning"))
        api_task = asyncio.create_task(api_server.serve())
        for _ in range(100):
            if api_server.started:
                break
            if api_task.done():
                raise RuntimeError("Uvicorn exited before the API became ready")
            await asyncio.sleep(0.1)
        assert api_server.started, "API server did not start"

        web_root = Path(__file__).resolve().parents[3] / "apps" / "web"
        vite_entry = web_root / "node_modules" / "vite" / "bin" / "vite.js"
        node = "node.exe" if os.name == "nt" else "node"
        vite_process = subprocess.Popen(
            [node, str(vite_entry), "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
            cwd=web_root,
            env={**os.environ, "VITE_DEV_API_TARGET": f"http://127.0.0.1:{api_port}"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        for _ in range(150):
            if vite_process.poll() is not None:
                raise RuntimeError(f"Vite exited with status {vite_process.returncode}")
            try:
                await asyncio.to_thread(urlopen, f"http://127.0.0.1:{vite_port}", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.2)
        else:
            raise RuntimeError("Vite did not become ready")

        page_errors: list[str] = []
        console_errors: list[str] = []
        api_errors: list[str] = []
        health_response: asyncio.Future = asyncio.get_running_loop().create_future()
        refresh_response: asyncio.Future = asyncio.get_running_loop().create_future()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(60_000)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

            def record_response(response) -> None:
                if "/api/" in response.url and response.status >= 400:
                    api_errors.append(f"{response.status} {response.url}")
                if "/api/ai/system-health" in response.url and not health_response.done():
                    health_response.set_result(response)
                if (
                    response.request.method == "POST"
                    and "/coverage/refresh" in response.url
                    and not refresh_response.done()
                ):
                    refresh_response.set_result(response)

            page.on("response", record_response)
            token = client.headers["Authorization"].removeprefix("Bearer ")
            await page.add_init_script(
                "localStorage.setItem('ai-qa.auth-token', "
                + json.dumps(token)
                + "); localStorage.setItem('ai-qa.selected-project', "
                + json.dumps(project["id"])
                + "); localStorage.setItem('ai-qa.ui-preferences', "
                + json.dumps({"theme": "system", "language": "en", "startPage": "/", "defaultProjectId": None})
                + ");"
            )
            await page.goto(
                f"http://127.0.0.1:{vite_port}/workspace/{project['id']}?stage=discover&view=discover",
                wait_until="domcontentloaded",
            )
            health_result = await asyncio.wait_for(health_response, timeout=30)
            assert health_result.status == 200
            health_payload = await health_result.json()
            print(
                "REAL_UI_PLATFORM_HEALTH="
                + json.dumps(
                    {
                        "status": health_payload.get("status"),
                        "components": [
                            {key: component.get(key) for key in ("component", "status", "operational_state")}
                            for component in health_payload.get("components", [])
                        ],
                    },
                    ensure_ascii=False,
                )
            )
            refresh_name = re.compile(r"^(Refresh coverage|刷新覆盖率)$")
            refresh = page.get_by_role("button", name=refresh_name)
            try:
                await refresh.wait_for(state="visible")
            except Exception as error:
                body = (await page.locator("body").inner_text())[:3000]
                await page.screenshot(path=str(tmp_path / "discovery-coverage-ui-failure.png"), full_page=True)
                raise AssertionError(
                    f"Refresh button missing at {page.url}; body={body!r}; page_errors={page_errors!r}; "
                    f"console_errors={console_errors!r}; api_errors={api_errors!r}"
                ) from error
            assert await page.get_by_text(re.compile(r"^(Verified|已验证)$")).count() > 0
            repository_root = Path(__file__).resolve().parents[3]
            screenshot_dir = repository_root / ".ai-runs/enterprise-continuation/round-2/screenshots" / run["id"]
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_dir / "discovery-coverage-before-refresh.png"), full_page=True)
            await refresh.click()
            refresh_result = await asyncio.wait_for(refresh_response, timeout=15)
            assert refresh_result.status == 200
            assert not api_errors, api_errors
            refreshed_status = page.get_by_role("status").get_by_text(
                re.compile(
                    r"^(Coverage refreshed from the latest test and automation results\.|已根据最新测试和自动化结果刷新覆盖率。)$"
                )
            )
            await refreshed_status.wait_for(state="visible")
            assert await page.get_by_text(re.compile(r"^(Verified|已验证)$")).count() > 0
            await page.screenshot(path=str(screenshot_dir / "discovery-coverage-after-refresh.png"), full_page=True)
            for width, name in ((768, "tablet"), (360, "mobile")):
                await page.set_viewport_size({"width": width, "height": 900})
                await page.get_by_role("button", name=refresh_name).scroll_into_view_if_needed()
                assert not await page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                if width == 360:
                    table = page.locator(".qd-table-scroll")
                    assert await table.evaluate("element => element.scrollWidth > element.clientWidth")
                    await table.evaluate("element => { element.scrollLeft = element.scrollWidth; }")
                    last_column = page.locator(".qd-coverage-table th").last
                    box = await last_column.bounding_box()
                    assert box and 0 <= box["x"] < 360 and box["x"] + box["width"] <= 360
                await page.screenshot(path=str(screenshot_dir / f"discovery-coverage-{name}.png"), full_page=True)
            assert not page_errors, page_errors
            assert not console_errors, console_errors
            assert not api_errors, api_errors
            print(
                "REAL_DISCOVERY_COVERAGE_UI="
                + json.dumps(
                    {
                        "refresh_status": "visible",
                        "coverage": "VERIFIED",
                        "screenshots": str(screenshot_dir),
                        "system_health": health_payload.get("status"),
                    }
                )
            )
            await browser.close()
            browser = None
    finally:
        app.dependency_overrides.pop(get_quality_discovery_service, None)
        if browser is not None:
            await browser.close()
        if vite_process is not None and vite_process.poll() is None:
            vite_process.terminate()
            try:
                await asyncio.to_thread(vite_process.wait, 10)
            except subprocess.TimeoutExpired:
                vite_process.kill()
                await asyncio.to_thread(vite_process.wait, 5)
        if api_server is not None and api_task is not None:
            api_server.should_exit = True
            await asyncio.wait_for(api_task, timeout=10)
        if run["status"] in {"QUEUED", "RUNNING", "PAUSED"}:
            await service.stop(run["id"])
        tasks = list(service._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
