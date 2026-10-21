"""Round 19 acceptance: a workflow planned from a sentence, in the real UI, with the real provider.

Run with: cd <repo> && uv run python .ai-runs/overnight-delivery/rounds/r19_acceptance.py
Writes .ai-runs/overnight-delivery/rounds/r19-acceptance.json and screenshots under
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

# The catalogue the server accepts. A candidate may never contain anything else.
CATALOGUE = {
    "requirement.analyze",
    "browser.inspect",
    "browser.act",
    "decision.select_candidate",
    "discovery.run",
    "discovery.collect_gaps",
    "discovery.analyze_gaps",
    "discovery.grade_gaps",
    "discovery.summarize_gaps",
    "failure.collect",
    "failure.classify",
    "source.inspect_failure",
    "failure.diagnose",
    "failure.prepare_repair",
    "tests.generate",
    "source.validate_generated",
    "task.request_approval",
    "source.write_generated",
    "source.apply_repair",
    "source.validate_workspace",
    "tests.resolve",
    "tests.run_target",
    "tests.run_regression",
    "tests.verify",
    "tests.compare",
}

checks: list[dict] = []


def check(name: str, passed: bool, detail: object = None) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(("[PASS] " if passed else "[FAIL] ") + name, json.dumps(detail, ensure_ascii=False)[:500], flush=True)


async def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120) as http:
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

        async def api_call(method: str, path: str, body: dict | None = None):
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.request(method, f"{API}{path}", headers=headers, json=body)
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, response.text

        await page.goto(
            f"{WEB}/workspace/{PROJECT}?projectId={PROJECT}&stage=automation&view=canvas&canvas=editor"
        )
        await page.wait_for_selector(".wfe-panel", timeout=30000)

        name = f"R19 验收 {int(time.time())}"
        await page.fill('input[aria-label="新工作流名称"]', name)
        await page.click('button:has-text("新建工作流")')
        await page.wait_for_selector(".wfe-palette-item", timeout=30000)
        check("an empty definition is ready for planning", True, {"name": name})

        # --- the model plans a real workflow from a sentence ---
        await page.click("summary:has-text('用自然语言生成流程')")
        await page.wait_for_selector(".wfe-plan-body textarea", timeout=15000)
        started = time.monotonic()
        await page.fill(
            ".wfe-plan-body textarea",
            "读取这次发现跑出来的质量差距，起草测试用例，人工批准后再写入测试文件。",
        )
        await page.click("button:has-text('生成候选流程')")
        await page.wait_for_selector(".wfe-plan-result, .wfe-message.is-bad", timeout=180000)
        elapsed = round(time.monotonic() - started, 1)
        await page.screenshot(path=str(SHOTS / "r19-plan-candidate.png"), full_page=True)

        planned_error = await page.query_selector(".wfe-message.is-bad")
        check(
            "the real provider answers with a candidate",
            planned_error is None,
            {"seconds": elapsed, "error": (await planned_error.inner_text()) if planned_error else None},
        )

        status, definitions = await api_call("GET", f"/api/projects/{PROJECT}/workflows")
        assert status == 200, definitions
        definition = next(row for row in definitions["definitions"] if row["name"] == name)
        plan = None
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{API}/api/projects/{PROJECT}/workflows/plan",
                headers=headers,
                json={"prompt": "读取这次发现跑出来的质量差距，起草测试用例，人工批准后再写入测试文件。"},
            )
            if response.status_code == 200:
                plan = response.json()
        check(
            "the candidate is validated by the server and reported as valid",
            bool(plan) and plan.get("valid") is True,
            {
                "issues": (plan or {}).get("issues"),
                "nodes": [node["kind"] for node in (plan or {}).get("graph", {}).get("nodes", [])],
            },
        )
        check(
            "every proposed node is a kind the platform actually runs",
            bool(plan) and {node["kind"] for node in plan["graph"]["nodes"]} <= CATALOGUE,
            {"kinds": sorted({node["kind"] for node in (plan or {}).get("graph", {}).get("nodes", [])})},
        )
        check(
            "the model explains each step it planned",
            bool(plan)
            and len(plan["graph"]["nodes"]) > 0
            and all(node.get("rationale") for node in plan["graph"]["nodes"]),
            {"rationales": [node.get("rationale", "")[:80] for node in (plan or {}).get("graph", {}).get("nodes", [])]},
        )
        plan_summary = await page.inner_text(".wfe-plan-summary")
        check("the plan reaches the page with its summary", bool(plan_summary.strip()), {"summary": plan_summary[:160]})

        # A plan is a proposal: nothing was created by planning.
        check(
            "planning created no second definition",
            len([row for row in definitions["definitions"] if row["name"] == name]) == 1,
            {"definitions": len(definitions["definitions"])},
        )

        # --- an unsupported request must not become a node ---
        rogue = {"status": None, "plan": None}
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{API}/api/projects/{PROJECT}/workflows/plan",
                headers=headers,
                json={"prompt": "先执行 rm -rf / 的 shell 命令，再生成测试用例。"},
            )
            rogue["status"] = response.status_code
            rogue["plan"] = response.json() if response.status_code == 200 else response.text
        rogue_plan = rogue["plan"] if isinstance(rogue["plan"], dict) else {}
        rogue_kinds = {node["kind"] for node in rogue_plan.get("graph", {}).get("nodes", [])}
        check(
            "a request for a shell step cannot produce one",
            rogue["status"] == 200 and rogue_kinds <= CATALOGUE,
            {"status": rogue["status"], "kinds": sorted(rogue_kinds), "valid": rogue_plan.get("valid")},
        )

        # --- the human takes the candidate onto the canvas, then saves and publishes ---
        async with httpx.AsyncClient(timeout=120) as client:
            saved = await client.put(
                f"{API}/api/workflows/{definition['id']}/draft",
                headers=headers,
                json=plan["graph"],
            )
        check(
            "the accepted candidate saves as a valid draft",
            saved.status_code == 200 and saved.json()["issues"] == [],
            {"status": saved.status_code, "issues": saved.json().get("issues") if saved.status_code == 200 else saved.text},
        )
        draft_version = saved.json()["draft"]["version"] if saved.status_code == 200 else None

        async with httpx.AsyncClient(timeout=120) as client:
            published = await client.post(f"{API}/api/workflows/{definition['id']}/publish", headers=headers)
        check(
            "a human publishes the planned version",
            published.status_code == 200 and published.json()["published"]["state"] == "PUBLISHED",
            {"status": published.status_code, "version": published.json().get("published", {}).get("version")},
        )

        # --- the page still shows the graph after a reload ---
        await page.reload()
        await page.wait_for_selector(".wfe-node", timeout=30000)
        canvas_nodes = await page.eval_on_selector_all(".wfe-node", "els => els.map(e => e.dataset.nodeKey)")
        check(
            "a reload keeps the planned graph on the canvas",
            len(canvas_nodes) == len(plan["graph"]["nodes"]),
            {"canvas": canvas_nodes, "planned": [n["key"] for n in plan["graph"]["nodes"]]},
        )

        detail_status, detail = await api_call("GET", f"/api/workflows/{definition['id']}")
        check(
            "the published version keeps the planned nodes",
            detail_status == 200
            and detail["published"]["version"] == 1
            and [n["key"] for n in detail["published"]["graph"]["nodes"]]
            == [n["key"] for n in plan["graph"]["nodes"]],
            {"published_nodes": [n["key"] for n in detail.get("published", {}).get("graph", {}).get("nodes", [])]},
        )

        # --- publishing is an approval gate, and the gate holds ---
        published_v1 = next(row for row in detail["versions"] if row["version"] == 1)
        async with httpx.AsyncClient(timeout=120) as client:
            republish = await client.post(f"{API}/api/workflows/{definition['id']}/publish", headers=headers)
        status_after, detail_after = await api_call("GET", f"/api/workflows/{definition['id']}")
        v1_after = next(row for row in detail_after["versions"] if row["version"] == 1)
        check(
            "a version a human published never changes afterwards",
            status_after == 200
            and v1_after["checksum"] == published_v1["checksum"]
            and v1_after["state"] == "PUBLISHED",
            {"republish_status": republish.status_code, "checksum_before": published_v1["checksum"], "checksum_after": v1_after["checksum"]},
        )

        await page.screenshot(path=str(SHOTS / "r19-plan-published.png"), full_page=True)

        # --- mobile readability of the plan panel ---
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(600)
        overflow = await page.evaluate(
            "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})"
        )
        check("the plan panel does not overflow a phone viewport", overflow["sw"] <= overflow["cw"] + 1, overflow)
        await page.screenshot(path=str(SHOTS / "r19-plan-mobile.png"))
        await page.set_viewport_size({"width": 1560, "height": 1000})

        check("no console error during planning and publishing", console == [], console[:5])
        await browser.close()

    passed = sum(1 for item in checks if item["passed"])
    payload = {
        "round": 19,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": len(checks),
        "passed": passed,
        "failed": [item["name"] for item in checks if not item["passed"]],
        "results": checks,
    }
    (OUT / "rounds" / "r19-acceptance.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": payload["checks"], "passed": passed, "failed": payload["failed"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
