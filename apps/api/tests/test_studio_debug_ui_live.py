from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
import pytest
from app.main import app as fastapi_app
from app.services.ai_settings_service import AISettingsService
from app.settings import config_manager, get_config, settings
from playwright.async_api import async_playwright, expect
from uvicorn import Config, Server

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LIVE_STUDIO_ENABLED = os.getenv("AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE") == "1"
BROWSER_CHANNEL = os.environ.get("AI_QA_ACCEPTANCE_BROWSER_CHANNEL") or None


@pytest.fixture(autouse=True)
def _workspace_storage_setting_is_restored():
    initial_workspace_dir = settings.workspace_storage_dir
    try:
        yield
    finally:
        settings.workspace_storage_dir = initial_workspace_dir
        assert settings.workspace_storage_dir == initial_workspace_dir


@pytest.fixture
async def disabled_external_health_probes():
    original = get_config()
    try:
        config_manager.replace_for_test(
            original.model_copy(
                update={
                    "ai": original.ai.model_copy(update={"enabled": False}),
                    "jev": original.jev.model_copy(update={"enabled": False}),
                }
            )
        )
        await AISettingsService().load_runtime_config()
        yield
    finally:
        config_manager.replace_for_test(original)
        await AISettingsService().load_runtime_config()


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def _wait_for_http(url: str, process: subprocess.Popen[bytes] | None = None) -> None:
    deadline = monotonic() + 60
    async with httpx.AsyncClient(timeout=1) as http:
        while monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"Vite exited with code {process.returncode}")
            try:
                response = await http.get(url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Service did not become ready: {url}")


async def _debug_record(client, session_id: str) -> dict:
    response = await client.get(f"/api/debug/sessions/{session_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def _wait_debug_status(client, session_id: str, statuses: set[str]) -> dict:
    deadline = monotonic() + 30
    while monotonic() < deadline:
        record = await _debug_record(client, session_id)
        if str(record["status"]).upper() in statuses:
            return record
        await asyncio.sleep(0.2)
    raise AssertionError(f"Debug session {session_id} did not reach {statuses}")


async def _wait_for_breakpoint(client, workspace_id: str, path: str, line_number: int) -> dict:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        response = await client.get(f"/api/workspaces/{workspace_id}/breakpoints")
        assert response.status_code == 200, response.text
        breakpoint = next(
            (
                item
                for item in response.json()
                if item["file_path"] == path and item["line_number"] == line_number and item["enabled"]
            ),
            None,
        )
        if breakpoint:
            return breakpoint
        await asyncio.sleep(0.1)
    raise AssertionError(f"Studio did not save breakpoint {path}:{line_number}")


async def _wait_for_run(client, run_id: str) -> dict:
    deadline = monotonic() + 60
    terminal = {"PASSED", "FAILED", "CANCELLED", "SKIPPED"}
    while monotonic() < deadline:
        response = await client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if str(run["status"]).upper() in terminal:
            return run
        await asyncio.sleep(0.25)
    raise AssertionError(f"Studio run {run_id} did not finish")


def _localized(*labels: str) -> re.Pattern[str]:
    return re.compile(r"^(?:" + "|".join(re.escape(label) for label in labels) + r")$")


@pytest.mark.asyncio
async def test_api_client_workspace_directory_is_scoped(client):
    assert settings.workspace_storage_dir.is_dir()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not LIVE_STUDIO_ENABLED,
    reason="Set AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1 to run the real UI/debugpy acceptance",
)
async def test_real_studio_edit_debug_run_and_failure_acceptance(
    client, tmp_path: Path, disabled_external_health_probes, monkeypatch: pytest.MonkeyPatch
):
    """Exercise Studio through Vite, Chromium, the authenticated API, and real debugpy."""
    assert importlib.metadata.version("playwright") == "1.62.0"

    monkeypatch.setattr(settings, "runtime_dir", tmp_path / "runtime")
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")
    evidence_root = Path(os.getenv("AI_QA_STUDIO_EVIDENCE_DIR", tmp_path / "evidence")).resolve()
    evidence_dir = evidence_root / f"studio-{uuid4().hex[:10]}"
    screenshot_dir = evidence_dir / "screenshots"
    log_dir = evidence_dir / "logs"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    project_response = await client.post(
        "/api/projects",
        json={"name": f"Studio UI acceptance {uuid4().hex[:8]}", "bootstrap_workspace": False},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    steps_path = "tests/test_studio_debug.py"
    steps_source = f"""# TODO: replace through the real Studio editor, then save.
from playwright.sync_api import expect, sync_playwright


def add_one(value):
    result = value + 1
    return result


def calculate(value):
    intermediate = add_one(value)
    return intermediate + 1


def test_debug_steps():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        try:
            page = browser.new_page()
            page.set_content("<title>Studio Debug</title><h1 id='status'>Ready</h1>")
            total = calculate(40)
            assert page.title() == "Studio Debug"
            expect(page.locator("#status")).to_have_text("Ready")
            assert total == 42
        finally:
            browser.close()
"""
    pause_path = "tests/test_studio_pause.py"
    pause_source = """import time


def test_pause_target():
    print("STUDIO_PAUSE_TARGET_RUNNING", flush=True)
    for _ in range(100):
        time.sleep(0.05)
    assert True
"""
    failure_path = "tests/test_studio_failure.py"
    failure_source = f"""import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def test_failure_has_browser_evidence():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel={BROWSER_CHANNEL!r})
        try:
            page = browser.new_page()
            page.set_content("<title>Failure target</title><h1>Observed state</h1>")
            evidence_dir = os.getenv("AI_QA_STUDIO_EVIDENCE_DIR")
            if evidence_dir:
                page.screenshot(path=str(Path(evidence_dir) / "python-browser-failure.png"))
            expect(page.get_by_role("heading", name="Expected absent")).to_be_visible(timeout=250)
        finally:
            browser.close()
"""
    for path, content in (
        (steps_path, steps_source),
        (pause_path, pause_source),
        (failure_path, failure_source),
    ):
        saved = await client.put(
            f"/api/workspaces/{project_id}/file",
            json={"path": path, "content": content},
        )
        assert saved.status_code == 200, saved.text

    api_port = _free_port()
    web_port = _free_port()
    server = Server(Config(fastapi_app, host="127.0.0.1", port=api_port, lifespan="off", log_level="warning"))
    api_task = asyncio.create_task(server.serve())
    vite_log = (log_dir / "vite.log").open("wb")
    vite: subprocess.Popen[bytes] | None = None
    browser = None
    created_sessions: list[str] = []
    api_errors: list[dict[str, object]] = []
    console_errors: list[str] = []
    run_result: dict | None = None
    session_results: list[dict] = []

    cleanup_errors: list[str] = []
    try:
        node = shutil.which("node")
        vite_script = REPOSITORY_ROOT / "apps/web/node_modules/vite/bin/vite.js"
        assert node and vite_script.is_file(), f"Expected installed Vite at {vite_script}"
        vite_environment = os.environ.copy()
        vite_environment["VITE_DEV_API_TARGET"] = f"http://127.0.0.1:{api_port}"
        vite = subprocess.Popen(
            [node, str(vite_script), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
            cwd=REPOSITORY_ROOT / "apps/web",
            env=vite_environment,
            stdout=vite_log,
            stderr=subprocess.STDOUT,
        )
        deadline = monotonic() + 30
        while not server.started and monotonic() < deadline:
            if api_task.done():
                await api_task
                raise RuntimeError("Uvicorn stopped before startup")
            await asyncio.sleep(0.1)
        assert server.started, "Uvicorn did not become ready"
        await _wait_for_http(f"http://127.0.0.1:{web_port}/", vite)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
            page = await browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(15_000)
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on(
                "console",
                lambda message: console_errors.append(message.text) if message.type == "error" else None,
            )
            page.on(
                "response",
                lambda response: (
                    api_errors.append({"status": response.status, "url": response.url})
                    if "/api/" in response.url and response.status >= 400
                    else None
                ),
            )
            token = client.headers["Authorization"].removeprefix("Bearer ")
            await page.add_init_script(
                "localStorage.setItem('ai-qa.auth-token', "
                + json.dumps(token)
                + "); localStorage.setItem('ai-qa.selected-project', "
                + json.dumps(project_id)
                + "); localStorage.setItem('ai-qa.ui-preferences', "
                + json.dumps({"theme": "system", "language": "en", "startPage": "/", "defaultProjectId": None})
                + ");"
            )
            studio_url = f"http://127.0.0.1:{web_port}/workspace/{project_id}?stage=automation&view=debug&file="
            await page.goto(studio_url + steps_path, wait_until="commit", timeout=45_000)
            editor = page.locator(".monaco-editor")
            await expect(editor).to_be_visible(timeout=30_000)
            debug_action = page.locator(".studio-editor-tabs button.studio-tool").filter(
                has_text=_localized("Debug", "调试")
            )
            await expect(debug_action).to_be_enabled(timeout=30_000)
            await page.screenshot(path=str(screenshot_dir / "studio-before-edit.png"), full_page=True)
            layout = await page.evaluate("""() => {
              const selectors = [".content-viewport", ".workspace-shell", ".workspace-grid", ".workspace-main-scroll", ".studio-container", ".studio-editor-pane", ".studio-editor-surface", ".monaco-editor", "section[aria-label*=调试器]"];
              const elements = Object.fromEntries(selectors.map((selector) => {
                const element = document.querySelector(selector);
                if (!element) return [selector, null];
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return [selector, {x: rect.x, y: rect.y, width: rect.width, height: rect.height, display: style.display, heightStyle: style.height, minHeight: style.minHeight, overflow: style.overflow, position: style.position, flex: style.flex, gridTemplateRows: style.gridTemplateRows}];
              }));
              const editor = document.querySelector(".monaco-editor");
              const rect = editor?.getBoundingClientRect();
              const target = rect ? document.elementFromPoint(rect.x + 180, rect.y + 20) : null;
              return {viewport: {width: innerWidth, height: innerHeight}, elements, target: target?.outerHTML.slice(0, 300)};
            }""")
            print("STUDIO_LAYOUT=" + json.dumps(layout, sort_keys=True))
            assert layout["elements"][".workspace-grid"]["height"] >= 600, layout
            assert layout["elements"][".monaco-editor"]["height"] >= 120, layout

            edited_source = steps_source.replace(
                "# TODO: replace through the real Studio editor, then save.",
                "# Edited and saved through the real Studio editor.",
                1,
            )
            await editor.click(position={"x": 180, "y": 20})
            await page.keyboard.press("Meta+ArrowLeft" if sys.platform == "darwin" else "Home")
            await page.keyboard.press("Shift+End")
            await page.keyboard.insert_text("# Edited and saved through the real Studio editor.")
            save_button = page.get_by_role("button", name=_localized("Save", "保存"))
            await save_button.click()
            await expect(save_button).to_be_disabled(timeout=15_000)
            saved_file = await client.get(f"/api/workspaces/{project_id}/file", params={"path": steps_path})
            assert saved_file.status_code == 200, saved_file.text
            assert saved_file.json()["content"] == edited_source
            await page.screenshot(path=str(screenshot_dir / "studio-after-edit.png"), full_page=True)

            breakpoint_line = edited_source.splitlines().index("    intermediate = add_one(value)") + 1
            await editor.click(position={"x": 180, "y": 20})
            await page.keyboard.press("Meta+Home" if sys.platform == "darwin" else "Control+Home")
            for _ in range(breakpoint_line - 1):
                await page.keyboard.press("ArrowDown")
            line_numbers = page.locator(".monaco-editor .line-numbers")
            line_number = line_numbers.filter(has_text=re.compile(rf"^\s*{breakpoint_line}\s*$"))
            line_debug = await editor.evaluate(
                "element => ({text: element.innerText, lineNumbers: [...element.querySelectorAll('.line-numbers')].map(line => line.textContent), viewLines: element.querySelectorAll('.view-line').length})"
            )
            print("STUDIO_BREAKPOINT_DOM=" + json.dumps(line_debug, sort_keys=True))
            await expect(line_number).to_be_visible()
            await line_number.click()
            await _wait_for_breakpoint(client, project_id, steps_path, breakpoint_line)
            await expect(editor.locator(".qa-breakpoint-glyph")).to_be_visible()
            await page.screenshot(path=str(screenshot_dir / "studio-breakpoint-set.png"), full_page=True)

            session_response_info = page.expect_response(
                lambda response: (
                    response.request.method == "POST" and response.url.rstrip("/").endswith("/api/debug/sessions")
                )
            )
            async with session_response_info as response_info:
                await debug_action.click()
            session_response = await response_info.value
            assert session_response.status < 400, await session_response.text()
            session_id = (await session_response.json())["id"]
            created_sessions.append(session_id)
            debug_region = page.get_by_role("region", name=re.compile(r"(?:Python Debugger|Python 调试器)"))
            await expect(debug_region.get_by_text(_localized("Paused", "已暂停"))).to_be_visible(timeout=30_000)
            await expect(
                debug_region.get_by_role(
                    "region", name=re.compile(r"(?:Breakpoint verification|断点验证状态)")
                ).get_by_text(_localized("Hit", "已命中"))
            ).to_be_visible()
            await expect(debug_region.get_by_text("calculate", exact=True)).to_be_visible()
            await expect(debug_region.get_by_text("value", exact=True)).to_be_visible()
            await expect(debug_region.get_by_text("40", exact=True)).to_be_visible()
            responsive_metrics = {}
            for name, viewport in (
                ("desktop", {"width": 1440, "height": 960}),
                ("tablet", {"width": 768, "height": 1024}),
                ("mobile", {"width": 390, "height": 844}),
            ):
                await page.set_viewport_size(viewport)
                responsive_metrics[name] = await page.evaluate(
                    "({width: window.innerWidth, documentWidth: document.documentElement.scrollWidth})"
                )
                assert responsive_metrics[name]["documentWidth"] <= responsive_metrics[name]["width"], (
                    responsive_metrics[name]
                )
                debug_box = await debug_region.bounding_box()
                editor_box = await page.locator(".studio-editor-surface").bounding_box()
                responsive_metrics[name]["debugPanelWidth"] = debug_box["width"] if debug_box else None
                responsive_metrics[name]["editorSurfaceHeight"] = editor_box["height"] if editor_box else None
                assert editor_box and editor_box["height"] >= 120, responsive_metrics[name]
                await page.screenshot(path=str(screenshot_dir / f"studio-debug-paused-{name}.png"), full_page=True)
                if name in {"tablet", "mobile"}:
                    debug_details = debug_region.locator(".studio-debug-details")
                    detail_sizes = await debug_details.evaluate(
                        "element => ({clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, clientHeight: element.clientHeight, scrollHeight: element.scrollHeight})"
                    )
                    responsive_metrics[name]["debugDetails"] = detail_sizes
                    assert detail_sizes["scrollWidth"] <= detail_sizes["clientWidth"], responsive_metrics[name]
                    if name == "mobile":
                        assert detail_sizes["scrollHeight"] > detail_sizes["clientHeight"], responsive_metrics[name]
                        output_panel = debug_details.locator(":scope > div").nth(2)
                        await output_panel.scroll_into_view_if_needed()
                        responsive_metrics[name]["debugDetailsScrollTop"] = await debug_details.evaluate(
                            "element => element.scrollTop"
                        )
                        assert responsive_metrics[name]["debugDetailsScrollTop"] > 0, responsive_metrics[name]
                        await expect(output_panel).to_be_visible()
                        await page.screenshot(
                            path=str(screenshot_dir / "studio-debug-paused-mobile-console.png"), full_page=True
                        )
                        await debug_details.evaluate("element => { element.scrollTop = 0; }")
            await page.set_viewport_size({"width": 1440, "height": 960})

            await page.get_by_role("button", name=_localized("Step In", "单步进入")).click()
            await expect(debug_region.get_by_text("add_one", exact=True)).to_be_visible(timeout=10_000)
            await page.get_by_role("button", name=_localized("Step Over", "单步跳过")).click()
            await expect(debug_region.get_by_text("41", exact=True)).to_be_visible(timeout=10_000)
            await page.get_by_role("button", name=_localized("Step Out", "单步跳出")).click()
            await expect(debug_region.get_by_role("button", name="calculate:11")).to_be_visible(timeout=10_000)
            # Python pauses on the call's line before its STORE_FAST; step over the remainder to inspect it.
            await page.get_by_role("button", name=_localized("Step Over", "单步跳过")).click()
            await expect(debug_region.get_by_text("intermediate", exact=True)).to_be_visible(timeout=10_000)
            await expect(debug_region.get_by_text("41", exact=True)).to_be_visible(timeout=10_000)
            await page.get_by_role("button", name=_localized("Continue", "继续")).click()
            session_results.append(await _wait_debug_status(client, session_id, {"CLOSED"}))

            # A second independent run proves that completion cleared the prior session state.
            repeated_response_info = page.expect_response(
                lambda response: (
                    response.request.method == "POST" and response.url.rstrip("/").endswith("/api/debug/sessions")
                )
            )
            async with repeated_response_info as response_info:
                await debug_action.click()
            repeated_response = await response_info.value
            assert repeated_response.status < 400, await repeated_response.text()
            repeated_id = (await repeated_response.json())["id"]
            created_sessions.append(repeated_id)
            await expect(debug_region.get_by_text(_localized("Paused", "已暂停"))).to_be_visible(timeout=30_000)
            await page.get_by_role("button", name=_localized("Continue", "继续")).click()
            session_results.append(await _wait_debug_status(client, repeated_id, {"CLOSED"}))

            # Exercise pause and stop against a distinct, deliberately long-running test.
            await page.goto(studio_url + pause_path, wait_until="domcontentloaded")
            await expect(page.locator(".monaco-editor")).to_be_visible(timeout=30_000)
            await expect(debug_action).to_be_enabled(timeout=30_000)
            pause_response_info = page.expect_response(
                lambda response: (
                    response.request.method == "POST" and response.url.rstrip("/").endswith("/api/debug/sessions")
                )
            )
            async with pause_response_info as response_info:
                await debug_action.click()
            pause_response = await response_info.value
            assert pause_response.status < 400, await pause_response.text()
            pause_id = (await pause_response.json())["id"]
            created_sessions.append(pause_id)
            await expect(page.get_by_text("STUDIO_PAUSE_TARGET_RUNNING")).to_be_visible(timeout=15_000)
            await _wait_debug_status(client, pause_id, {"ACTIVE"})
            await page.get_by_role("button", name=_localized("Pause", "暂停")).click()
            pause_debug_region = page.get_by_role("region", name=re.compile(r"(?:Python Debugger|Python 调试器)"))
            await expect(pause_debug_region.get_by_text(_localized("Paused", "已暂停"))).to_be_visible(timeout=15_000)
            await page.set_viewport_size({"width": 390, "height": 844})
            responsive_metrics["mobile-paused"] = await page.evaluate(
                "({width: window.innerWidth, documentWidth: document.documentElement.scrollWidth})"
            )
            pause_debug_box = await pause_debug_region.bounding_box()
            responsive_metrics["mobile-paused"]["debugPanelWidth"] = (
                pause_debug_box["width"] if pause_debug_box else None
            )
            await page.screenshot(
                path=str(screenshot_dir / "studio-debug-paused-before-stop-mobile.png"), full_page=True
            )
            await page.set_viewport_size({"width": 1440, "height": 960})
            await page.get_by_role("button", name=_localized("Stop", "停止")).click()
            session_results.append(await _wait_debug_status(client, pause_id, {"CLOSED"}))

            # Run a real Playwright failure through Studio and retain its UI/runtime evidence.
            await page.goto(studio_url + failure_path, wait_until="domcontentloaded")
            await expect(page.locator(".monaco-editor")).to_be_visible(timeout=30_000)
            await expect(page.get_by_role("button", name=_localized("Run File", "运行文件"))).to_be_enabled(
                timeout=30_000
            )
            run_response_info = page.expect_response(
                lambda response: response.request.method == "POST" and response.url.rstrip("/").endswith("/api/runs")
            )
            async with run_response_info as response_info:
                await page.get_by_role("button", name=_localized("Run File", "运行文件")).click()
            run_response = await response_info.value
            assert run_response.status < 400, await run_response.text()
            run_id = (await run_response.json())["id"]
            run_result = await _wait_for_run(client, run_id)
            assert str(run_result["status"]).upper() == "FAILED", run_result
            assert run_result["failed"] == 1, run_result
            execution = run_result["executions"][0]
            trace = "\n".join(
                value or ""
                for value in (
                    execution.get("stack_trace"),
                    execution.get("error_message"),
                    run_result.get("log_output"),
                )
            )
            assert "Expected absent" in trace or "to_be_visible" in trace, trace
            execution_monitor = page.get_by_role("region", name=re.compile(r"(?:Execution Monitor|执行观察台)"))
            await expect(execution_monitor.get_by_role("status")).to_have_text(
                re.compile(r"(?:FAILED|失败)", re.IGNORECASE), timeout=20_000
            )
            await page.screenshot(path=str(screenshot_dir / "studio-failure-evidence.png"), full_page=True)

            # A Debug deep link must keep the linked run available in the existing browser drawer.
            failure_response = await client.get("/api/failures", params={"project_id": project_id})
            assert failure_response.status_code == 200, failure_response.text
            failure = next(item for item in failure_response.json() if item["run_id"] == run_id)
            mode_targets = {
                "explore": f"http://127.0.0.1:{web_port}/workspace/{project_id}?stage=discover&view=discover",
                "write-tests": (
                    f"http://127.0.0.1:{web_port}/workspace/{project_id}?stage=automation&view=code"
                    f"&file={steps_path.replace('/', '%2F')}"
                ),
                "ai-repair": (
                    f"http://127.0.0.1:{web_port}/workspace/{project_id}?stage=failure&view=results"
                    f"&runId={run_id}&failureId={failure['id']}"
                ),
            }
            mode_viewports = (
                ("desktop", {"width": 1440, "height": 960}),
                ("tablet", {"width": 768, "height": 1024}),
                ("narrow", {"width": 390, "height": 844}),
            )
            mode_metrics: dict[str, dict[str, object]] = {}
            for mode_name, mode_url in mode_targets.items():
                await page.goto(mode_url, wait_until="domcontentloaded")
                await expect(page.locator(".workspace-mode-tab.is-current")).to_be_visible(timeout=30_000)
                await expect(page.locator(".workspace-mode-tab")).to_have_count(4)
                if mode_name == "explore":
                    await expect(page.locator(".qd-load-status")).to_have_count(0, timeout=30_000)
                if mode_name == "ai-repair":
                    await expect(page.locator('.failure-workflow-attempt [role="status"]')).to_have_count(
                        0, timeout=30_000
                    )
                if mode_name == "write-tests":
                    await expect(page.locator(".monaco-editor")).to_be_visible(timeout=30_000)
                for size_name, viewport in mode_viewports:
                    await page.set_viewport_size(viewport)
                    metrics = await page.evaluate(
                        "({width: innerWidth, documentWidth: document.documentElement.scrollWidth})"
                    )
                    assert metrics["documentWidth"] <= metrics["width"], (mode_name, size_name, metrics)
                    mode_metrics.setdefault(mode_name, {})[size_name] = metrics
                    await page.screenshot(
                        path=str(screenshot_dir / f"mode-{mode_name}-{size_name}.png"), full_page=True
                    )

            await page.set_viewport_size({"width": 1440, "height": 960})
            await page.goto(
                f"{studio_url}{failure_path}&runId={run_id}&failureId={failure['id']}",
                wait_until="domcontentloaded",
            )
            await expect(page.locator(".monaco-editor")).to_be_visible(timeout=30_000)
            await page.locator(".lc-studio-tools > summary").click()
            await page.get_by_role("button", name=_localized("Show browser & live run", "显示浏览器与实时运行")).click()
            workflow_link = page.get_by_role("link", name="Open Workflow")
            await expect(workflow_link).to_be_visible(timeout=15_000)
            assert run_id in (await workflow_link.get_attribute("href") or "")
            await page.screenshot(path=str(screenshot_dir / "debug-linked-run-browser.png"), full_page=True)

        assert not api_errors, api_errors
        assert not console_errors, console_errors
        summary = {
            "project_id": project_id,
            "debug_sessions": [record["status"] for record in session_results],
            "failure_run": {
                "status": run_result["status"],
                "failed": run_result["failed"],
                "trace_excerpt": trace[-1000:],
            },
            "responsive_metrics": responsive_metrics,
            "mode_responsive_metrics": mode_metrics,
            "api_errors": api_errors,
            "console_errors": console_errors,
            "screenshots": [str(path.relative_to(evidence_root)) for path in sorted(screenshot_dir.glob("*.png"))],
        }
        (evidence_dir / "acceptance-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("STUDIO_UI_ACCEPTANCE=" + json.dumps(summary, ensure_ascii=False))
    finally:
        primary_error = sys.exc_info()[0] is not None
        for session_id in created_sessions:
            try:
                response = await client.delete(f"/api/debug/sessions/{session_id}")
                if response.status_code >= 400:
                    cleanup_errors.append(f"DELETE session {session_id}: {response.status_code} {response.text}")
            except Exception as error:
                cleanup_errors.append(f"DELETE session {session_id}: {error}")
        if browser is not None:
            try:
                await browser.close()
            except Exception as error:
                cleanup_errors.append(f"close Chromium: {error}")
        if vite is not None:
            vite.terminate()
            try:
                await asyncio.to_thread(vite.wait, 10)
            except subprocess.TimeoutExpired:
                vite.kill()
                await asyncio.to_thread(vite.wait, 10)
        vite_log.close()
        server.should_exit = True
        try:
            await asyncio.wait_for(api_task, timeout=15)
        except asyncio.TimeoutError:
            api_task.cancel()
            await asyncio.gather(api_task, return_exceptions=True)
        if cleanup_errors and not primary_error:
            raise AssertionError("Acceptance cleanup errors: " + "; ".join(cleanup_errors))
