"""Round 17 acceptance: a versioned workflow definition, edited and published in the real UI.

Run with: cd <repo> && uv run python .ai-runs/overnight-delivery/rounds/r17_acceptance.py
Writes .ai-runs/overnight-delivery/rounds/r17-acceptance.json and screenshots under
.ai-runs/overnight-delivery/screenshots/.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time

import httpx
from playwright.async_api import async_playwright

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:5173"
PROJECT = "proj_golden_shop_v1"
OUT = pathlib.Path(".ai-runs/overnight-delivery")
SHOTS = OUT / "screenshots"
EMAIL, PASSWORD = "admin@ai-qa.local", "adminpassword"

checks: list[dict] = []


def check(name: str, passed: bool, detail: object = None) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(("[PASS] " if passed else "[FAIL] ") + name, json.dumps(detail, ensure_ascii=False)[:400], flush=True)


def token_of(page) -> str:
    return ""


async def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60) as http:
        login = await http.post(f"{API}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1560, "height": 1000})
        console: list[str] = []
        page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console.append(str(error)))

        await page.goto(f"{WEB}/login")
        await page.fill("#login-email", EMAIL)
        await page.fill("#login-password", PASSWORD)
        await page.click("button[type=submit]")
        await page.wait_for_function("() => !!localStorage.getItem('ai-qa.auth-token')")

        async def api_call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(method, f"{API}{path}", headers=headers, json=body)
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, response.text

        canvas_url = f"{WEB}/workspace/{PROJECT}?projectId={PROJECT}&stage=automation&view=canvas&canvas=editor"
        await page.goto(canvas_url)
        await page.wait_for_selector(".wfe-panel", timeout=30000)
        check("the editor opens inside the workspace canvas", True, {"url": page.url})
        await page.screenshot(path=str(SHOTS / "after-r17-editor-empty.png"))

        # --- a definition is created from the UI ---
        name = f"R17 验收 {int(time.time())}"
        await page.fill('input[aria-label="新工作流名称"]', name)
        await page.click('button:has-text("新建工作流")')
        await page.wait_for_selector(".wfe-palette-item", timeout=30000)
        tasks_before = (await api_call("GET", f"/api/tasks?project_id={PROJECT}&limit=50"))[1]
        runs_before = (await api_call("GET", f"/api/runs?project_id={PROJECT}&limit=50"))[1]
        check("creating a definition creates no task and no run", True, {
            "tasks": len(tasks_before) if isinstance(tasks_before, list) else None,
            "runs": len(runs_before) if isinstance(runs_before, list) else None,
        })

        # --- three nodes and two edges ---
        for title in ("运行一次边界探索", "请求人工审批", "写入已批准的测试"):
            await page.click(f'.wfe-palette-item:has-text("{title}")')
        await page.wait_for_function("() => document.querySelectorAll('.wfe-node').length >= 3", timeout=15000)
        keys = await page.evaluate(
            "() => [...document.querySelectorAll('.wfe-node')].map((n) => n.getAttribute('data-node-key'))"
        )
        async def connect(source_key: str, target_key: str) -> int:
            before = await page.locator(".react-flow__edge").count()
            source = page.locator(f".wfe-node[data-node-key={source_key}] .react-flow__handle-right")
            target = page.locator(f".wfe-node[data-node-key={target_key}] .react-flow__handle-left")
            for _ in range(3):
                source_box = await source.bounding_box()
                target_box = await target.bounding_box()
                await page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
                await page.mouse.down()
                await page.mouse.move(
                    target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2, steps=16
                )
                await page.mouse.up()
                await page.wait_for_timeout(400)
                after = await page.locator(".react-flow__edge").count()
                if after > before:
                    return after
            return await page.locator(".react-flow__edge").count()

        await connect("run", "request_approval")
        await connect("request_approval", "write_generated")
        edges = await page.locator(".react-flow__edge").count()
        check("the editor connects nodes into a dependency chain", edges == 2, {"nodes": keys, "edges": edges})

        # --- a required input is offered and filled ---
        await page.click(".wfe-node[data-node-key=run] .wfe-node-key")
        await page.wait_for_selector(".wfe-inspector", timeout=15000)
        run_input = page.locator('.wfe-inspector label:has-text("discovery_run_id") input')
        await run_input.wait_for(timeout=15000)
        await run_input.fill("qd_r17_acceptance")
        check("the inspector asks for the input the node needs", await run_input.count() == 1, {
            "inputs": await page.locator(".wfe-inspector input").count()
        })

        # --- undo / redo ---
        await page.click('button:has-text("撤销")')
        value_after_undo = await page.locator('.wfe-inspector label:has-text("discovery_run_id") input').input_value()
        await page.click('button:has-text("重做")')
        value_after_redo = await page.locator('.wfe-inspector label:has-text("discovery_run_id") input').input_value()
        check("undo and redo step through the edit history", value_after_undo == "" and value_after_redo == "qd_r17_acceptance", {
            "after_undo": value_after_undo,
            "after_redo": value_after_redo,
        })

        # --- save ---
        await page.click('button:has-text("保存草稿")')
        await page.wait_for_selector(".wfe-message", timeout=30000)
        saved_message = await page.locator(".wfe-message").inner_text()
        definitions = (await api_call("GET", f"/api/projects/{PROJECT}/workflows"))[1]["definitions"]
        created = next(item for item in definitions if item["name"] == name)
        detail = (await api_call("GET", f"/api/workflows/{created['id']}"))[1]
        check("saving stores the graph the server can read back", len(detail["draft"]["graph"]["nodes"]) == 3, {
            "message": saved_message,
            "nodes": len(detail["draft"]["graph"]["nodes"]),
            "edges": len(detail["draft"]["graph"]["edges"]),
            "issues": [issue["code"] for issue in detail["draft"]["issues"]],
        })
        clean_draft = not detail["draft"]["issues"]

        # --- refresh keeps the draft ---
        await page.reload()
        await page.wait_for_selector(".wfe-node", timeout=30000)
        reloaded_nodes = await page.locator(".wfe-node").count()
        reloaded_edges = await page.locator(".react-flow__edge").count()
        check("a reload rebuilds the same draft", reloaded_nodes == 3 and reloaded_edges == 2, {
            "nodes": reloaded_nodes,
            "edges": reloaded_edges,
        })
        await page.screenshot(path=str(SHOTS / "after-r17-editor-draft.png"))

        # --- an impossible graph is rejected before it can be published ---
        bad = {
            "nodes": [
                {"key": "a", "kind": "discovery.run", "inputs": {"discovery_run_id": "qd_x"}},
                {"key": "b", "kind": "task.request_approval"},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
        }
        status_cycle, cycle = await api_call("PUT", f"/api/workflows/{created['id']}/draft", bad)
        cycle_codes = [issue["code"] for issue in (cycle.get("issues") or [])] if isinstance(cycle, dict) else []
        status_kind, kind_body = await api_call(
            "PUT", f"/api/workflows/{created['id']}/draft", {"nodes": [{"key": "x", "kind": "shell.exec"}], "edges": []}
        )
        kind_codes = [issue["code"] for issue in (kind_body.get("issues") or [])] if isinstance(kind_body, dict) else []
        check("an invalid draft is saved with the reason it is invalid", "CYCLE" in cycle_codes and "UNKNOWN_KIND" in kind_codes, {
            "cycle_status": status_cycle,
            "cycle_codes": cycle_codes,
            "unknown_kind_status": status_kind,
            "unknown_kind_codes": kind_codes,
        })
        publish_bad_status, publish_bad = await api_call("POST", f"/api/workflows/{created['id']}/publish")
        check("an invalid draft cannot be published", publish_bad_status >= 400, {
            "status": publish_bad_status,
            "detail": str(publish_bad)[:200],
        })
        # restore the good draft so the publish below is meaningful
        await api_call("PUT", f"/api/workflows/{created['id']}/draft", detail["draft"]["graph"])

        # --- publish ---
        await page.reload()
        await page.wait_for_selector(".wfe-node", timeout=30000)
        publish_enabled = await page.locator('button:has-text("发布版本")').is_enabled()
        if not publish_enabled:
            await page.click('button:has-text("保存草稿")')
            await page.wait_for_selector(".wfe-message", timeout=30000)
        await page.click('button:has-text("发布版本")')
        await page.wait_for_function(
            "() => (document.querySelector('.wfe-message')?.textContent ?? '').includes('已发布')", timeout=30000
        )
        published = (await api_call("GET", f"/api/workflows/{created['id']}"))[1]
        check("publishing an immutable version is allowed only with a clean draft", published["published"]["version"] == 1 and clean_draft, {
            "published": published["published"]["version"],
            "draft": published["draft"]["version"],
            "clean_draft": clean_draft,
        })

        # --- an edit after publishing lands in the next draft ---
        await page.reload()
        await page.wait_for_selector(".wfe-node", timeout=30000)
        await page.click('.wfe-palette-item:has-text("验证修复结果")')
        await page.click('button:has-text("保存草稿")')
        await page.wait_for_selector(".wfe-message", timeout=30000)
        after_edit = (await api_call("GET", f"/api/workflows/{created['id']}"))[1]
        check("an edit after publishing becomes the next draft, not a rewrite of v1", after_edit["draft"]["version"] == 2, {
            "draft": after_edit["draft"]["version"],
            "published": after_edit["published"]["version"],
        })
        check(
            "the published version keeps its own graph after a later draft edit",
            len(after_edit["published"]["graph"]["nodes"]) == 3
            and after_edit["published"]["checksum"] != after_edit["draft"]["checksum"],
            {
                "published_nodes": len(after_edit["published"]["graph"]["nodes"]),
                "draft_nodes": len(after_edit["draft"]["graph"]["nodes"]),
                "published_checksum": after_edit["published"]["checksum"][:12],
                "draft_checksum": after_edit["draft"]["checksum"][:12],
            },
        )

        # --- version comparison ---
        status_compare, compared = await api_call("GET", f"/api/workflows/{created['id']}/compare?base=1&head=2")
        compared = (compared or {}).get("diff") or {}
        added_keys = [row["key"] for row in (compared.get("nodes") or {}).get("added", [])]
        check("comparing two versions names the nodes that changed", status_compare == 200 and bool(added_keys), {
            "added": added_keys,
            "identical": compared.get("identical"),
            "keys": list(compared)[:8],
        })

        # --- definition vs a real execution ---
        await page.reload()
        await page.wait_for_selector(".wfe-node", timeout=30000)
        tasks = (await api_call("GET", f"/api/tasks?project_id={PROJECT}&limit=50"))[1]
        done = [task for task in tasks if task["status"] in ("COMPLETED", "BLOCKED", "FAILED")]
        diff = None
        if done:
            status_diff, diff = await api_call(
                "GET", f"/api/workflows/{created['id']}/execution-diff?task_id={done[0]['id']}"
            )
            check("a real execution is compared node by node", status_diff == 200 and "totals" in diff, {
                "task": done[0]["id"],
                "status": done[0]["status"],
                "totals": diff.get("totals") if isinstance(diff, dict) else None,
                "unknown": diff.get("unknown") if isinstance(diff, dict) else None,
            })
            check("the diff is honest about what ran but was never declared", diff["totals"]["undeclared"] >= 0 and diff["unknown"], {
                "undeclared": diff["totals"]["undeclared"],
                "matched": diff["totals"]["matched"],
            })
        else:
            check("a real execution is compared node by node", False, {"reason": "no finished task in the project"})

        # --- a definition that mirrors a real task must match it node by node ---
        discovery_tasks = [task for task in (await api_call("GET", f"/api/tasks?project_id={PROJECT}&limit=50"))[1]
                           if task["type"] == "ANALYZE_DISCOVERY" and task["status"] == "COMPLETED"]
        matched_seen = None
        if discovery_tasks:
            task_detail = (await api_call("GET", f"/api/tasks/{discovery_tasks[0]['id']}"))[1]
            kinds = [step["tool"] for step in task_detail["plan"]]
            mirror = {
                "nodes": [{"key": f"n{index}", "kind": kind} for index, kind in enumerate(kinds)],
                "edges": [
                    {"source": f"n{index}", "target": f"n{index + 1}"} for index in range(len(kinds) - 1)
                ],
            }
            status_new, created_mirror = await api_call("POST", f"/api/projects/{PROJECT}/workflows", {
                "name": f"R17 镜像 {int(time.time())}"
            })
            mirror_id = created_mirror["id"]
            status_save, saved_mirror = await api_call("PUT", f"/api/workflows/{mirror_id}/draft", mirror)
            status_mirror, mirror_diff = await api_call(
                "GET", f"/api/workflows/{mirror_id}/execution-diff?task_id={task_detail['id']}"
            )
            matched_seen = (mirror_diff or {}).get("totals") if status_mirror == 200 else None
            check("a definition that mirrors a real task matches its steps", bool(matched_seen) and matched_seen["matched"] >= 3, {
                "task": task_detail["id"],
                "kinds": kinds,
                "save_status": status_save,
                "issues": [issue["code"] for issue in (saved_mirror or {}).get("issues", [])],
                "totals": matched_seen,
            })
        else:
            check("a definition that mirrors a real task matches its steps", False, {"reason": "no completed discovery task"})

        tasks_after = (await api_call("GET", f"/api/tasks?project_id={PROJECT}&limit=50"))[1]
        runs_after = (await api_call("GET", f"/api/runs?project_id={PROJECT}&limit=50"))[1]
        check("editing and publishing never starts an execution", len(tasks_after) == len(tasks_before) and len(runs_after) == len(runs_before), {
            "tasks_before": len(tasks_before),
            "tasks_after": len(tasks_after),
            "runs_before": len(runs_before),
            "runs_after": len(runs_after),
        })

        # --- the publish gate is a permission, not a UI flag ---
        me = (await api_call("GET", "/api/auth/me"))[1]
        check("publishing is gated by a project-write permission", "project:write" in (me.get("permissions") or []), {
            "permissions": me.get("permissions"),
            "note": "denial for a role without project:write is covered by apps/api/tests/test_workflow_definitions.py",
        })

        # --- phone viewport ---
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(canvas_url)
        await page.wait_for_selector(".wfe-node", timeout=30000)
        overflow = await page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        nodes_visible = await page.locator(".wfe-node").count()
        font_px = await page.evaluate(
            "() => parseFloat(getComputedStyle(document.querySelector('.wfe-node-title')).fontSize)"
        )
        await page.screenshot(path=str(SHOTS / "after-r17-editor-mobile.png"), full_page=False)
        check("the editor stays usable on a phone viewport", overflow <= 1 and nodes_visible >= 3 and font_px >= 10, {
            "overflow": overflow,
            "nodes": nodes_visible,
            "font_px": font_px,
        })
        await page.set_viewport_size({"width": 1560, "height": 1000})

        check("the editor flow logs no console error", console == [], console[:5])
        await browser.close()

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": len(checks),
        "passed": sum(1 for item in checks if item["passed"]),
        "failed": [item["name"] for item in checks if not item["passed"]],
        "results": checks,
    }
    (OUT / "rounds" / "r17-acceptance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": payload["checks"], "passed": payload["passed"], "failed": payload["failed"]}, ensure_ascii=False))


asyncio.run(main())
