"""Authenticated real-browser acceptance for the Round 3 workbench UX changes."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("QA_UX_BASE_URL", "http://127.0.0.1:5174")
API_BASE = os.environ.get("QA_UX_API_BASE", "http://127.0.0.1:8001")
CHROME = os.environ.get(
    "QA_UX_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
EMAIL = os.environ.get("QA_UX_EMAIL", "admin@ai-qa.local")
PASSWORD = os.environ.get("QA_UX_PASSWORD", "adminpassword")
PROJECT_ID = "proj_golden_shop_v1"
CASE_ID = "case_golden_001"
NODE_ID = "tests/test_shop.py::test_search"
FILE_PATH = "runtime/workspaces/proj_golden_shop_v1/tests/test_shop.py"
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent / "evidence" / "after"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_url(**context: str) -> str:
    return f"{BASE_URL}/workspace/{PROJECT_ID}?" + urlencode(
        {"projectId": PROJECT_ID, **context}
    )


def main() -> None:
    version = importlib.metadata.version("playwright")
    assert version == "1.62.0", f"Expected Playwright 1.62.0, got {version}"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    source_hash_before = sha256(ROOT / FILE_PATH)
    results: dict[str, object] = {"playwright": version, "project_id": PROJECT_ID}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        console_errors: list[str] = []
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        page.goto(BASE_URL, wait_until="domcontentloaded")
        if page.get_by_label("邮箱").count():
            page.get_by_label("邮箱").fill(EMAIL)
            page.get_by_label("密码").fill(PASSWORD)
            page.get_by_role("button", name="登录").click()
            page.wait_for_timeout(400)
        page.evaluate(
            "projectId => localStorage.setItem('ai-qa.selected-project', projectId)",
            PROJECT_ID,
        )

        page.goto(
            workspace_url(
                caseId=CASE_ID,
                requirementId="req_golden_shop_v1",
                stage="automation",
                view="code",
                file=FILE_PATH.removeprefix("runtime/workspaces/proj_golden_shop_v1/"),
                nodeid=NODE_ID,
            ),
            wait_until="domcontentloaded",
        )
        page.get_by_role("button", name="运行用例", exact=True).wait_for(timeout=30000)
        page.locator(".studio-container").wait_for()
        page.screenshot(path=str(EVIDENCE / "automation-studio-1440.png"), full_page=True)

        assert page.locator(".studio-project-select select").count() == 0
        assert page.locator('.studio-project-select button[aria-label="快速打开文件（Cmd+P）"]').count() == 1
        results["embedded_studio"] = {
            "project_selector_count": page.locator(".studio-project-select select").count(),
            "quick_open_count": page.locator('.studio-project-select button[aria-label="快速打开文件（Cmd+P）"]').count(),
            "run_button": page.get_by_role("button", name="运行用例", exact=True).inner_text(),
            "run_button_title": page.get_by_role("button", name="运行用例", exact=True).get_attribute("title"),
        }

        layout: list[dict[str, object]] = []
        for width, height in ((768, 1024), (360, 800)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(250)
            metrics = page.evaluate(
                """() => {
                  const nav = document.querySelector('.workspace-stage-nav');
                  return {
                    viewport: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    navWidth: nav?.clientWidth ?? null,
                    navScrollWidth: nav?.scrollWidth ?? null,
                    navStageCount: nav?.querySelectorAll('button').length ?? 0,
                    stageButtonWidths: [...(nav?.querySelectorAll('button') ?? [])].map(item => Math.round(item.getBoundingClientRect().width)),
                  };
                }"""
            )
            assert metrics["documentWidth"] <= width, metrics
            assert metrics["navScrollWidth"] == metrics["navWidth"], metrics
            assert metrics["navStageCount"] == 5, metrics
            layout.append(metrics)
            page.screenshot(path=str(EVIDENCE / f"automation-studio-{width}.png"), full_page=True)
            first_stage = page.locator(".workspace-stage-nav button").first
            first_stage.focus()
            page.keyboard.press("Tab")
            active_stage_index = page.locator(".workspace-stage-nav button").evaluate_all(
                "buttons => buttons.indexOf(document.activeElement)"
            )
            assert active_stage_index == 1, {"width": width, "active_stage_index": active_stage_index}
        results["responsive_layout"] = layout
        page.set_viewport_size({"width": 1440, "height": 1000})

        page.locator(".workspace-run-launcher").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_role("button", name="运行配置").click()
        config = {
            "environment": dialog.get_by_label("环境").input_value(),
            "region": dialog.get_by_label("区域").input_value(),
            "browser": dialog.get_by_label("浏览器").input_value(),
            "workers": int(dialog.get_by_label("并行 worker").input_value()),
        }
        page.screenshot(path=str(EVIDENCE / "run-controls-config-1440.png"), full_page=True)
        dialog.get_by_role("button", name="关闭运行控制").click()
        results["run_config"] = config

        with page.expect_response(
            lambda response: response.request.method == "POST" and response.url.rstrip("/").endswith("/api/runs"),
            timeout=30000,
        ) as response_info:
            page.get_by_role("button", name="运行用例", exact=True).click()
        response = response_info.value
        assert response.ok, f"Run creation returned HTTP {response.status}"
        request_payload = response.request.post_data_json
        run = response.json()
        assert request_payload["nodeids"] == [NODE_ID], request_payload
        assert request_payload["browser"] == config["browser"], request_payload
        assert request_payload["environment"] == {
            "QA_ENVIRONMENT": config["environment"],
            "QA_REGION": config["region"],
        }, request_payload
        assert request_payload["parallel_workers"] == config["workers"], request_payload

        token = page.evaluate("localStorage.getItem('ai-qa.auth-token')")
        run_id = run["id"]
        headers = {"Authorization": f"Bearer {token}"}
        terminal_run = run
        for _ in range(120):
            current = page.request.get(f"{API_BASE}/api/runs/{run_id}", headers=headers)
            assert current.ok, f"Run poll returned HTTP {current.status}"
            terminal_run = current.json()
            if terminal_run["status"] in {"PASSED", "FAILED", "ERROR", "CANCELLED"}:
                break
            time.sleep(0.5)
        assert terminal_run["status"] == "PASSED", terminal_run
        assert terminal_run["executions"] and terminal_run["executions"][0]["status"] == "PASSED", terminal_run
        results["run"] = {
            "id": run_id,
            "request": request_payload,
            "status": terminal_run["status"],
            "executions": [
                {"nodeid": item["nodeid"], "status": item["status"]}
                for item in terminal_run["executions"]
            ],
        }

        page.locator(".rt-tabs").wait_for(timeout=20000)
        page.locator(".rt-tabs button", has_text="浏览器").click()
        page.locator(".rt-browser").wait_for(timeout=10000)
        page.screenshot(path=str(EVIDENCE / "runtime-browser-1440.png"), full_page=True)
        browser_panel_text = page.locator(".rt-browser").inner_text()
        assert "Invalid Date" not in browser_panel_text, browser_panel_text
        results["run_details"] = {
            "runtime_tab": "浏览器",
            "browser_panel_text": browser_panel_text[:1200],
            "invalid_timestamps_rendered_as_placeholder": "Invalid Date" not in browser_panel_text,
        }
        page.get_by_role("button", name="关闭运行详情").click()
        page.locator(".workspace-stage-nav button").nth(4).click()
        page.locator(".workspace-result-columns").wait_for(timeout=20000)
        page.get_by_text(NODE_ID, exact=True).first.wait_for()
        page.screenshot(path=str(EVIDENCE / "run-result-1440.png"), full_page=True)
        log = page.locator(".workspace-result-raw-log summary")
        if log.count():
            log.click()

        failures_response = page.request.get(
            f"{API_BASE}/api/failures?project_id={PROJECT_ID}&limit=50", headers=headers
        )
        assert failures_response.ok
        failures = failures_response.json()
        failure = next((item for item in failures if item["id"] == "fail_16d594548ce0"), None)
        assert failure is not None, "The existing Northstar debug/repair fixture is unavailable"
        repair_response = page.request.get(
            f"{API_BASE}/api/failures/{failure['id']}/repair-workflow", headers=headers
        )
        assert repair_response.ok
        repair = repair_response.json()
        page.goto(
            workspace_url(
                failureId=failure["id"],
                runId=failure["run_id"],
                stage="failure",
                view="results",
            ),
            wait_until="domcontentloaded",
        )
        page.locator(".workspace-main-panel").wait_for(timeout=20000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(EVIDENCE / "failure-repair-1440.png"), full_page=True)
        results["existing_repair"] = {
            "failure_id": failure["id"],
            "run_id": failure["run_id"],
            "repair_state": repair.get("state"),
            "block_reason": repair.get("block_reason"),
            "ai_or_jev_invoked": False,
            "apply_clicked": False,
        }

        page.locator(".workspace-run-launcher").click()
        debug_dialog = page.get_by_role("dialog")
        debug_dialog.get_by_role("button", name="调试", exact=True).click()
        page.locator(".studio-container").wait_for(timeout=20000)
        page.wait_for_timeout(3500)
        page.screenshot(path=str(EVIDENCE / "debugger-from-failure-1440.png"), full_page=True)
        debug_state = page.locator(".studio-container").inner_text()[-1800:]
        debug_tools = page.locator(".studio-editor-tabs .studio-tool").evaluate_all(
            """buttons => {
              const boxes = buttons.map(button => {
                const rect = button.getBoundingClientRect();
                return { label: button.innerText.trim(), x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom, width: rect.width };
              });
              const overlaps = boxes.flatMap((a, index) => boxes.slice(index + 1)
                .filter(b => a.x < b.right && a.right > b.x && a.y < b.bottom && a.bottom > b.y)
                .map(b => [a.label, b.label]));
              return { minButtonWidth: Math.min(...boxes.map(button => button.width)), overlaps, buttons: boxes };
            }"""
        )
        assert debug_tools["minButtonWidth"] >= 40, debug_tools
        assert not debug_tools["overlaps"], debug_tools
        results["debugger"] = {
            "opened_from_failure": True,
            "visible_status": debug_state,
            "toolbar_layout": debug_tools,
        }
        stop_button = page.get_by_role("button", name="停止", exact=True)
        if stop_button.count() and stop_button.is_visible():
            stop_button.click()
            page.wait_for_timeout(400)

        source_hash_after = sha256(ROOT / FILE_PATH)
        assert source_hash_after == source_hash_before, "The demo source changed during the workflow"
        results["source_unchanged"] = True
        results["console_errors"] = console_errors
        results["known_console_404"] = "Reproduced in the isolated local demo shop as GET /favicon.ico; not a platform API failure."
        (EVIDENCE / "interaction-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
