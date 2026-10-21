"""Round 22 release-candidate acceptance: two real business chains on the real stack.

Chain 1 — a failing test → failure record → repair task (approval gate) → human approval → apply →
exact verification of the very nodeid that failed.
Chain 2 — a natural-language goal → candidate workflow (real provider) → draft → publish →
attempted execution, which must stop before running anything.

Every AI call is the configured real provider; every run is a real Playwright/pytest execution.

Run: cd <repo> && uv run python .ai-runs/overnight-delivery/rounds/r22_acceptance.py
Writes r22-acceptance.json + screenshots beside the other rounds' evidence.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time

from playwright.async_api import async_playwright

OUT = pathlib.Path(".ai-runs/overnight-delivery/rounds")
SHOTS = OUT / "screenshots"
WEB = "http://127.0.0.1:5173"
PROJECT = "proj_golden_shop_v1"
NODEID = "tests/test_known_locator.py::test_known_locator_change"
BROKEN = '''"""TC-006: cart assertions, temporarily using the retired locator."""

from pages.shop import ShopPage
from playwright.sync_api import expect


def test_known_locator_change(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    shop.add_with_legacy_locator()
    shop.cart()
    expect(page.get_by_test_id("cart-item")).to_contain_text(shop_data["product"])
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price']}.00")
'''

checks: list[dict] = []
console: list[str] = []


def check(name: str, passed: bool, detail: object = None) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"[check] {name}: {'PASS' if passed else 'FAIL'} {detail if detail is not None else ''}")


async def login(page) -> None:
    await page.goto(f"{WEB}/login", wait_until="domcontentloaded")
    await page.fill("#login-email", "admin@ai-qa.local")
    await page.fill("#login-password", "adminpassword")
    await page.click("button[type=submit]")
    await page.wait_for_function("() => Boolean(localStorage.getItem('ai-qa.auth-token'))", timeout=30000)


async def call(page, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, object]:
    return await page.evaluate(
        """async ({path, method, body}) => {
            const token = localStorage.getItem('ai-qa.auth-token');
            const response = await fetch(`/api${path}`, {
                method,
                headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'},
                body: body ? JSON.stringify(body) : undefined,
            });
            const text = await response.text();
            try { return [response.status, JSON.parse(text)]; } catch { return [response.status, text]; }
        }""",
        {"path": path, "method": method, "body": body},
    )


async def wait_run(page, run_id: str, timeout: float = 240.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, run = await call(page, f"/runs/{run_id}")
        if isinstance(run, dict) and run.get("status") in {"PASSED", "FAILED", "ERROR", "CANCELLED", "TIMEOUT"}:
            return run
        await asyncio.sleep(2)
    return run if isinstance(run, dict) else {}


async def wait_task(page, task_id: str, timeout: float = 420.0) -> dict:
    deadline = time.time() + timeout
    task: dict = {}
    while time.time() < deadline:
        _, task = await call(page, f"/tasks/{task_id}")
        if not isinstance(task, dict):
            return {}
        if task.get("status") in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}:
            return task
        await asyncio.sleep(3)
    return task


def step(task: dict, key: str) -> dict:
    for item in task.get("plan") or []:
        if item.get("key") == key:
            return item
    return {}


async def main() -> None:
    report: dict = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1560, "height": 1000})
        page = await context.new_page()
        page.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
        await login(page)

        # ---------------------------------------------------------------- chain 1
        status, workspaces = await call(page, f"/workspaces?project_id={PROJECT}")
        workspace_id = PROJECT
        if isinstance(workspaces, list) and workspaces:
            workspace_id = workspaces[0].get("id") or PROJECT
        status, written = await call(
            page, f"/workspaces/{workspace_id}/file", "PUT", {"path": NODEID.split("::")[0], "content": BROKEN}
        )
        check("chain 1 starts from a genuinely failing test file", status == 200, {"status": status, "workspace": workspace_id})

        status, run = await call(
            page,
            "/runs",
            "POST",
            {"project_id": PROJECT, "workspace_id": workspace_id, "nodeids": [NODEID], "requested_by": "release-audit"},
        )
        run_id = run.get("id") if isinstance(run, dict) else None
        run = await wait_run(page, run_id) if run_id else {}
        failures: list = []
        if run_id:
            _, all_failures = await call(page, f"/failures?project_id={PROJECT}&limit=200")
            failures = [row for row in (all_failures or []) if row.get("run_id") == run_id]
        failure = failures[0] if failures else {}
        check(
            "the failing run records a failure with its source position",
            run.get("status") == "FAILED" and bool(failure),
            {
                "run": run_id,
                "status": run.get("status"),
                "failure": failure.get("id"),
                "source": f"{failure.get('source_file')}:{failure.get('source_line')}",
                "nodeid": failure.get("test_nodeid"),
            },
        )
        report["run_id"] = run_id
        report["failure_id"] = failure.get("id")

        status, task = await call(
            page,
            "/tasks",
            "POST",
            {
                "type": "FIX_FAILURE",
                "goal": f"诊断并修复 {NODEID} 的失败",
                "project_id": PROJECT,
                "workspace_id": workspace_id,
                "inputs": {"failure_id": failure.get("id"), "origin": "failure", "origin_id": failure.get("id")},
            },
        )
        task_id = task.get("id") if isinstance(task, dict) else None
        task = await wait_task(page, task_id, timeout=300) if task_id else {}
        approval = step(task, "approval")
        apply_step = step(task, "apply")
        check(
            "the repair task stops at a real approval gate before touching the source",
            approval.get("status") == "WAITING_FOR_APPROVAL" and apply_step.get("status") == "PENDING",
            {"task": task_id, "status": task.get("status"), "approval": approval.get("status"), "apply": apply_step.get("status")},
        )
        report["repair_task_id"] = task_id
        _, diff_text = await call(page, f"/workspaces/{workspace_id}/file?path={NODEID.split('::')[0]}")
        report["source_before_approval"] = "add_with_legacy_locator" in json.dumps(diff_text)

        await page.goto(f"{WEB}/tasks?taskId={task_id}", wait_until="domcontentloaded")
        for _ in range(12):
            if await page.get_by_role("button", name="批准并应用修复").count():
                break
            await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SHOTS / "r22-01-approval-gate.png"))
        approve = page.get_by_role("button", name="批准并应用修复")
        check(
            "the approval control is a real human action in the UI",
            await approve.count() > 0,
            {"buttons": await approve.count(), "needs_approval_text": "需要审批" in await page.evaluate("() => document.body.innerText")},
        )

        status, decided = await call(
            page, f"/tasks/{task_id}/approval", "POST", {"approved": True, "comment": "Release audit: approve the recorded repair."}
        )
        task = await wait_task(page, task_id, timeout=600)
        verify = step(task, "verify")
        target = step(task, "target_run")
        verification_run_id = (verify.get("outputs") or {}).get("run_id") or (verify.get("outputs") or {}).get("run_ids", [None])[0]
        _, verification = await call(page, f"/runs/{verification_run_id}") if verification_run_id else (0, {})
        _, repaired = await call(page, f"/workspaces/{workspace_id}/file?path={NODEID.split('::')[0]}")
        repaired_text = json.dumps(repaired)
        check(
            "the approval alone applies the change and an independent verification run passes",
            task.get("status") == "COMPLETED"
            and verify.get("status") == "COMPLETED"
            and (verify.get("outputs") or {}).get("verified") is True
            and verification.get("status") == "PASSED"
            and NODEID in (verification.get("nodeids") or [])
            and "add_with_legacy_locator" not in repaired_text,
            {
                "task": task.get("status"),
                "apply": (step(task, "apply").get("outputs") or {}).get("file_path"),
                "verify": verify.get("status"),
                "verified": (verify.get("outputs") or {}).get("verified"),
                "verification_run": verification_run_id,
                "verification_status": verification.get("status"),
                "verification_nodeids": verification.get("nodeids"),
                "target_run": target.get("status"),
            },
        )
        report["verification_run_id"] = verification_run_id

        # ------------------------------------------------------- chain 2 (workflow)
        prompt = (
            "探索商品搜索页面，识别 API 和 DOM，生成测试场景，运行 Playwright，对失败用 AI/Jev 分析，"
            "并在人工批准后执行精确验证。"
        )
        status, plan = 0, {}
        attempts = 0
        while attempts < 3:  # the UI offers the same retry; the model is sometimes slow or malformed
            attempts += 1
            status, plan = await call(page, f"/projects/{PROJECT}/workflows/plan", "POST", {"prompt": prompt})
            if not isinstance(plan, dict):
                plan = {}
            if status == 200:
                break
        nodes = (plan.get("graph") or {}).get("nodes") if isinstance(plan, dict) else None
        kinds = [node.get("kind") for node in nodes or []]
        check(
            "a natural-language goal becomes a validated candidate workflow from the real provider",
            status == 200 and isinstance(plan, dict) and plan.get("valid") is True and bool(kinds),
            {"status": status, "valid": (plan or {}).get("valid"), "nodes": len(kinds), "kinds": kinds[:6], "attempts": attempts, "invocation": (plan or {}).get("invocation_id")},
        )
        report["plan"] = {"valid": (plan or {}).get("valid"), "nodes": len(kinds), "attempts": attempts, "invocation_id": (plan or {}).get("invocation_id")}

        status, definition = await call(
            page, f"/projects/{PROJECT}/workflows", "POST", {"name": f"Release audit {int(time.time())}", "description": prompt}
        )
        definition_id = definition.get("id") if isinstance(definition, dict) else None
        status, saved = await call(
            page, f"/workflows/{definition_id}/draft", "PUT", {"nodes": nodes, "edges": (plan.get("graph") or {}).get("edges")}
        )
        status, published = await call(page, f"/workflows/{definition_id}/publish", "POST")
        draft_version = ((saved or {}).get("draft") or {}).get("version") or (saved or {}).get("version")
        published_body = (published or {}).get("published") or {}
        check(
            "the planner's graph is saved as a draft and published as an immutable version",
            bool(definition_id) and bool(draft_version) and published_body.get("state") == "PUBLISHED",
            {"definition": definition_id, "draft_version": draft_version,
             "published_version": published_body.get("version"), "state": published_body.get("state")},
        )
        report["definition_id"] = definition_id

        status, rewritten = await call(
            page,
            f"/workflows/{definition_id}/draft",
            "PUT",
            {"nodes": [{"key": "collect", "kind": "discovery.collect_gaps", "inputs": {"discovery_run_id": "qd_1"}}], "edges": []},
        )
        _, after = await call(page, f"/workflows/{definition_id}")
        versions = (after or {}).get("versions") or []
        published_now = [row for row in versions if row.get("version") == published_body.get("version")]
        status_exec, _ = await call(page, f"/workflows/{definition_id}/execute", "POST", {})
        check(
            "editing a published workflow opens a new draft and leaves the published version untouched",
            status == 200
            and bool(published_now)
            and published_now[0].get("checksum") == published_body.get("checksum")
            and published_now[0].get("state") == "PUBLISHED"
            and status_exec in {404, 405},
            {
                "draft_after_edit": ((rewritten or {}).get("draft") or {}).get("version"),
                "published_version": published_body.get("version"),
                "published_state_now": published_now[0].get("state") if published_now else None,
                "same_checksum": bool(published_now and published_now[0].get("checksum") == published_body.get("checksum")),
                "execute_status": status_exec,
            },
        )

        # -------------------------------------------------------- surfaces + trace
        _, trace = await call(page, f"/tasks/{task_id}/execution-trace")
        trace_nodes = (trace or {}).get("nodes") or []
        ids = [node.get("id") for node in trace_nodes]
        invocation_nodes = [node for node in trace_nodes if str(node.get("type") or "").lower() == "invocation"]
        _, again = await call(page, f"/tasks/{task_id}/execution-trace")
        ids_again = [node.get("id") for node in (again or {}).get("nodes") or []]
        check(
            "the execution tree maps the real task, its steps, its provider calls and its evidence",
            len(trace_nodes) >= 4
            and len(set(ids)) == len(ids)
            and ids == ids_again
            and bool(invocation_nodes)
            and all(node.get("provider") for node in invocation_nodes),
            {"nodes": len(trace_nodes), "unique": len(set(ids)), "reload_identical": ids == ids_again,
             "invocations": [f"{n.get('provider')}/{n.get('model')}" for n in invocation_nodes][:3]},
        )

        await page.goto(f"{WEB}/workspace/{PROJECT}?stage=automation&view=canvas&canvas=execution", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        tree_cards = await page.evaluate("() => document.querySelectorAll('.react-flow__node').length")
        await page.screenshot(path=str(SHOTS / "r22-02-execution-tree.png"))
        check("the execution tree renders the same task in the browser", tree_cards >= 4, {"cards": tree_cards})

        detail: dict = {}
        readings: list = []
        _, runs = await call(page, f"/discovery/runs?project_id={PROJECT}&limit=20")
        run_rows = runs if isinstance(runs, list) else (runs or {}).get("runs") or []
        best: list = []
        for row in run_rows:
            _, evidence_summary = await call(page, f"/discovery/runs/{row.get('id')}/evidence/summary")
            if not detail and isinstance(evidence_summary, dict) and sum((evidence_summary.get("counts") or {}).values()):
                detail = {"run": row.get("id"), "counts": evidence_summary.get("counts")}
            _, suggestions = await call(page, f"/discovery/runs/{row.get('id')}/suggestions")
            rows_here = suggestions if isinstance(suggestions, list) else (suggestions or {}).get("suggestions") or []
            if any(item.get("review_status") not in {None, "PENDING"} for item in rows_here):
                best = rows_here
                break
        readings = best or readings
        check("a discovery run still explains itself from stored evidence", bool(detail), detail)

        reviewed = [row for row in readings if row.get("review_status") and row.get("review_status") != "PENDING"]
        linked = [row for row in readings if row.get("related_case_ids")]
        check(
            "a reviewed reading keeps its rule verdict and its provenance",
            bool(readings) and bool(reviewed) and all(row.get("coverage_status") and row.get("evidence_ids") for row in reviewed),
            {
                "readings": len(readings),
                "reviewed": [(row.get("review_status"), row.get("coverage_status")) for row in reviewed][:3],
                "linked_cases": [row.get("related_case_ids") for row in linked][:3],
            },
        )

        # ------------------------------------------------- Round 12-16.5 regression
        await page.goto(f"{WEB}/failures/{failure.get('id')}?projectId={PROJECT}", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        chain_text = await page.evaluate("() => document.body.innerText")
        await page.screenshot(path=str(SHOTS / "r22-03-failure.png"))
        check(
            "the failure page still shows one forward path after the repair completed",
            "验证" in chain_text and ("通过" in chain_text or "已完成" in chain_text),
            {"primary": await page.evaluate("() => document.querySelector('.failure-primary-action')?.textContent || ''")},
        )

        mobile = await browser.new_context(viewport={"width": 390, "height": 844})
        phone = await mobile.new_page()
        phone.on("console", lambda message: console.append(message.text) if message.type == "error" else None)
        await login(phone)
        await phone.goto(f"{WEB}/workspace/{PROJECT}?stage=automation&view=canvas&canvas=execution", wait_until="domcontentloaded")
        await phone.wait_for_timeout(4000)
        smallest = await phone.evaluate(
            """() => Array.from(document.querySelectorAll('.react-flow__node *'))
                .map((element) => parseFloat(getComputedStyle(element).fontSize))
                .filter((size) => Number.isFinite(size))
                .reduce((minimum, size) => Math.min(minimum, size), 99)"""
        )
        await phone.screenshot(path=str(SHOTS / "r22-04-execution-tree-390.png"))
        check("the execution tree stays readable on a phone", smallest >= 10, {"smallest_px": smallest})

        unexpected = [line for line in console if not ("Failed to load resource" in line and any(code in line for code in ("404", "409", "422", "503")))]
        check("no surface logs an unexpected console error", not unexpected, unexpected[:5])

        await browser.close()

    passed = sum(1 for item in checks if item["passed"])
    payload = {"checks": len(checks), "passed": passed, "failed": [item for item in checks if not item["passed"]],
               "console_errors": console, "chain": report}
    (OUT / "r22-acceptance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": len(checks), "passed": passed, "failed": payload["failed"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
