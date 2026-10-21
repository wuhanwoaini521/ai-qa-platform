"""Round 16.5 acceptance: the execution tree shows the real trajectory of a real task.

Run:  uv run python .ai-runs/e2e-round16.5/execution_tree_acceptance.py

Every check compares what the browser shows with what the server stored (trace API) and with what
the database holds (sqlite). Nothing is seeded into the UI and no demo data is substituted.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:5173"
PROJECT = "proj_golden_shop_v1"
FIXTURE = f"{API}/api/demo-shop/discovery-fixture-d.html"
DB = Path("runtime/ai_qa_platform.db")
OUT = Path(".ai-runs/e2e-round16.5")
SHOTS = OUT / "screenshots"

checks: list[dict] = []


def check(name: str, passed: bool, detail: object = None) -> bool:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"[check] {name}: {'PASS' if passed else 'FAIL'} {detail if not passed else ''}".strip(), flush=True)
    return passed


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_rows(sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(DB) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, params)]


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=API, timeout=120) as client:
        login = await client.post("/api/auth/login", json={"email": "admin@ai-qa.local", "password": "adminpassword"})
        login.raise_for_status()
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        # --- 1. a fresh real discovery run, so the analysis task has something real to read
        runs_before = {row["id"] for row in (await client.get("/api/discovery/runs", params={"project_id": PROJECT})).json()}
        start = await client.post(
            "/api/discovery/runs",
            json={"project_id": PROJECT, "start_url": FIXTURE, "mode": "EXPLORE"},
        )
        assert start.status_code in (200, 201, 202), start.text
        run_id = start.json()["id"]
        deadline = time.monotonic() + 240
        discovery = None
        while time.monotonic() < deadline:
            await asyncio.sleep(4)
            response = await client.get(f"/api/discovery/runs/{run_id}")
            discovery = response.json()
            if discovery["status"] in {"COMPLETED", "STOPPED", "FAILED", "BLOCKED", "BUDGET_EXHAUSTED"}:
                break
        stage("discovery", {"run_id": run_id, "status": discovery["status"], "progress": discovery.get("progress")})
        check("a real discovery run finished so the analysis has evidence", discovery["status"] == "COMPLETED", discovery["status"])

        # --- 1b. materialise the scenarios of that run, exactly as the readings view does
        refreshed = await client.post(f"/api/discovery/runs/{run_id}/scenarios/refresh")
        assert refreshed.status_code == 200, refreshed.text
        scenarios = (await client.get(f"/api/discovery/runs/{run_id}/scenarios")).json()["scenarios"]
        stage("scenarios", {"rows": [row["coverage_status"] for row in scenarios]})

        # --- 2. the analysis task itself (real model + Jev)
        created = await client.post(
            "/api/tasks",
            json={
                "type": "ANALYZE_DISCOVERY",
                "goal": "Read the unsettled scenarios of this run and propose what a human should write next.",
                "project_id": PROJECT,
                "inputs": {"discovery_run_id": run_id},
            },
        )
        assert created.status_code in (200, 201), created.text
        task_id = created.json()["id"]
        stage("task.created", {"task_id": task_id})

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(viewport={"width": 1560, "height": 1000})
            page = await context.new_page()
            console: list[str] = []
            page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: console.append(str(error)))

            await page.goto(f"{WEB}/login")
            await page.fill("#login-email", "admin@ai-qa.local")
            await page.fill("#login-password", "adminpassword")
            await page.click("button[type=submit]")
            await page.wait_for_function("() => !!localStorage.getItem('ai-qa.auth-token')")

            canvas_url = (
                f"{WEB}/workspace/{PROJECT}?projectId={PROJECT}&stage=automation&view=canvas"
            )
            await page.goto(canvas_url)
            await page.wait_for_selector(".react-flow", timeout=60_000)
            await page.wait_for_timeout(1500)
            before_nodes = await page.locator(".lw-node").count()
            await page.screenshot(path=str(SHOTS / "before-pipeline-canvas.png"), full_page=False)

            # --- 3. switch to the execution tree, with the running task selected
            await page.get_by_role("tab", name="执行树").click()
            await page.wait_for_selector(".let-panel", timeout=30_000)
            await page.wait_for_timeout(1200)
            selector = page.get_by_label("任务")
            options = await selector.locator("option").evaluate_all("(nodes) => nodes.map((n) => n.value)")
            assert task_id in options, f"task {task_id} missing from the picker ({options[:3]})"
            await selector.select_option(task_id)
            await page.wait_for_selector(f'.let-node[data-trace-node="task:{task_id}"]', timeout=60_000)

            # live: a new activity appears without a manual refresh
            first_count = await page.locator(".let-node").count()
            live_grew = False
            for _ in range(90):
                await page.wait_for_timeout(1000)
                count = await page.locator(".let-node").count()
                if count > first_count:
                    live_grew = True
                    break
            check("the tree adds a node while the task is still running", live_grew, {"first": first_count})

            # wait for the task to finish, then read the authoritative trace
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                detail = (await client.get(f"/api/tasks/{task_id}")).json()
                if detail["status"] in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}:
                    break
                await asyncio.sleep(3)
            trace = (await client.get(f"/api/tasks/{task_id}/execution-trace")).json()
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(SHOTS / "after-execution-tree.png"), full_page=False)
            stage("task.trace", {"task_id": task_id, "status": detail["status"], "counts": trace["counts"]})

            # 2. real task node
            task_nodes = [node for node in trace["nodes"] if node["type"] == "task"]
            rendered = await page.locator(f'.let-node[data-trace-node="task:{task_id}"]').count()
            check(
                "the tree shows the real task node with its stored status",
                len(task_nodes) == 1 and rendered == 1 and task_nodes[0]["status"] == detail["status"],
                {"api": task_nodes[0]["status"] if task_nodes else None, "rendered": rendered},
            )

            # 3. invocation → step → task chain
            invocations = [node for node in trace["nodes"] if node["type"] == "invocation"]
            by_id = {node["id"]: node for node in trace["nodes"]}
            chain_ok = True
            for node in invocations:
                parent = by_id.get(node["parent_id"] or "")
                if parent is None:
                    chain_ok = False
                    break
                if parent["type"] == "step" and parent["task_id"] != task_id:
                    chain_ok = False
            real_invocations = db_rows("select id, step_id, provider, model, duration_ms, token_source, fallback_used, status from ai_invocations where task_id = ?", (task_id,))
            check(
                "every model call is attached to this task (through its step when the row knows it)",
                bool(invocations) and chain_ok and {row["id"] for row in real_invocations} == {node["invocation_id"] for node in invocations},
                {"invocations": len(invocations), "rows": len(real_invocations)},
            )

            # 4. Jev: provider/model/fallback straight from the row
            jev_rows = [row for row in real_invocations if row["provider"] == "jev"]
            jev_nodes = [node for node in invocations if node["provider"] == "jev"]
            jev_honest = all(
                any(
                    node["invocation_id"] == row["id"]
                    and node["model"] == row["model"]
                    and bool(node["fallback_used"]) == bool(row["fallback_used"])
                    for node in jev_nodes
                )
                for row in jev_rows
            )
            check(
                "a Jev call shows its provider, model and whether it fell back",
                bool(jev_rows) and len(jev_nodes) == len(jev_rows) and jev_honest,
                {"rows": [(row["id"], row["status"], row["fallback_used"]) for row in jev_rows]},
            )

            # 5. durations match the stored numbers
            step_rows = {row["id"]: row for row in db_rows("select id, duration_ms, status from agent_task_steps where task_id = ?", (task_id,))}
            step_nodes = [node for node in trace["nodes"] if node["type"] == "step"]
            durations_ok = bool(step_nodes) and all(
                node["duration_ms"] is None
                or (step_id := node["id"].removeprefix("step:")) not in step_rows
                or step_rows[step_id]["duration_ms"] is None
                or abs(node["duration_ms"] - step_rows[step_id]["duration_ms"]) < 0.001
                for node in step_nodes
            )
            inv_durations_ok = all(
                node["duration_ms"] is None
                or next((row["duration_ms"] for row in real_invocations if row["id"] == node["invocation_id"]), None) is None
                or abs(node["duration_ms"] - next(row["duration_ms"] for row in real_invocations if row["id"] == node["invocation_id"])) < 0.001
                for node in invocations
            )
            check("every duration equals the stored duration", durations_ok and inv_durations_ok, {"steps": len(step_nodes)})

            # 6. no invented tokens or cost
            unmetered = [node for node in invocations if node["token_usage"] is None]
            priced = [node for node in invocations if node["cost"] is not None]
            ui_text = await page.locator(".let-panel").inner_text()
            check(
                "a call without metered tokens shows no number and no invented cost",
                (not unmetered or "未计量" in ui_text) and not priced and all(node["pricing"] == "unpriced" for node in invocations),
                {"unmetered": len(unmetered), "priced": len(priced)},
            )

            # 7. reload keeps the whole trajectory
            ids_before = sorted(node["id"] for node in trace["nodes"])
            await page.reload()
            await page.wait_for_selector(".let-panel", timeout=30_000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SHOTS / "after-execution-tree-reloaded.png"))
            await page.wait_for_selector(f'.let-node[data-trace-node="task:{task_id}"]', timeout=60_000)
            reloaded = (await client.get(f"/api/tasks/{task_id}/execution-trace")).json()
            check(
                "a reload rebuilds the same trajectory from the server",
                sorted(node["id"] for node in reloaded["nodes"]) == ids_before,
                {"nodes": len(ids_before)},
            )

            # 8. re-sync never duplicates a node
            rendered_ids = await page.locator(".let-node").evaluate_all("(nodes) => nodes.map((n) => n.getAttribute('data-trace-node'))")
            await page.reload()
            await page.wait_for_selector(".let-panel", timeout=30_000)
            await page.wait_for_selector(f'.let-node[data-trace-node="task:{task_id}"]', timeout=60_000)
            await page.wait_for_timeout(2500)
            second_ids = await page.locator(".let-node").evaluate_all("(nodes) => nodes.map((n) => n.getAttribute('data-trace-node'))")
            check(
                "a re-sync adds no duplicate node",
                len(rendered_ids) == len(set(rendered_ids)) and sorted(second_ids) == sorted(rendered_ids),
                {"first": len(rendered_ids), "second": len(second_ids)},
            )

            # 9. clicking a node reaches its original evidence: either the ids the answer cited, or
            # the scenario the reading is about when the model cited nothing (the row then stores none).
            evidence_node = next((node for node in trace["nodes"] if node["evidence_ids"]), None)
            fallback_node = next((node for node in trace["nodes"] if node["type"] == "suggestion"), None)
            await page.locator(
                f'.let-node[data-trace-node="{(evidence_node or fallback_node)["id"]}"]'
            ).click()
            await page.wait_for_selector(".let-detail", timeout=15_000)
            detail_text = await page.locator(".let-detail").inner_text()
            if evidence_node is None:
                scenario_id = (fallback_node.get("outputs") or {}).get("scenario_id")
                evidence_shown = [scenario_id] if scenario_id and scenario_id in detail_text else []
            else:
                evidence_shown = [evidence for evidence in evidence_node["evidence_ids"] if evidence in detail_text]
            await page.screenshot(path=str(SHOTS / "after-node-detail.png"))
            check(
                "a node's detail leads to the evidence the server stored",
                bool(evidence_shown),
                {
                    "path": "cited" if evidence_node else "scenario",
                    "node": (evidence_node or fallback_node)["id"],
                    "shown": evidence_shown[:2],
                },
            )

            # 10. the pipeline canvas still works
            await page.get_by_role("tab", name="工作流").click()
            await page.wait_for_selector(".react-flow", timeout=30_000)
            await page.wait_for_timeout(1200)
            after_nodes = await page.locator(".lw-node").count()
            check("the pipeline canvas is unchanged", after_nodes == before_nodes and after_nodes > 0, {"before": before_nodes, "after": after_nodes})

            # 11. mobile: cards stay readable and the page does not scroll sideways
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.get_by_role("tab", name="执行树").click()
            await page.wait_for_selector(f'.let-node[data-trace-node="task:{task_id}"]', timeout=30_000)
            await page.wait_for_timeout(1200)
            metrics = await page.evaluate(
                """() => {
                    const card = document.querySelector('.let-node');
                    const title = card?.querySelector('.let-node-title');
                    return {
                        scrollWidth: document.documentElement.scrollWidth,
                        clientWidth: document.documentElement.clientWidth,
                        fontSize: title ? parseFloat(getComputedStyle(title).fontSize) : 0,
                        cardWidth: card ? card.getBoundingClientRect().width : 0,
                        scale: card ? card.getBoundingClientRect().width / 236 : 0,
                    };
                }"""
            )
            await page.screenshot(path=str(SHOTS / "after-execution-tree-mobile.png"))
            check(
                "on a phone the cards stay legible and nothing is cut off",
                metrics["scrollWidth"] <= metrics["clientWidth"] + 1 and metrics["fontSize"] * metrics["scale"] >= 7,
                metrics,
            )
            await page.set_viewport_size({"width": 1560, "height": 1000})

            # 12. no console error
            check("the execution tree logs no console error", console == [], console[:3])
            await browser.close()

    report = {
        "generated_at": now(),
        "task_id": task_id,
        "discovery_run_id": run_id,
        "checks": checks,
        "total": len(checks),
        "passed": sum(1 for item in checks if item["passed"]),
        "failed": [item["name"] for item in checks if not item["passed"]],
    }
    (OUT / "acceptance.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({"checks": report["total"], "passed": report["passed"], "failed": report["failed"]}, ensure_ascii=False))
    return 0 if not report["failed"] else 1


def stage(name: str, payload: dict) -> None:
    print(json.dumps({"stage": name, "at": datetime.now().strftime("%H:%M:%S"), **payload}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
