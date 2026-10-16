from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest
from app.repositories.task_unit_of_work import TaskRepositoryScopeFactory
from app.services.ai_settings_service import AISettingsService
from app.services.decision_settings_service import DecisionSettingsService
from app.services.workspace_service import WorkspaceService
from app.settings import settings
from qa_core.ai.registry import AIProviderRegistry

#: Bundled Playwright Chromium by default; hosts where it cannot execute (e.g. some macOS builds)
#: set AI_QA_ACCEPTANCE_BROWSER_CHANNEL=chrome to use an installed system browser.
BROWSER_CHANNEL = os.environ.get("AI_QA_ACCEPTANCE_BROWSER_CHANNEL") or None


@pytest.fixture
def local_http_url():
    servers = []

    def serve(html: str) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/"

    yield serve
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_live_ai_jev_repair_requires_approval_and_exact_rerun(
    client, test_db_session, tmp_path, local_http_url, monkeypatch
):
    if os.getenv("AI_QA_RUN_LIVE_JEV_ACCEPTANCE") != "1":
        pytest.skip("set AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1 to run the real-provider acceptance")

    repository_scope = TaskRepositoryScopeFactory()
    ai_config = await AISettingsService(repository_scope)._effective_config()
    decision_config = await DecisionSettingsService(repository_scope).get_runtime_config()
    if ai_config.provider == "fake" or not ai_config.api_key:
        pytest.skip("a real AI provider and configured key are required for this acceptance")
    if not decision_config.enabled or not decision_config.api_key:
        pytest.skip("enabled Jev runtime and configured key are required for this acceptance")

    monkeypatch.setattr(settings, "failure_auto_repair_mode", "AUTO")

    original_runtime = AIProviderRegistry._runtime_config
    original_middleware = AIProviderRegistry._middleware
    original_artifact_dir = settings.artifact_storage_dir
    settings.artifact_storage_dir = tmp_path / "artifacts"
    settings.artifact_storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        await AISettingsService(repository_scope).load_runtime_config()

        html = (
            "<main><h1>Checkout</h1><p>Review your order and complete checkout.</p>"
            "<button>Cancel order</button>"
            '<button aria-label="Complete order" '
            "onclick=\"document.querySelector('#status').textContent='ORDER_COMPLETED'\">Complete order</button>"
            '<p id="status">Pending</p></main>'
        )
        page_url = local_http_url(html)
        source = f"""from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

PAGE_URL = {page_url!r}


def test_workflow():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        page = browser.new_page()
        try:
            page.goto(PAGE_URL, wait_until="domcontentloaded")
            try:
                page.locator("#purchase-now").click(timeout=1500)
            except PlaywrightTimeoutError as error:
                raise AssertionError("Checkout action did not complete because its previous target was missing.") from error
            assert page.locator("#status").inner_text() == "ORDER_COMPLETED"
        finally:
            browser.close()
"""
        project_response = await client.post(
            "/api/projects", json={"name": "Live locator acceptance", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        source_response = await client.put(
            f"/api/workspaces/{project_id}/file",
            json={"path": "tests/test_workflow.py", "content": source},
        )
        assert source_response.status_code == 200, source_response.text

        workspace = WorkspaceService().get_workspace_dir(project_id)
        temp_root = tmp_path / "pytest-temp"
        temp_root.mkdir()
        run_environment = {
            **os.environ,
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "TMPDIR": str(temp_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        def run_pytest(name: str) -> subprocess.CompletedProcess[str]:
            basetemp = temp_root / name
            assert not basetemp.exists()
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--basetemp={basetemp}",
                    "tests/test_workflow.py::test_workflow",
                ],
                cwd=workspace,
                env=run_environment,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )

        original_result = await asyncio.to_thread(run_pytest, "baseline")
        original_output = original_result.stdout + original_result.stderr
        assert original_result.returncode != 0 and "purchase-now" in original_output, original_output[-2500:]

        original_response = await client.post(
            "/api/runs",
            json={
                "project_id": project_id,
                "workspace_id": project_id,
                "nodeids": ["tests/test_workflow.py::test_workflow"],
                "runner_type": "LOCAL",
                "requested_by": "Live AI + Jev locator acceptance",
            },
        )
        assert original_response.status_code == 201, original_response.text
        original_run_id = original_response.json()["id"]
        original_run = original_response.json()
        for _ in range(120):
            if original_run["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                break
            await asyncio.sleep(0.25)
            status_response = await client.get(f"/api/runs/{original_run_id}")
            assert status_response.status_code == 200, status_response.text
            original_run = status_response.json()
        assert original_run["status"] == "FAILED", original_run
        browser_sessions = original_run.get("browser_sessions") or []
        assert any(
            session.get("page_evidence", {}).get("controls")
            for session in browser_sessions
            if isinstance(session.get("page_evidence"), dict)
        ), browser_sessions
        failures_response = await client.get(f"/api/failures?project_id={project_id}")
        assert failures_response.status_code == 200, failures_response.text
        failure = next(
            item
            for item in failures_response.json()
            if item["run_id"] == original_run_id and item["test_nodeid"] == "tests/test_workflow.py::test_workflow"
        )
        failure_id = failure["id"]

        # AUTO may start a real analysis, but a human Apply request must authorize any source write.
        analysis = None
        for _ in range(240):
            history_response = await client.get(f"/api/failures/{failure_id}/analyses")
            assert history_response.status_code == 200, history_response.text
            history = history_response.json()
            analysis = history[0] if history else None
            if analysis and (
                analysis["result"].get("verification_run_id")
                or analysis["status"] in {"COMPLETED", "FAILED", "CANCELLED"}
            ):
                break
            await asyncio.sleep(0.5)
        assert analysis is not None, "Failure did not automatically start an analysis"
        assert analysis["result"].get("automatic_triggered") is True, analysis
        assert analysis["result"].get("verification_run_id") is None, analysis
        workflow_events = analysis["events"]
        completed_events = [event for event in workflow_events if event["type"] == "run.completed"]
        assert completed_events, analysis
        stream_types = {event["type"] for event in workflow_events}
        assert {
            "repair.started",
            "diagnosis.completed",
            "decision.completed",
            "candidate.verified",
            "patch.generated",
        } <= stream_types, stream_types
        completed = completed_events[-1]
        result = completed["metadata"]
        proposal = result.get("repair_proposal") or {}
        assert completed["type"] == "run.completed"
        assert result["initial_classification"] == "ASSERTION_FAILURE"
        assert result["resolved_classification"] == "LOCATOR_CHANGED"
        assert result["classification_source"] == "AI_DIAGNOSIS"
        assert result["diagnosis"]["provider"] not in {"", "fake"}
        assert result["diagnosis"]["fallback_used"] is False
        assert proposal.get("provider") == "jev" and proposal.get("ai_fallback_used") is False, {
            "decision": proposal.get("decision_summary"),
            "verification_reason": proposal.get("verification_reason"),
            "trace": [
                {"stage": event.get("stage"), "message": event.get("message"), "metadata": event.get("metadata")}
                for event in proposal.get("execution_trace", [])
            ],
            "inspection": [
                event.get("metadata")
                for event in workflow_events
                if event.get("type") == "workflow.step" and event.get("stage") == "inspection"
            ],
        }
        assert proposal["verified"] is True and proposal["code_diff"]
        assert result["repair_state"] == "PATCH_READY"
        assert result["changes_applied"] is False
        assert proposal["proposed_locator"] != 'page.locator("#purchase-now")'
        model_event = next(event for event in workflow_events if event["type"] == "model.completed")
        decision_summary = proposal.get("decision_summary") or {}
        print(
            "REAL_AI_JEV_ACCEPTANCE="
            + json.dumps(
                {
                    "ai": {
                        "provider": model_event.get("metadata", {}).get("provider"),
                        "model": model_event.get("metadata", {}).get("model"),
                        "latency_ms": model_event.get("duration_ms"),
                        "fallback": model_event.get("metadata", {}).get("fallback_used"),
                        "classification": result["resolved_classification"],
                    },
                    "jev": {
                        "provider": proposal.get("provider"),
                        "model": decision_summary.get("model"),
                        "decision": decision_summary.get("candidate_id"),
                        "locator": decision_summary.get("selected_locator"),
                        "confidence": decision_summary.get("confidence"),
                        "latency_ms": decision_summary.get("latency_ms"),
                        "fallback": proposal.get("ai_fallback_used"),
                        "fallback_reason": decision_summary.get("fallback_reason"),
                        "playwright_verified": proposal.get("verified"),
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        analysis_id = result["analysis_id"]
        assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
        apply_response = await client.post(
            f"/api/failures/{failure_id}/analyses/{analysis_id}/apply",
            json={
                "file_path": proposal["file_path"],
                "old_code": proposal["source_locator"] or proposal["old_locator"],
                "new_code": proposal["proposed_locator"],
            },
        )
        assert apply_response.status_code == 200, apply_response.text
        patched_source = await WorkspaceService().read_file(project_id, "tests/test_workflow.py")
        assert 'page.locator("#purchase-now")' not in patched_source
        assert proposal["proposed_locator"] in patched_source

        verification_response = await client.post(f"/api/failures/{failure_id}/analyses/{analysis_id}/verification/run")
        assert verification_response.status_code == 200, verification_response.text
        verification_run_id = verification_response.json()["id"]
        assert verification_response.json()["nodeids"] == ["tests/test_workflow.py::test_workflow"]
        final_run = verification_response.json()
        for _ in range(120):
            await asyncio.sleep(0.25)
            status_response = await client.get(f"/api/runs/{verification_run_id}")
            assert status_response.status_code == 200, status_response.text
            final_run = status_response.json()
            if final_run["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                break
        assert final_run["status"] == "PASSED", final_run

        history = await client.get(f"/api/failures/{failure_id}/analyses")
        assert history.status_code == 200, history.text
        verified_analysis = next(item for item in history.json() if item["id"] == analysis_id)
        assert verified_analysis["result"]["verified"] is True
        assert verified_analysis["result"]["verification_run_status"] == "PASSED"
        recorded_types = {event["type"] for event in verified_analysis["events"]}
        assert {"patch.applied", "verification.started", "verification.completed", "repair.verified"} <= recorded_types
    finally:
        settings.artifact_storage_dir = original_artifact_dir
        AIProviderRegistry.configure_runtime(original_runtime)
        AIProviderRegistry.set_middleware(original_middleware)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_live_ai_jev_failure_repair_through_browser_ui(
    client, test_db_session, tmp_path, local_http_url, monkeypatch
):
    """Drive diagnosis, apply, and verification through the real React UI and API."""
    if os.getenv("AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE") != "1":
        pytest.skip("set AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1 to run the real browser acceptance")

    from playwright.async_api import async_playwright
    from uvicorn import Config, Server

    repository_scope = TaskRepositoryScopeFactory()
    ai_config = await AISettingsService(repository_scope)._effective_config()
    decision_config = await DecisionSettingsService(repository_scope).get_runtime_config()
    if ai_config.provider == "fake" or not ai_config.api_key:
        pytest.skip("a real AI provider and configured key are required for this acceptance")
    if not decision_config.enabled or not decision_config.api_key:
        pytest.skip("enabled Jev runtime and configured key are required for this acceptance")

    import app.settings as settings_module

    current_config = settings_module.get_config()
    repair_config = current_config.repair.model_copy(update={"mode": "ASSISTED", "auto_start_on_failure": False})
    monkeypatch.setattr(
        settings_module.config_manager,
        "_config",
        current_config.model_copy(update={"repair": repair_config}),
    )
    original_runtime = AIProviderRegistry._runtime_config
    original_middleware = AIProviderRegistry._middleware
    original_artifact_dir = settings.artifact_storage_dir
    settings.artifact_storage_dir = tmp_path / "artifacts"
    settings.artifact_storage_dir.mkdir(parents=True, exist_ok=True)
    api_server = None
    api_task = None
    vite_process = None
    browser = None
    try:
        await AISettingsService(repository_scope).load_runtime_config()

        html = (
            "<main><h1>Checkout</h1><p>Review your order and complete checkout.</p>"
            "<button>Cancel order</button><button>View order</button>"
            '<button aria-label="Complete order" '
            "onclick=\"document.querySelector('#status').textContent='ORDER_COMPLETED'\">Continue</button>"
            '<button>Return</button><p id="status">Pending</p></main>'
        )
        page_url = local_http_url(html)
        source = f"""from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

PAGE_URL = {page_url!r}


def test_workflow():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        page = browser.new_page()
        try:
            page.goto(PAGE_URL, wait_until="domcontentloaded")
            try:
                page.locator("#purchase-now").click(timeout=1500)
            except PlaywrightTimeoutError as error:
                raise AssertionError("Checkout action did not complete because its previous target was missing.") from error
            assert page.locator("#status").inner_text() == "ORDER_COMPLETED"
        finally:
            browser.close()
"""
        project_response = await client.post(
            "/api/projects", json={"name": "Live browser locator acceptance", "bootstrap_workspace": False}
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        source_response = await client.put(
            f"/api/workspaces/{project_id}/file",
            json={"path": "tests/test_workflow.py", "content": source},
        )
        assert source_response.status_code == 200, source_response.text
        workspace = WorkspaceService().get_workspace_dir(project_id)
        temp_root = tmp_path / "pytest-temp"
        temp_root.mkdir()
        run_environment = {
            **os.environ,
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "TMPDIR": str(temp_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--basetemp={temp_root / 'baseline'}",
                "tests/test_workflow.py::test_workflow",
            ],
            cwd=workspace,
            env=run_environment,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        baseline_output = baseline.stdout + baseline.stderr
        assert baseline.returncode != 0 and "purchase-now" in baseline_output, baseline_output[-2500:]
        original_response = await client.post(
            "/api/runs",
            json={
                "project_id": project_id,
                "workspace_id": project_id,
                "nodeids": ["tests/test_workflow.py::test_workflow"],
                "runner_type": "LOCAL",
                "requested_by": "Live AI + Jev browser acceptance",
            },
        )
        assert original_response.status_code == 201, original_response.text
        original_run = original_response.json()
        for _ in range(120):
            if original_run["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                break
            await asyncio.sleep(0.25)
            response = await client.get(f"/api/runs/{original_run['id']}")
            assert response.status_code == 200, response.text
            original_run = response.json()
        assert original_run["status"] == "FAILED", original_run
        browser_sessions = original_run.get("browser_sessions") or []
        assert any(
            session.get("page_evidence", {}).get("controls")
            for session in browser_sessions
            if isinstance(session.get("page_evidence"), dict)
        ), browser_sessions
        failures_response = await client.get(f"/api/failures?project_id={project_id}")
        assert failures_response.status_code == 200, failures_response.text
        failure = next(item for item in failures_response.json() if item["run_id"] == original_run["id"])

        def free_port() -> int:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                return int(listener.getsockname()[1])

        api_port, vite_port = free_port(), free_port()
        from app.main import app

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
        vite_env = {**os.environ, "VITE_DEV_API_TARGET": f"http://127.0.0.1:{api_port}"}
        vite_process = subprocess.Popen(
            [node, str(vite_entry), "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
            cwd=web_root,
            env=vite_env,
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

        token = client.headers["Authorization"].removeprefix("Bearer ")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
            page = await browser.new_page()
            page.set_default_timeout(180_000)
            await page.add_init_script(
                "localStorage.setItem('ai-qa.auth-token', "
                + json.dumps(token)
                + "); localStorage.setItem('ai-qa.selected-project', "
                + json.dumps(project_id)
                + "); localStorage.setItem('ai-qa.ui-preferences', "
                + json.dumps({"theme": "system", "language": "en", "startPage": "/", "defaultProjectId": None})
                + ");"
            )
            await page.goto(f"http://127.0.0.1:{vite_port}/failures/{failure['id']}", wait_until="commit")
            diagnose_button = page.get_by_role("button", name=re.compile(r"Run AI diagnosis|运行 AI 诊断", re.I))
            try:
                await diagnose_button.wait_for(state="visible", timeout=60_000)
            except Exception as error:
                raise AssertionError(
                    f"Failure action is not available at {page.url}; page text: "
                    f"{(await page.locator('body').inner_text())[:3000]}"
                ) from error
            screenshot_dir = Path(os.getenv("AI_QA_FAILURE_UI_SCREENSHOT_DIR", tmp_path / "failure-ui-review"))
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            for width, name in ((1440, "desktop"), (768, "tablet"), (360, "mobile")):
                await page.set_viewport_size({"width": width, "height": 900})
                await page.screenshot(path=str(screenshot_dir / f"{name}.png"), full_page=True)
                has_horizontal_overflow = await page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth"
                )
                assert not has_horizontal_overflow, f"Failure UI overflows horizontally at {width}px"
            await page.set_viewport_size({"width": 1440, "height": 900})
            await diagnose_button.click()
            analysis_id = ""
            state = {}
            for _ in range(180):
                await asyncio.sleep(1)
                history_response = await client.get(f"/api/failures/{failure['id']}/analyses")
                assert history_response.status_code == 200, history_response.text
                rows = history_response.json()
                if rows:
                    candidate = rows[0]
                    analysis_id = candidate["id"]
                    workflow_response = await client.get(
                        f"/api/failures/{failure['id']}/repair-workflow?analysis_id={analysis_id}"
                    )
                    assert workflow_response.status_code == 200, workflow_response.text
                    state = workflow_response.json()
                    if state["state"] in {
                        "PATCH_READY",
                        "VERIFYING_FIX",
                        "VERIFIED",
                        "FAILED",
                        "ROLLED_BACK",
                        "BLOCKED",
                    }:
                        break
            assert analysis_id, "The browser flow did not create an analysis"
            proposal = state.get("repair_proposal") or {}
            decision_summary = proposal.get("decision_summary") or {}
            result = candidate.get("result") or {}
            diagnosis = result.get("diagnosis") or {}
            selection = result.get("selection") or {}
            print(
                "REAL_AI_JEV_BROWSER_ACCEPTANCE="
                + json.dumps(
                    {
                        "analysis_status": candidate.get("status"),
                        "workflow_state": state.get("state"),
                        "repair_state": result.get("repair_state"),
                        "resolved_classification": result.get("resolved_classification"),
                        "ai_provider": diagnosis.get("provider"),
                        "ai_model": diagnosis.get("model"),
                        "ai_fallback_used": diagnosis.get("fallback_used"),
                        "jev_provider": proposal.get("provider") or decision_summary.get("provider"),
                        "jev_fallback_used": proposal.get("ai_fallback_used"),
                        "verification_run_status": state.get("verification_run_status"),
                        "proposal_present": bool(proposal),
                        "selection": {
                            key: selection.get(key)
                            for key in ("provider", "fallback_reason", "selected_candidate", "confidence")
                        },
                        "decision_events": [
                            {
                                "status": event.get("status"),
                                "message": event.get("message"),
                                "metadata": {
                                    key: (event.get("metadata") or {}).get(key)
                                    for key in ("provider", "fallback_reason", "selected_candidate", "confidence")
                                },
                            }
                            for event in candidate.get("events", [])
                            if event.get("type") == "decision.completed"
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            if state["state"] == "BLOCKED":
                assert "APPLY" not in state.get("allowed_actions", []), state
                if not proposal:
                    selection = candidate.get("result", {}).get("selection") or {}
                    if selection.get("fallback_reason") == "below_minimum_confidence":
                        confidence = selection.get("confidence")
                        assert candidate["status"] == "COMPLETED", candidate
                        assert candidate["result"].get("repair_state") == "BLOCKED", candidate
                        assert isinstance(confidence, (int, float))
                        assert confidence < decision_config.minimum_confidence, selection
                        assert state.get("verification_run_id") is None, state
                        assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
                        fallback_note = page.locator(".failure-workflow-fallback-note")
                        await fallback_note.wait_for(state="visible", timeout=30_000)
                        fallback_text = await fallback_note.inner_text()
                        assert (
                            f"Jev confidence was {confidence:.2f}" in fallback_text
                            or f"Jev 本次置信度为 {confidence:.2f}" in fallback_text
                        ), fallback_text
                        return
                    assert candidate["status"] == "FAILED", {
                        "status": candidate["status"],
                        "repair_state": candidate.get("result", {}).get("repair_state"),
                        "initial_classification": candidate.get("result", {}).get("initial_classification"),
                        "resolved_classification": candidate.get("result", {}).get("resolved_classification"),
                        "selection": candidate.get("result", {}).get("selection"),
                        "events": [
                            {key: event.get(key) for key in ("type", "stage", "status", "message")}
                            for event in candidate.get("events", [])
                        ],
                        "workflow_state": {
                            key: state.get(key)
                            for key in ("state", "block_reason", "allowed_actions", "verification_run_id")
                        },
                    }
                    assert any(event["type"] == "run.failed" for event in candidate["events"]), candidate
                    assert state.get("verification_run_id") is None, state
                    assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
                    return
                fallback_reason = decision_summary.get("fallback_reason") or proposal.get("verification_reason")
                assert fallback_reason, proposal
                assert state.get("verification_run_id") is None, state
                assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
                if fallback_reason == "below_minimum_confidence":
                    confidence = decision_summary.get("confidence")
                    assert confidence is not None and confidence < decision_config.minimum_confidence, decision_summary
                    fallback_note = page.locator(".failure-workflow-fallback-note")
                    await fallback_note.wait_for(state="visible", timeout=30_000)
                    fallback_text = await fallback_note.inner_text()
                    assert (
                        f"Jev confidence was {confidence:.2f}" in fallback_text
                        or f"Jev 本次置信度为 {confidence:.2f}" in fallback_text
                    ), fallback_text
                return

            assert proposal.get("provider") == "jev", proposal
            assert proposal.get("ai_fallback_used") is False, proposal
            assert state["state"] == "PATCH_READY", state
            assert "APPLY" in state.get("allowed_actions", []), state
            assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
            await page.screenshot(path=str(screenshot_dir / "patch-ready.png"), full_page=True)
            apply_button = page.get_by_role("button", name=re.compile(r"Apply repair|应用修复", re.I))
            await apply_button.wait_for(state="visible", timeout=30_000)
            await apply_button.click()
            for _ in range(30):
                await asyncio.sleep(1)
                workflow_response = await client.get(
                    f"/api/failures/{failure['id']}/repair-workflow?analysis_id={analysis_id}"
                )
                assert workflow_response.status_code == 200, workflow_response.text
                state = workflow_response.json()
                if "VERIFY" in state.get("allowed_actions", []) or state["state"] == "BLOCKED":
                    break
            assert state["state"] == "PATCH_APPLIED", state
            assert "VERIFY" in state.get("allowed_actions", []), state
            patched_source = await WorkspaceService().read_file(project_id, "tests/test_workflow.py")
            assert 'page.locator("#purchase-now")' not in patched_source
            assert proposal["proposed_locator"] in patched_source
            verify_button = page.locator("button.failure-primary-action")
            await verify_button.wait_for(state="visible", timeout=30_000)
            verify_label = await verify_button.inner_text()
            assert re.search(r"Verify repair|验证修复", verify_label, re.I), verify_label
            await verify_button.click()
            for _ in range(180):
                if state["state"] in {"VERIFIED", "FAILED", "ROLLED_BACK", "BLOCKED"}:
                    break
                await asyncio.sleep(1)
                workflow_response = await client.get(
                    f"/api/failures/{failure['id']}/repair-workflow?analysis_id={analysis_id}"
                )
                assert workflow_response.status_code == 200, workflow_response.text
                state = workflow_response.json()
            if state["state"] == "FAILED":
                for _ in range(20):
                    await asyncio.sleep(0.5)
                    await client.get(f"/api/failures/{failure['id']}/analyses")
                    workflow_response = await client.get(
                        f"/api/failures/{failure['id']}/repair-workflow?analysis_id={analysis_id}"
                    )
                    assert workflow_response.status_code == 200, workflow_response.text
                    state = workflow_response.json()
                    if state["state"] == "ROLLED_BACK":
                        break
            if state["state"] == "ROLLED_BACK":
                assert state["verified"] is False, state
                assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
                await page.get_by_text(
                    re.compile(r"Retest failed · repair rolled back|复测未通过 · 修复已回滚", re.I)
                ).wait_for(state="visible", timeout=30_000)
                await page.get_by_text(
                    re.compile(
                        r"The original test did not pass\. The system automatically rolled back the patch and restored the original file\.|原失败用例未通过，系统已自动回滚补丁，原文件内容已恢复。",
                        re.I,
                    )
                ).wait_for(state="visible", timeout=30_000)
                await (
                    page.locator(".failure-workflow-result-status")
                    .get_by_text(re.compile(r"Retest: Retest did not pass|复测状态：实际复测未通过", re.I))
                    .wait_for(state="visible", timeout=30_000)
                )
                return
            assert state["state"] == "VERIFIED" and state["verified"] is True, state
            assert state["verification_run_status"] == "PASSED", state
            await page.screenshot(path=str(screenshot_dir / "verification-in-progress.png"), full_page=True)
            await (
                page.locator(".failure-workflow-result-status")
                .get_by_text(re.compile(r"Retest: Actual verification passed|复测状态：实际复测已通过", re.I))
                .wait_for(state="visible", timeout=30_000)
            )
            assert await page.get_by_role("button", name=re.compile(r"Apply repair|应用修复", re.I)).count() == 0
            history = await client.get(f"/api/failures/{failure['id']}/analyses")
            assert history.status_code == 200, history.text
            analysis = next(item for item in history.json() if item["id"] == analysis_id)
            recorded_types = {event["type"] for event in analysis["events"]}
            required_events = {
                "patch.applied",
                "verification.started",
                "verification.completed",
                "repair.verified",
            }
            assert required_events <= recorded_types, {
                "missing": sorted(required_events - recorded_types),
                "result": {
                    key: analysis.get("result", {}).get(key)
                    for key in ("repair_state", "verification_run_id", "verification_run_status", "verified")
                },
                "events": [
                    {key: event.get(key) for key in ("type", "step_id", "status", "metadata")}
                    for event in analysis.get("events", [])
                    if event.get("type", "").startswith(("patch.", "verification.", "repair."))
                ],
            }
            assert 'page.locator("#purchase-now")' not in await WorkspaceService().read_file(
                project_id, "tests/test_workflow.py"
            )
            print(
                "REAL_AI_JEV_BROWSER_VERIFICATION="
                + json.dumps(
                    {
                        "workflow_state": state["state"],
                        "verified": state["verified"],
                        "verification_run_status": state["verification_run_status"],
                        "ai_provider": diagnosis.get("provider"),
                        "ai_fallback_used": diagnosis.get("fallback_used"),
                        "jev_provider": proposal.get("provider"),
                        "jev_fallback_used": proposal.get("ai_fallback_used"),
                    },
                    sort_keys=True,
                )
            )

            rolled_back = await client.post(f"/api/failures/{failure['id']}/analyses/{analysis_id}/rollback")
            assert rolled_back.status_code == 200, rolled_back.text
            assert await WorkspaceService().read_file(project_id, "tests/test_workflow.py") == source
            actual_history = (await client.get(f"/api/failures/{failure['id']}/analyses")).json()
            actual_analysis = next(item for item in actual_history if item["id"] == analysis_id)
            assert actual_analysis["result"]["repair_state"] == "ROLLED_BACK"
            assert any(event["type"] == "repair.rolled_back" for event in actual_analysis["events"])
            await page.reload(wait_until="domcontentloaded")
            try:
                await page.get_by_text(
                    re.compile(
                        r"Code change: Rolled back · original code restored|代码修改：已回滚，原代码已恢复", re.I
                    )
                ).wait_for(state="visible", timeout=30_000)
                await page.screenshot(path=str(screenshot_dir / "real-rollback.png"), full_page=True)
                print(
                    "REAL_REPAIR_ROLLBACK="
                    + json.dumps({"analysis_id": analysis_id, "state": "ROLLED_BACK", "original_source_restored": True})
                )
            except Exception as error:
                body = (await page.locator("body").inner_text())[:3000]
                raise AssertionError(f"Persisted real rollback was not visible at {page.url}: {body}") from error
    finally:
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
            await asyncio.gather(api_task, return_exceptions=True)
        settings.artifact_storage_dir = original_artifact_dir
        AIProviderRegistry.configure_runtime(original_runtime)
        AIProviderRegistry.set_middleware(original_middleware)
