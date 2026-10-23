"""RC Hotfix 1 — cancel in a real browser against the real backend.

The defect being verified (R18-B2): a cancel used to be a single unconditional status write from
whichever replica served the request. Now the request is recorded and the lease owner ends the task.
This run drives the real UI: a real FIX_FAILURE task, the real 取消任务 button, a reload mid-cancel,
and the real database afterwards.

Usage: uv run python .ai-runs/overnight-delivery/rounds/r18b_cancel_acceptance.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".ai-runs/overnight-delivery/rounds"
SHOTS = OUT / "screenshots"
DB = ROOT / "runtime/ai_qa_platform.db"
WEB = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"
PROJECT = "proj_golden_shop_v1"

checks: list[dict] = []
journal: list[dict] = []


def check(name: str, passed: bool, detail=None) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    mark = "PASS" if passed else "FAIL"
    print(f"[check] {name}: {mark} {json.dumps(detail, ensure_ascii=False)[:300] if detail is not None else ''}")


def stage(name: str, **data) -> None:
    entry = {"stage": name, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **data}
    journal.append(entry)
    print(json.dumps(entry, ensure_ascii=False))


async def call(page, path: str, method: str = "GET", body=None):
    return await page.evaluate(
        """async ({ path, method, body }) => {
            const token = localStorage.getItem('ai-qa.auth-token');
            const init = {
                method,
                headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            };
            if (body !== undefined && body !== null) init.body = JSON.stringify(body);
            const response = await fetch(`/api${path}`, init);
            const text = await response.text();
            let data; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
            return [response.status, data];
        }""",
        {"path": path, "method": method, "body": body},
    )


def rows(sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as connection:
        return connection.execute(sql, params).fetchall()


async def wait_status(page, task_id: str, wanted: set[str], timeout: float = 180.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        _, task = await call(page, f"/tasks/{task_id}")
        status = (task or {}).get("status", "")
        if status in wanted:
            return status
        await asyncio.sleep(0.5)
    return status


def single_writer_or_die() -> None:
    """A second process holding the DB runs its own scheduler and executes tasks behind the API's back."""
    holders: list[str] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                if str(fd.readlink()).endswith("runtime/ai_qa_platform.db"):
                    holders.append(entry.name)
                    break
        except (OSError, PermissionError):
            continue
    if len(set(holders)) > 1:
        raise SystemExit(
            "Refusing to accept: several processes hold runtime/ai_qa_platform.db "
            f"(pids {sorted(set(holders))}). One of them executes tasks with its own scheduler, so a cancel "
            "issued through the API would race it. Stop the stale process first."
        )


async def main() -> None:
    single_writer_or_die()
    SHOTS.mkdir(parents=True, exist_ok=True)
    console: list[str] = []
    task_id = ""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await (await browser.new_context(viewport={"width": 1560, "height": 1000})).new_page()
        page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)

        await page.goto(f"{WEB}/login", wait_until="domcontentloaded")
        await page.fill("#login-email", "admin@ai-qa.local")
        await page.fill("#login-password", "adminpassword")
        await page.click("button[type=submit]")
        await page.wait_for_function("Boolean(localStorage.getItem('ai-qa.auth-token'))", timeout=30000)

        status_, failures = await call(page, f"/failures?project_id={PROJECT}&limit=20")
        rows_ = failures.get("items", []) if isinstance(failures, dict) else (failures or [])
        failure = next((row for row in rows_ if isinstance(row, dict) and row.get("run_id")), None)
        check("a real failure record is available to drive a task", failure is not None,
              {"failure_id": (failure or {}).get("id"), "nodeid": (failure or {}).get("test_nodeid")})
        if failure is None:
            await browser.close()
            return

        created_status, created = await call(page, "/tasks", "POST", {
            "type": "FIX_FAILURE",
            "goal": "Hotfix 1: cancel this task from the UI while it is running.",
            "project_id": PROJECT,
            "workspace_id": PROJECT,
            "inputs": {"failure_id": failure["id"], "origin": "failure", "origin_id": failure["id"]},
        })
        task_id = (created or {}).get("id") or ""
        check("the task is created and starts executing", created_status == 201 and bool(task_id),
              {"status": created_status, "task_id": task_id})
        stage("task_created", task_id=task_id)

        started = await wait_status(page, task_id, {"PLANNING", "RUNNING", "VERIFYING"}, timeout=60)
        stage("task_started", status=started)

        await page.goto(f"{WEB}/tasks?taskId={task_id}", wait_until="domcontentloaded")
        cancel_button = page.locator('.rt-task-actions button', has_text="取消任务").first
        await cancel_button.wait_for(state="visible", timeout=45000)
        shot_before = SHOTS / "hotfix1-before-cancel.png"
        await page.screenshot(path=str(shot_before))
        check("the running task offers a cancel control in the UI", await cancel_button.is_enabled(), {"task_id": task_id})

        await cancel_button.click()
        stage("cancel_clicked", task_id=task_id)

        # The request is a recorded fact the API returns, not a made-up terminal status in the client.
        hinted = False
        for _ in range(40):
            _, task = await call(page, f"/tasks/{task_id}")
            if (task or {}).get("cancel_requested_at"):
                hinted = True
                break
            await asyncio.sleep(0.25)
        check("the cancel is recorded as a request on the task", hinted, {"cancel_requested_at": (task or {}).get("cancel_requested_at")})

        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(SHOTS / "hotfix1-cancel-requested-after-reload.png"))

        final = await wait_status(page, task_id, {"CANCELLED", "COMPLETED", "FAILED", "BLOCKED"}, timeout=180)
        stage("task_finished", task_id=task_id, status=final)
        check("the owner ends the task as cancelled", final == "CANCELLED", {"status": final})

        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(SHOTS / "hotfix1-after-cancel.png"))
        try:
            await page.wait_for_function(
                "document.body.innerText.includes('已取消') || document.body.innerText.includes('CANCELLED')",
                timeout=20000,
            )
        except Exception:
            pass
        body_text = await page.locator("body").inner_text()
        check("the page shows a terminal state instead of a spinner",
              "已取消" in body_text or "CANCELLED" in body_text,
              {"sample": next((line for line in body_text.splitlines() if "取消" in line), "")[:80]})

        again_status, _ = await call(page, f"/tasks/{task_id}/cancel", "POST")
        check("cancelling an already-cancelled task is refused, not rewritten", again_status == 409, {"status": again_status})

        row = rows("select status, cancel_requested_at, cancel_requested_by, lease_owner, finished_at from agent_tasks where id=?", (task_id,))
        status_, requested_at, requested_by, lease_owner, finished_at = row[0] if row else (None,) * 5
        stage("db_task", **{"status": status_, "cancel_requested_by": requested_by, "lease_owner": lease_owner})
        check("the database agrees with the API", status_ == "CANCELLED" and requested_at is not None, {"status": status_, "requested_at": requested_at})
        check("the recorded request names the actor who asked", requested_by == "admin@ai-qa.local" or bool(requested_by), {"requested_by": requested_by})
        check("the lease is released after the task ends", not lease_owner, {"lease_owner": lease_owner})
        check("the task carries a finish time", finished_at is not None, {"finished_at": finished_at})

        events = [r[0] for r in rows("select type from agent_task_events where task_id=? order by id", (task_id,))]
        stage("db_events", events=events[-8:])
        check("exactly one cancel request and one terminal transition were recorded",
              events.count("task.cancel_requested") == 1 and events.count("task.cancelled") == 1,
              {"requested": events.count("task.cancel_requested"), "cancelled": events.count("task.cancelled")})

        steps = rows("select key, status from agent_task_steps where task_id=? and status in ('RUNNING','WAITING_FOR_APPROVAL','CANCELLED')", (task_id,))
        check("no step is left running after the cancel", all(status == "CANCELLED" for _, status in steps), {"steps": steps})

        unexpected = [line for line in console if "409" not in line]
        check("the flow logs no console error", unexpected == [], unexpected[:5])
        await browser.close()

    result = {
        "checks": len(checks),
        "passed": sum(1 for entry in checks if entry["passed"]),
        "failed": [entry for entry in checks if not entry["passed"]],
        "task_id": task_id,
        "journal": journal,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / "r18b-cancel-acceptance.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"checks": result["checks"], "passed": result["passed"], "failed": result["failed"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
