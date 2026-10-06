"""A real browser journey against a local site with deterministic planner/decision providers."""

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from app.api.tasks import task_runtime_service
from app.main import app as fastapi_app
from app.persistence.models import TaskORM
from app.services.decision_service import DecisionService
from app.services.task_runtime_service import TaskBlocked, TaskRuntimeService
from app.settings import settings
from project_model.models import DecisionResult
from qa_core.ai.models import AICompletionResponse, BrowserActionCandidate, BrowserAgentPlan
from qa_core.ai.registry import AIProviderRegistry


class SearchSiteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = '<title>Search</title><form action="/search"><input name="q" type="search" placeholder="Search"><button type="submit">Search</button></form>'
        elif path == "/search":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            body = f'<title>Results</title><h1>Results for {query}</h1><a href="/selenium">Selenium official site</a>'
        else:
            body = "<title>Selenium WebDriver</title><h1>Selenium WebDriver documentation</h1>"
        payload = f"<!doctype html><html><body>{body}</body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


class NotFoundSiteHandler(BaseHTTPRequestHandler):
    status_code = 200

    def do_GET(self):
        body = b"<!doctype html><html><title>404 Not Found</title><body><h1>Not Found</h1></body></html>"
        self.send_response(self.status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class Http404SiteHandler(NotFoundSiteHandler):
    status_code = 404


class FixturePlanner:
    provider_name = "e2e-planner-fixture"
    model = "deterministic-browser-plan"

    def __init__(self):
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        prompt = json.loads(request.prompt)
        page = prompt["current_page"]
        path = urlparse(page["url"]).path
        controls = page["interactive_elements"]

        def candidate(candidate_id, action_type, element, *, value=None, effect):
            return BrowserActionCandidate(
                candidate_id=candidate_id,
                action_type=action_type,
                target_id=element["id"],
                target=element.get("name") or element.get("placeholder") or "Selenium",
                value=value,
                reason_summary="This action is grounded in the current page observation.",
                expected_effect=effect,
                risk="LOW",
            )

        if path == "/":
            search = next(control for control in controls if control.get("role") == "textbox")
            if search.get("value") == "Selenium":
                plan = BrowserAgentPlan(
                    current_subgoal="Submit the Selenium search",
                    candidates=[
                        candidate(
                            "submit-search",
                            "press_key",
                            search,
                            value="Enter",
                            effect="Results for Selenium appear.",
                        )
                    ],
                )
            else:
                plan = BrowserAgentPlan(
                    subgoals=["Search for Selenium", "Open the Selenium site"],
                    current_subgoal="Enter the requested search term",
                    candidates=[
                        candidate(
                            "fill-search",
                            "fill",
                            search,
                            value="Selenium",
                            effect="Selenium is in the search box.",
                        )
                    ],
                )
        elif path == "/search":
            link = next(control for control in controls if control.get("role") == "link")
            plan = BrowserAgentPlan(
                current_subgoal="Open the observed Selenium result",
                candidates=[
                    candidate(
                        "open-selenium",
                        "navigate",
                        link,
                        effect="Selenium WebDriver documentation appears.",
                    )
                ],
            )
        else:
            plan = BrowserAgentPlan(
                goal_status="completed",
                completion_evidence=["Selenium WebDriver documentation"],
            )

        payload = plan.model_dump(mode="json")
        return AICompletionResponse(
            content=json.dumps(payload),
            structured_data=payload,
            provider=self.provider_name,
            model=self.model,
            invocation_id=f"e2e-ai-{self.calls}",
        )


class PopupRedirectPlanner(FixturePlanner):
    def __init__(self, propose_popup_followup=False):
        super().__init__()
        self.propose_popup_followup = propose_popup_followup

    async def complete(self, request):
        prompt = json.loads(request.prompt)
        page = prompt["current_page"]
        if self.propose_popup_followup and urlparse(page["url"]).path == "/landing":
            self.calls += 1
            plan = BrowserAgentPlan(
                current_subgoal="Inspect the trusted Selenium page",
                candidates=[
                    BrowserActionCandidate(
                        candidate_id="inspect-trusted-popup",
                        action_type="inspect",
                        target="Current page",
                        reason_summary="The current page is the trusted Selenium landing page.",
                        expected_effect="The current Selenium page is inspected.",
                        risk="LOW",
                    )
                ],
            )
            payload = plan.model_dump(mode="json")
            return AICompletionResponse(
                content=json.dumps(payload),
                structured_data=payload,
                provider=self.provider_name,
                model=self.model,
                invocation_id=f"popup-ai-{self.calls}",
            )
        if urlparse(page["url"]).path != "/s":
            return await super().complete(request)

        self.calls += 1
        link = next(item for item in page["interactive_elements"] if item.get("role") == "link")
        plan = BrowserAgentPlan(
            current_subgoal="Open the observed Selenium result",
            candidates=[
                BrowserActionCandidate(
                    candidate_id="open-selenium-popup",
                    action_type="click",
                    target_id=link["id"],
                    target=link.get("name") or "Selenium official site",
                    reason_summary="This action follows the observed official-site result.",
                    expected_effect="Selenium WebDriver documentation appears.",
                    risk="LOW",
                )
            ],
        )
        payload = plan.model_dump(mode="json")
        return AICompletionResponse(
            content=json.dumps(payload),
            structured_data=payload,
            provider=self.provider_name,
            model=self.model,
            invocation_id=f"popup-ai-{self.calls}",
        )


class NotFoundRecoveryPlanner:
    provider_name = "404-recovery-fixture"
    model = "deterministic-browser-plan"

    async def complete(self, _request):
        plan = BrowserAgentPlan(
            current_subgoal="Recover from the unavailable initial page",
            preferred_candidate_id="recover_back",
            candidates=[
                BrowserActionCandidate(
                    candidate_id="recover_back",
                    action_type="back",
                    target="Previous browser page",
                    reason_summary="The current page is a 404 response with no interactive controls.",
                    expected_effect="Return to a usable page.",
                    risk="LOW",
                )
            ],
        )
        payload = plan.model_dump(mode="json")
        return AICompletionResponse(
            content=json.dumps(payload),
            structured_data=payload,
            provider=self.provider_name,
            model=self.model,
            invocation_id="404-recovery-ai",
        )


@pytest.mark.asyncio
async def test_browser_agent_e2e_searches_and_verifies_with_real_playwright(
    test_db_session, tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SearchSiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)

    planner = FixturePlanner()
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: planner)
    decisions = []

    async def choose_with_fixture_jev(_service, request, **_kwargs):
        choice = next(option.key for option in request.options if option.key != "abstain")
        decisions.append(choice)
        return DecisionResult(
            choice=choice,
            provider="jev",
            model="deterministic-jev-fixture",
            confidence=0.99,
            probabilities={choice: 0.99},
            reason="Selected an observed, safe browser candidate.",
        )

    monkeypatch.setattr(DecisionService, "choose", choose_with_fixture_jev)
    task_id = uuid4().hex
    start_url = f"http://127.0.0.1:{server.server_port}/"
    task = TaskORM(
        id=task_id,
        type="EXPLORE_PAGE",
        goal="Search for Selenium and open the Selenium site",
        owner_id=uuid4().hex,
        inputs={
            "url": start_url,
            "max_browser_actions": 5,
            "require_jev_decisions": True,
            "observable_text_criteria": ["Selenium WebDriver documentation"],
        },
    )
    try:
        async with test_db_session() as session:
            session.add(task)
            await session.commit()

        result = await TaskRuntimeService()._browser_agent(task, {})

        assert result["verified"] is True
        assert result["final_url"] == f"http://127.0.0.1:{server.server_port}/selenium"
        assert result["goal_evidence"]["visible_text_criteria"] == ["Selenium WebDriver documentation"]
        assert [item["action"] for item in result["actions"]] == ["fill", "press_key", "navigate"]
        assert result["metrics"]["ai_calls"] == 3
        assert result["metrics"]["jev_decisions"] == 3
        assert result["metrics"]["jev_correct"] == 3
        assert len(decisions) == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_browser_agent_api_e2e_persists_jev_decisions_and_browser_evidence(
    client, tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SearchSiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)

    planner = FixturePlanner()
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: planner)
    decisions = []

    async def choose_with_fixture_jev(_service, request, **_kwargs):
        choice = next(option.key for option in request.options if option.key != "abstain")
        decisions.append(choice)
        return DecisionResult(
            choice=choice,
            provider="jev",
            model="deterministic-jev-fixture",
            confidence=0.99,
            probabilities={choice: 0.99},
            reason="Selected an observed, safe browser candidate.",
        )

    monkeypatch.setattr(DecisionService, "choose", choose_with_fixture_jev)
    monkeypatch.setattr(fastapi_app.state, "task_runtime", task_runtime_service, raising=False)
    start_url = f"http://127.0.0.1:{server.server_port}/"
    try:
        project = await client.post("/api/projects", json={"name": "Browser Journey API E2E"})
        assert project.status_code == 201, project.text
        await task_runtime_service.start()

        created = await client.post(
            "/api/tasks",
            json={
                "type": "EXPLORE_PAGE",
                "goal": "Search for Selenium and open the Selenium site",
                "project_id": project.json()["id"],
                "inputs": {
                    "url": start_url,
                    "max_browser_actions": 5,
                    "require_jev_decisions": True,
                    "observable_text_criteria": ["Selenium WebDriver documentation"],
                },
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]

        for _ in range(300):
            await asyncio.sleep(0.1)
            detail = await client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200, detail.text
            body = detail.json()
            if body["status"] in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}:
                break

        assert body["status"] == "COMPLETED", body.get("failure_reason")
        result = next(step for step in body["steps"] if step["key"] == "browser_agent")["outputs"]
        assert result["verified"] is True
        assert result["final_url"] == f"http://127.0.0.1:{server.server_port}/selenium"
        assert [item["action"] for item in result["actions"]] == ["fill", "press_key", "navigate"]
        assert result["metrics"]["ai_calls"] == 3
        assert result["metrics"]["jev_decisions"] == 3
        assert result["metrics"]["jev_correct"] == 3
        assert len(decisions) == 3
        assert len(body["decisions"]) == 3
        assert all(item["provider"] == "jev" and item["confidence"] == 0.99 for item in body["decisions"])
        evidence_types = {item["type"] for item in body["evidence"]}
        assert {"AccessibilityTree", "DOMSnapshot"} <= evidence_types
        event_types = {item["type"] for item in body["events"]}
        assert {
            "decision.created",
            "browser.action_started",
            "browser.action_completed",
            "browser.goal_completed",
        } <= event_types
    finally:
        await task_runtime_service.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_browser_agent_blocks_back_to_blank_when_no_prior_page_was_observed(
    test_db_session, tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), NotFoundSiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)
    planner = NotFoundRecoveryPlanner()
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: planner)

    async def jev_must_not_receive_unsafe_candidate(*_args, **_kwargs):
        pytest.fail("An unusable browser-history action must be rejected before Jev decision.")

    monkeypatch.setattr(DecisionService, "choose", jev_must_not_receive_unsafe_candidate)
    task = TaskORM(
        id=uuid4().hex,
        type="EXPLORE_PAGE",
        goal="Open this page and continue to a usable page.",
        owner_id=uuid4().hex,
        inputs={"url": f"http://127.0.0.1:{server.server_port}/missing", "require_jev_decisions": True},
    )
    try:
        async with test_db_session() as session:
            session.add(task)
            await session.commit()

        with pytest.raises(TaskBlocked) as blocked:
            await TaskRuntimeService()._browser_agent(task, {})

        assert blocked.value.failure_type == "NO_SAFE_HISTORY", blocked.value.details
        assert "没有执行后退操作" in str(blocked.value)
        assert blocked.value.details["action_executed"] is False
        assert blocked.value.details["current_url"] == f"http://127.0.0.1:{server.server_port}/missing"
        assert blocked.value.details["metrics"]["browser_actions"] == 0

        detail = await TaskRuntimeService().get(task.id)
        assert detail is not None
        blocked_event = next(event for event in detail.events if event.type == "browser.action_blocked")
        assert blocked_event.payload["action_executed"] is False
        assert not any(event.type == "browser.action_started" for event in detail.events)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_browser_agent_stops_on_initial_http_error_without_calling_ai_or_jev(
    test_db_session, tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Http404SiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)

    def provider_must_not_run(*_args, **_kwargs):
        pytest.fail("A page returned as HTTP 404 must stop before a model request.")

    monkeypatch.setattr(AIProviderRegistry, "get_provider", provider_must_not_run)
    monkeypatch.setattr(DecisionService, "choose", provider_must_not_run)
    task = TaskORM(
        id=uuid4().hex,
        type="EXPLORE_PAGE",
        goal="Open this page and continue to a usable page.",
        owner_id=uuid4().hex,
        inputs={"url": f"http://127.0.0.1:{server.server_port}/missing", "require_jev_decisions": True},
    )
    try:
        async with test_db_session() as session:
            session.add(task)
            await session.commit()

        with pytest.raises(TaskBlocked) as blocked:
            await TaskRuntimeService()._browser_agent(task, {})

        assert blocked.value.failure_type == "HTTP_STATUS_ERROR"
        assert "HTTP 404" in str(blocked.value)
        assert blocked.value.details["initial_http_status"] == 404
        assert blocked.value.details["action_executed"] is False
        assert blocked.value.details["metrics"]["browser_actions"] == 0

        detail = await TaskRuntimeService().get(task.id)
        assert detail is not None
        blocked_event = next(event for event in detail.events if event.type == "browser.action_blocked")
        assert blocked_event.payload["http_status"] == 404
        assert blocked_event.payload["action_executed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_browser_agent_reports_navigation_cause_and_closes_owned_browser(
    test_db_session, monkeypatch
):
    import playwright.async_api as playwright_api
    from app.services import task_runtime_service

    class FakePage:
        url = "about:blank"

        async def goto(self, *_args, **_kwargs):
            raise RuntimeError(
                "Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at "
                "https://shop.example/products?token=private-value"
            )

    class FakeContext:
        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        closed = False

        async def new_context(self, **_kwargs):
            return FakeContext()

        async def close(self):
            self.closed = True

    class FakePlaywright:
        stopped = False

        async def stop(self):
            self.stopped = True

    class FakePlaywrightManager:
        async def start(self):
            return playwright

    browser = FakeBrowser()
    playwright = FakePlaywright()
    monkeypatch.setattr(playwright_api, "async_playwright", lambda: FakePlaywrightManager())
    monkeypatch.setattr(task_runtime_service, "browser_proxy_options", lambda: None)

    async def launch(_playwright, **_kwargs):
        return browser

    monkeypatch.setattr(task_runtime_service, "launch_chromium", launch)
    task = TaskORM(
        id=uuid4().hex,
        type="EXPLORE_PAGE",
        goal="Open the product page.",
        owner_id=uuid4().hex,
        inputs={"url": "https://shop.example/products?token=private-value"},
    )
    async with test_db_session() as session:
        session.add(task)
        await session.commit()

    with pytest.raises(TaskBlocked) as blocked:
        await TaskRuntimeService()._browser_agent(task, {})

    assert blocked.value.failure_type == "NAVIGATION_FAILED"
    assert blocked.value.details["stage"] == "page_navigation"
    assert blocked.value.details["error_type"] == "RuntimeError"
    assert "net::ERR_TUNNEL_CONNECTION_FAILED" in blocked.value.details["error_message"]
    assert blocked.value.details["requested_url"] == "https://shop.example/products"
    assert "private-value" not in str(blocked.value)
    assert browser.closed
    assert playwright.stopped


@pytest.mark.asyncio
async def test_browser_agent_reports_low_confidence_jev_without_executing_action(
    test_db_session, tmp_path, monkeypatch
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SearchSiteHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: FixturePlanner())

    async def reject_low_confidence(_service, _request, **_kwargs):
        return DecisionResult(
            provider="fallback",
            fallback_used=True,
            reason="below_minimum_confidence",
            confidence=0.42,
        )

    monkeypatch.setattr(DecisionService, "choose", reject_low_confidence)
    task = TaskORM(
        id=uuid4().hex,
        type="EXPLORE_PAGE",
        goal="Search for Selenium and inspect the result.",
        owner_id=uuid4().hex,
        inputs={
            "url": f"http://127.0.0.1:{server.server_port}/",
            "require_jev_decisions": True,
        },
    )
    try:
        async with test_db_session() as session:
            session.add(task)
            await session.commit()

        with pytest.raises(TaskBlocked) as blocked:
            await TaskRuntimeService()._browser_agent(task, {})

        assert blocked.value.failure_type == "JEV_NO_DECISION"
        assert "0.42" in str(blocked.value)
        assert blocked.value.details["decision_failure"] == "below_minimum_confidence"
        assert blocked.value.details["jev_confidence"] == 0.42
        assert blocked.value.details["action_executed"] is False
        assert blocked.value.details["metrics"]["jev_failed"] == 1
        assert blocked.value.details["metrics"]["fallbacks"] == 0
        assert blocked.value.details["metrics"]["browser_actions"] == 0

        detail = await TaskRuntimeService().get(task.id)
        assert detail is not None
        blocked_event = next(event for event in detail.events if event.type == "browser.decision_blocked")
        assert blocked_event.payload["candidate_count"] == 1
        assert blocked_event.payload["failure_reason"] == "below_minimum_confidence"
        assert blocked_event.payload["confidence"] == 0.42
        assert blocked_event.payload["action_executed"] is False
        assert not any(event.type == "browser.action_started" for event in detail.events)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("landing_host", "should_block", "redirect_during_action_start"),
    [
        ("selenium.evil.com", True, False),
        ("selenium.dev", False, False),
        ("selenium.dev", True, True),
    ],
)
@pytest.mark.asyncio
async def test_browser_agent_checks_and_switches_to_popup_landing(
    landing_host, should_block, redirect_during_action_start, test_db_session, tmp_path, monkeypatch
):
    from app.services import task_runtime_service as runtime_module

    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path)
    planner = PopupRedirectPlanner(propose_popup_followup=redirect_during_action_start)
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: planner)

    decisions = []

    async def choose_with_fixture_jev(_service, request, **_kwargs):
        choice = next(option.key for option in request.options if option.key != "abstain")
        decisions.append(choice)
        return DecisionResult(
            choice=choice,
            provider="jev",
            model="deterministic-jev-fixture",
            confidence=0.99,
            probabilities={choice: 0.99},
            reason="Selected an observed, safe browser candidate.",
        )

    monkeypatch.setattr(DecisionService, "choose", choose_with_fixture_jev)
    real_launch = runtime_module.launch_chromium
    routed_requests = []

    class RoutedBrowser:
        def __init__(self, browser):
            self.browser = browser

        async def new_context(self, **options):
            context = await self.browser.new_context(ignore_https_errors=True, **options)

            async def serve_test_site(route):
                request_url = urlparse(route.request.url)
                routed_requests.append(route.request.url)
                if request_url.hostname == "www.baidu.com" and request_url.path == "/":
                    body = (
                        '<title>百度</title><form action="/s">'
                        '<input name="wd" type="search" placeholder="百度一下">'
                        '<button type="submit">百度一下</button></form>'
                    )
                    await route.fulfill(status=200, content_type="text/html", body=body)
                elif request_url.hostname == "www.baidu.com":
                    body = (
                        '<title>搜索结果</title><h1>Selenium</h1>'
                        '<a target="_blank" href="https://selenium.dev/redirect">'
                        "Selenium official website</a>"
                    )
                    await route.fulfill(status=200, content_type="text/html", body=body)
                elif request_url.hostname == "selenium.dev" and request_url.path == "/redirect":
                    await route.fulfill(
                        status=302,
                        headers={"location": f"https://{landing_host}/landing"},
                        body="",
                    )
                elif request_url.hostname == "selenium.dev":
                    body = "<title>Selenium WebDriver</title><h1>Selenium WebDriver documentation</h1>"
                    await route.fulfill(status=200, content_type="text/html", body=body)
                elif request_url.hostname == "selenium.evil.com":
                    body = "<title>Selenium</title><h1>Selenium fake download</h1>"
                    await route.fulfill(status=200, content_type="text/html", body=body)
                else:
                    await route.continue_()

            await context.route("**/*", serve_test_site)
            return context

        async def close(self):
            await self.browser.close()

    async def launch_routed_browser(playwright, **options):
        return RoutedBrowser(await real_launch(playwright, **options))

    monkeypatch.setattr(runtime_module, "launch_chromium", launch_routed_browser)
    real_execute = TaskRuntimeService._execute_browser_candidate
    executed_candidates = []
    current_page = {}

    async def execute_with_popup(page, candidate):
        current_page["page"] = page
        executed_candidates.append(candidate["candidate_id"])
        if candidate["candidate_id"] == "open-selenium-popup":
            popup = await page.context.new_page()
            await popup.goto(f"https://{landing_host}/landing", wait_until="domcontentloaded")
            current_page["page"] = popup
            return
        await real_execute(page, candidate)

    monkeypatch.setattr(
        TaskRuntimeService,
        "_execute_browser_candidate",
        staticmethod(execute_with_popup),
    )
    if redirect_during_action_start:
        real_event = TaskRuntimeService._browser_agent_event
        recorded_events = []

        async def event_with_delayed_redirect(
            service,
            task_id,
            event_type,
            title,
            summary="",
            *,
            status=None,
            duration_ms=None,
            metadata=None,
        ):
            recorded_events.append((event_type, metadata or {}))
            await real_event(
                service,
                task_id,
                event_type,
                title,
                summary,
                status=status,
                duration_ms=duration_ms,
                metadata=metadata,
            )
            if event_type == "browser.action_started" and (metadata or {}).get("candidate_id") == "inspect-trusted-popup":
                await current_page["page"].goto(
                    "https://selenium.evil.com/interstitial", wait_until="domcontentloaded"
                )

        monkeypatch.setattr(TaskRuntimeService, "_browser_agent_event", event_with_delayed_redirect)
    task = TaskORM(
        id=uuid4().hex,
        type="EXPLORE_PAGE",
        goal="Search for Selenium and open the Selenium official website",
        owner_id=uuid4().hex,
        inputs={
            "url": "https://www.baidu.com/",
            "trusted_domains": ["selenium.dev"],
            "max_browser_actions": 5,
            "require_jev_decisions": True,
        },
    )
    async with test_db_session() as session:
        session.add(task)
        await session.commit()

    if should_block:
        with pytest.raises(TaskBlocked) as blocked:
            await TaskRuntimeService()._browser_agent(task, {})

        assert blocked.value.failure_type == "OFFICIAL_DOMAIN_UNVERIFIED"
        assert blocked.value.details["stop_reason"] == "OFFICIAL_DOMAIN_UNVERIFIED"
        if redirect_during_action_start:
            assert planner.calls == 4
            assert len(decisions) == 4
            assert executed_candidates == ["fill-search", "submit-search", "open-selenium-popup"]
            assert blocked.value.details["metrics"]["browser_actions"] == 3
            assert blocked.value.details["current_url"] == "https://selenium.evil.com/interstitial"
            action_lifecycle = [
                event_type
                for event_type, metadata in recorded_events
                if metadata.get("candidate_id") == "inspect-trusted-popup"
                and event_type in {"browser.action_started", "browser.action_completed", "browser.action_blocked"}
            ]
            assert action_lifecycle == ["browser.action_started", "browser.action_blocked"]
        else:
            assert planner.calls == 3
            assert len(decisions) == 3
            assert executed_candidates == ["fill-search", "submit-search", "open-selenium-popup"]
    else:
        try:
            result = await TaskRuntimeService()._browser_agent(task, {})
        except TaskBlocked as error:
            async with test_db_session() as session:
                stored_task = await session.get(TaskORM, task.id)
                agent_state = ((stored_task.context or {}).get("browser_agent") if stored_task else {}) or {}
            raise AssertionError(
                (
                    error.failure_type,
                    error.details,
                    [
                        (
                            item.get("action"),
                            item.get("status"),
                            item.get("error_type"),
                            item.get("url_before"),
                            item.get("url_after"),
                            item.get("opened_tabs"),
                        )
                        for item in agent_state.get("history", [])
                    ],
                    planner.calls,
                    decisions,
                    routed_requests,
                )
            ) from error

        assert result["verified"] is True
        assert result["final_url"] == "https://selenium.dev/landing"
        assert [item["action"] for item in result["actions"]] == ["fill", "press_key", "click"]
        assert planner.calls == 4
        assert len(decisions) == 3
