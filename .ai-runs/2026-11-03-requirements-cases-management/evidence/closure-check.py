"""Isolated end-to-end closure check for the 需求与用例 page.

Runs the real UI in Chromium against the dev server on 5173, but every /api/** call is
proxied to an isolated API instance (default: 127.0.0.1:8010, its own SQLite file), so the
shared dev database and its demo project are never read or written.

Faults and delays are injected at the proxy layer, never in product code.

Usage:
    uv run python evidence/closure-check.py [--api http://127.0.0.1:8010] [--web http://127.0.0.1:5173]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

results: dict[str, object] = {}
failures: list[str] = []


def check(name: str, ok: bool, detail: object = None) -> bool:
    results[name] = {"ok": bool(ok), **({"detail": detail} if detail is not None else {})}
    if not ok:
        failures.append(name)
    return ok


class Proxy:
    """Per-request fault/delay injection in front of the isolated API."""

    def __init__(self, api: str, web: str) -> None:
        self.api = api
        self.web = web
        self.fail: set[str] = set()
        self.delay: dict[str, float] = {}
        self.counts: dict[str, int] = {}

    def handle(self, route) -> None:  # noqa: ANN001 - Playwright route object
        request = route.request
        path = request.url.split("/api/", 1)[-1].split("?")[0]
        method = request.method
        key = f"{method} {path}"
        for rule in sorted(list(self.fail)):
            if rule in key:
                self.counts[key] = self.counts.get(key, 0) + 1
                route.fulfill(status=500, content_type="application/json", body='{"detail":"injected failure"}')
                return
        for rule, seconds in self.delay.items():
            if rule in key:
                time.sleep(seconds)
        self.counts[key] = self.counts.get(key, 0) + 1
        response = route.fetch(url=request.url.replace(self.web, self.api))
        route.fulfill(response=response)


def api_call(base: str, method: str, path: str, body=None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(base + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:  # noqa: PERF203 - explicit per-call error surface
        return {"_error": error.code, "_body": error.read().decode(errors="replace")}

def read_with_lag(base: str, path: str, token: str, attempts: int = 60, expect=None):
    """GET that tolerates the API's read-after-write lag (see 10-closure.md, D1).

    Returns (payload, lag_seconds). lag > 0 means an earlier attempt still saw the
    pre-write state, which is recorded as evidence instead of hidden.
    """
    started = time.time()
    payload = None
    for index in range(attempts):
        payload = api_call(base, "GET", path, token=token)
        ready = expect(payload) if expect else bool(payload.get("qa_model"))
        if ready:
            return payload, round(time.time() - started, 2) if index else 0.0
        time.sleep(0.3)
    return payload, round(time.time() - started, 2)


def settle(page, ms: int = 500) -> None:
    page.wait_for_timeout(ms)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8010")
    parser.add_argument("--web", default="http://127.0.0.1:5173")
    parser.add_argument("--shots", default="/tmp/aiqa-isolated/shots")
    args = parser.parse_args()
    proxy = Proxy(args.api, args.web)

    token = api_call(args.api, "POST", "/api/auth/login", {"email": "admin@ai-qa.local", "password": "adminpassword"})["access_token"]
    project = api_call(args.api, "POST", "/api/projects", {
        "name": "Closure Isolated Project",
        "description": "isolated closure verification, safe to delete",
        "bootstrap_workspace": False,
    }, token)
    project_id = project["id"]
    results["isolated_project"] = project_id
    stamp = results["stamp"] = time.strftime("%H%M%S")

    try:
        return run_flow(args, proxy, token, project_id)
    finally:
        results["failures"] = failures
        print(json.dumps(results, ensure_ascii=False, indent=2))


def run_flow(args, proxy, token, project_id):
    stamp = results["stamp"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # Only the API prefix: a glob like **/api/** would also swallow Vite module URLs
        # such as /src/api/client.ts and break the app bundle.
        page.route(lambda url: url.startswith(f"{args.web}/api/"), proxy.handle)
        page.on("pageerror", lambda exc: failures.append(f"pageerror: {exc}"))
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(args.web, wait_until="networkidle")
        if page.locator("#login-email").count():
            page.fill("#login-email", "admin@ai-qa.local")
            page.fill("#login-password", "adminpassword")
            page.click("button[type=submit]")
            page.wait_for_selector(".page-container", timeout=20000)
        check("login", "/login" not in page.url, page.url)

        management = f"{args.web}/projects/{project_id}/management"
        page.goto(management, wait_until="networkidle")
        page.wait_for_selector(".project-management-page")
        settle(page)
        check("empty_project_requirements", "暂无需求" in page.inner_text(".project-management-page"), page.inner_text(".project-management-page")[:160])

        # --- create requirement: browser validation blocks an empty title ---
        page.click(".project-management-header-actions .btn-primary")
        page.wait_for_selector("#requirement-title")
        page.click(".modal-footer .btn-primary")
        settle(page)
        check("create_validation_blocks_empty",
              page.locator("#requirement-title").count() == 1 and proxy.counts.get("POST requirements", 0) == 0,
              proxy.counts)

        long_title = f"结算页优惠券叠加与运费计算在跨区域多仓库存场景下的完整业务流程校验（含超长标题换行与操作列可读性检查）{stamp}"
        page.fill("#requirement-title", long_title)
        page.fill("#requirement-description", "隔离环境中的收口验证需求，用于检查长标题、长验收标准与多关联用例的展示。")
        page.fill("#requirement-acceptance-criteria", "进入结算页并确认优惠券可选\n叠加优惠券后总价按最优方案计算\n跨区域订单按仓库拆分运费")
        page.click(".modal-footer .btn-primary")
        page.wait_for_selector("#requirement-title", state="detached")
        settle(page, 800)
        check("create_requirement_success", proxy.counts.get("POST requirements", 0) == 1, proxy.counts)

        requirements = api_call(args.api, "GET", f"/api/requirements?project_id={project_id}", token=token)
        req = next((item for item in requirements if item["title"] == long_title), None)
        check("requirement_persisted", req is not None, len(requirements))

        # --- duplicate submit guard: slow POST + double submit ---
        proxy.delay["POST requirements"] = 1.5
        page.click(".project-management-header-actions .btn-primary")
        page.wait_for_selector("#requirement-title")
        page.fill("#requirement-title", f"重复提交检查需求-{stamp}")
        page.evaluate("document.querySelector('.modal-footer .btn-primary').click(); document.querySelector('.modal-footer .btn-primary').click()")
        page.wait_for_selector("#requirement-title", state="detached", timeout=15000)
        settle(page, 500)
        proxy.delay.pop("POST requirements", None)
        duplicated = [item for item in api_call(args.api, "GET", f"/api/requirements?project_id={project_id}", token=token)
                      if item["title"] == f"重复提交检查需求-{stamp}"]
        check("create_duplicate_submit_guard", len(duplicated) == 1, len(duplicated))

        # --- create failure: error visible, input kept, retry succeeds ---
        proxy.fail.add("POST requirements")
        page.click(".project-management-header-actions .btn-primary")
        page.wait_for_selector("#requirement-title")
        page.fill("#requirement-title", f"失败后可重试的需求-{stamp}")
        page.click(".modal-footer .btn-primary")
        page.wait_for_selector(".form-error", timeout=10000)
        error_text = page.inner_text(".form-error")
        kept_value = page.input_value("#requirement-title")
        check("create_failure_shows_error", "创建失败" in error_text, error_text)
        check("create_failure_keeps_input", kept_value == f"失败后可重试的需求-{stamp}", kept_value)
        proxy.fail.discard("POST requirements")
        page.click(".modal-footer .btn-primary")
        page.wait_for_selector("#requirement-title", state="detached", timeout=15000)
        settle(page, 600)
        retried = [item for item in api_call(args.api, "GET", f"/api/requirements?project_id={project_id}", token=token)
                   if item["title"] == f"失败后可重试的需求-{stamp}"]
        check("create_retry_after_failure", len(retried) == 1, len(retried))

        # --- drawer: acceptance criteria edit, ID preservation ---
        page.goto(f"{management}?tab=requirements", wait_until="networkidle")
        page.wait_for_selector(".project-management-table")
        page.click(f"tr:has-text('{long_title[:24]}') button:has-text('详情')")
        page.wait_for_selector(".management-detail-drawer")
        settle(page, 400)
        drawer_title = page.inner_text("#management-detail-title")
        check("drawer_matches_row", drawer_title == long_title, drawer_title)
        page.click("button:has-text('编辑验收标准')")
        page.fill(".management-detail-label textarea", "进入结算页并确认优惠券可选\n叠加优惠券后总价按最优方案计算（含会员价）\n跨区域订单按仓库拆分运费")
        page.click("button:has-text('保存验收标准')")
        page.wait_for_selector(".management-detail-feedback.is-success", timeout=10000)
        document, lag = read_with_lag(args.api, f"/api/requirements/{req['id']}", token)
        results["criteria_read_lag_seconds"] = lag
        first_ids = [item["id"] for item in (document.get("qa_model") or {}).get("criteria", [])]
        check("criteria_saved_feedback", "验收标准已保存" in page.inner_text(".management-detail-feedback"), first_ids)
        check("criteria_ids_created", first_ids == ["AC-001", "AC-002", "AC-003"], first_ids)

        page.click("button:has-text('编辑验收标准')")
        page.fill(".management-detail-label textarea", "进入结算页并确认优惠券可选\n叠加优惠券后总价按最优方案计算（含会员价与新人券）\n跨区域订单按仓库拆分运费\n新增一条支付失败重试标准")
        page.click("button:has-text('保存验收标准')")
        settle(page, 900)
        second_doc, second_lag = read_with_lag(
            args.api, f"/api/requirements/{req['id']}", token,
            expect=lambda payload: [
                item.get("description") for item in (payload.get("qa_model") or {}).get("criteria", [])
            ] == [
                "进入结算页并确认优惠券可选",
                "叠加优惠券后总价按最优方案计算（含会员价与新人券）",
                "跨区域订单按仓库拆分运费",
                "新增一条支付失败重试标准",
            ],
        )
        results["criteria_edit_read_lag_seconds"] = second_lag
        second = (second_doc.get("qa_model") or {}).get("criteria", [])
        second_ids = [item["id"] for item in second]
        check("criteria_ids_preserved_on_edit", second_ids[:3] == first_ids and len(second_ids) == 4, second_ids)
        check("criteria_text_updated", second[1]["description"].endswith("新人券）"), second[1]["description"])

        # --- create case from the drawer (requirement context) ---
        page.click(".management-detail-section:has(h4:text-is('关联用例')) button:has-text('新建用例')")
        page.wait_for_selector("#test-case-title")
        check("case_form_requirement_context", proxy.counts.get("GET test-cases", 0) >= 1, "form opened from drawer")
        page.fill("#test-case-title", "抽屉内新建并自动关联的用例")
        page.fill("#test-case-steps", "打开结算页\n选择优惠券并提交订单")
        page.fill("#test-case-expected-result", "总价按最优优惠计算")
        page.fill("#test-case-tags", "checkout, coupon, regression")
        page.click(".modal-footer .btn-primary")
        page.wait_for_selector("#test-case-title", state="detached")
        settle(page, 900)
        drawer_cases = page.locator(".management-detail-case-list li").count()
        check("case_created_from_drawer_linked", drawer_cases == 1, drawer_cases)
        check("drawer_fact_count_matches", "已关联 1 个用例" in page.inner_text(".management-detail-facts"),
              page.inner_text(".management-detail-facts"))

        # --- two independent cases ---
        case_ids = {}
        for title in ("待关联的独立用例", "关联失败后的独立用例"):
            created = api_call(args.api, "POST", "/api/test-cases", {
                "project_id": project_id, "title": title, "requirement_id": None,
                "steps": ["步骤一"], "expected_result": "结果", "priority": "P2",
                "automation_status": "MANUAL", "tags": ["manual"],
            }, token)
            case_ids[title] = created["id"]
        check("independent_cases_created", len(case_ids) == 2, case_ids)

        # --- link failure then success ---
        proxy.fail.add("PATCH test-cases")
        page.goto(f"{management}?tab=requirements&detail={req['id']}", wait_until="networkidle")
        page.wait_for_selector(".management-detail-drawer")
        settle(page, 400)
        page.select_option(".management-detail-section:has(h4:text-is('关联已有用例')) select", case_ids["关联失败后的独立用例"])
        page.click(".management-detail-section:has(h4:text-is('关联已有用例')) button:has-text('关联')")
        page.wait_for_selector(".management-detail-feedback.is-error", timeout=10000)
        link_error = page.inner_text(".management-detail-feedback.is-error")
        selected_after_failure = page.input_value(".management-detail-section:has(h4:text-is('关联已有用例')) select")
        after_failure = api_call(args.api, "GET", f"/api/test-cases/{case_ids['关联失败后的独立用例']}", token=token)
        check("link_failure_shows_error", "关联失败" in link_error, link_error)
        check("link_failure_keeps_selection", selected_after_failure == case_ids["关联失败后的独立用例"], selected_after_failure)
        check("link_failure_no_false_relation", after_failure.get("requirement_id") is None, after_failure.get("requirement_id"))
        check("link_failure_count_unchanged", "已关联 1 个用例" in page.inner_text(".management-detail-facts"))

        proxy.fail.discard("PATCH test-cases")
        page.click(".management-detail-section:has(h4:text-is('关联已有用例')) button:has-text('关联')")
        page.wait_for_selector(".management-detail-feedback.is-success", timeout=10000)
        settle(page, 600)
        check("link_success_feedback", "用例已关联" in page.inner_text(".management-detail-feedback.is-success"))
        linked, _ = read_with_lag(
            args.api, f"/api/test-cases/{case_ids['关联失败后的独立用例']}", token,
            expect=lambda payload: payload.get("requirement_id") == req["id"],
        )
        check("link_success_persisted", linked.get("requirement_id") == req["id"], linked.get("requirement_id"))

        page.select_option(".management-detail-section:has(h4:text-is('关联已有用例')) select", case_ids["待关联的独立用例"])
        page.click(".management-detail-section:has(h4:text-is('关联已有用例')) button:has-text('关联')")
        settle(page, 900)
        check("drawer_linked_three", page.locator(".management-detail-case-list li").count() == 3,
              page.locator(".management-detail-case-list li").count())

        # --- cross-view consistency: drawer / list / trace / filter ---
        page.goto(f"{management}?tab=cases&requirement={req['id']}", wait_until="networkidle")
        page.wait_for_selector(".project-management-table")
        settle(page, 400)
        filtered_rows = page.locator(".project-management-table tbody tr").count()
        summary = page.inner_text(".project-management-filter-summary")
        check("cases_filter_rows_match_linked", filtered_rows == 3, filtered_rows)
        check("cases_filter_summary_matches", "显示 3 / 3" in summary, summary)

        page.goto(f"{management}?tab=traceability&trace={req['id']}", wait_until="networkidle")
        page.wait_for_selector(".management-trace-table")
        settle(page, 400)
        trace_rows = page.locator(".management-trace-case-list li").count()
        trace_text = page.inner_text(".management-trace-table")
        check("trace_rows_match", trace_rows == 3, trace_rows)
        check("trace_count_matches", "3" in trace_text, trace_text[:200])

        # --- reload and deep link persistence ---
        page.goto(f"{management}?tab=requirements&detail={req['id']}", wait_until="networkidle")
        page.wait_for_selector(".management-detail-drawer")
        settle(page, 600)
        drawer_text = page.inner_text(".management-detail-drawer")
        check("deep_link_title", long_title in drawer_text, drawer_text[:120])
        check("deep_link_criteria_persisted", "新增一条支付失败重试标准" in drawer_text)
        check("deep_link_cases_persisted", page.locator(".management-detail-case-list li").count() == 3)

        # --- error state must not look like an empty list ---
        proxy.fail.add("GET requirements")
        page.goto(f"{management}?tab=requirements", wait_until="networkidle")
        settle(page, 800)
        error_region = page.inner_text(".project-management-state")
        check("load_failure_not_empty", "加载失败" in error_region and "暂无需求" not in error_region, error_region)
        check("load_failure_offers_retry", page.locator(".project-management-state button").count() >= 1, error_region)
        proxy.fail.discard("GET requirements")
        page.click(".project-management-state button")
        page.wait_for_selector(".project-management-table", timeout=15000)
        settle(page, 600)
        check("load_retry_recovers", page.locator(".project-management-table tbody tr").count() >= 3,
              page.locator(".project-management-table tbody tr").count())

        # --- screenshots at the three desktop viewports ---
        for width, height in ((1280, 800), (1440, 900), (1920, 1080)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{management}?tab=requirements&detail={req['id']}", wait_until="networkidle")
            page.wait_for_selector(".management-detail-drawer")
            settle(page, 700)
            page.screenshot(path=f"{args.shots}/closure-drawer-{width}.png")
            overflow = page.evaluate("document.querySelector('.management-detail-drawer').scrollWidth - document.querySelector('.management-detail-drawer').clientWidth")
            page_overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"drawer_no_horizontal_overflow_{width}", overflow <= 0, overflow)
            check(f"page_no_horizontal_overflow_{width}", page_overflow <= 0, page_overflow)
            page.goto(f"{management}?tab=requirements", wait_until="networkidle")
            page.wait_for_selector(".project-management-table")
            settle(page, 500)
            page.screenshot(path=f"{args.shots}/closure-requirements-{width}.png")
            row_text = page.inner_text(".project-management-table tbody tr:first-child")
            check(f"long_title_row_readable_{width}", long_title[:10] in row_text, row_text[:80])

        unexpected = [item for item in console_errors if "status of 500" not in item]
        check("console_errors", not unexpected, unexpected[:5])
        check("injected_500_observed", len(console_errors) >= 1, len(console_errors))
        browser.close()
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
