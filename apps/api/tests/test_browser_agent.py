import json

import pytest
from app.persistence.models import TaskORM
from app.repositories.task_repo import TaskRepository
from app.services.event_normalizer import normalize_event
from app.services.task_runtime_service import TaskRuntimeService
from project_model.models import DecisionResult
from project_model.task_models import TaskStatus, TaskStepStatus
from pydantic import ValidationError
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.models import AICompletionResponse, BrowserActionCandidate, BrowserAgentPlan
from qa_core.ai.trace import make_trace_event


def test_browser_agent_schema_bounds_candidates_and_uses_observed_targets():
    candidate = BrowserActionCandidate(
        candidate_id="open_pants",
        action_type="click",
        target_id="el_2",
        target="Pants",
        reason_summary="The visible category link matches the subgoal.",
        expected_effect="The pants listing appears.",
        evidence=["el_2 is visible", "el_2 is enabled"],
    )
    plan = BrowserAgentPlan(candidates=[candidate], preferred_candidate_id="open_pants")

    assert plan.candidates[0].target_id == "el_2"
    assert plan.preferred_candidate_id == "open_pants"
    with pytest.raises(ValidationError):
        BrowserAgentPlan(candidates=[candidate] * 6)
    with pytest.raises(ValidationError):
        BrowserActionCandidate(candidate_id="bad id", action_type="click")


def test_browser_safety_allows_browsing_and_cart_but_blocks_order_changes():
    assert classify_browser_action("back") == "READ_ONLY"
    assert classify_browser_action("scroll") == "READ_ONLY"
    assert classify_browser_action("filter", name="Search", input_type="submit") == "SAFE_INTERACTION"
    assert classify_browser_action("filter", name="Continue", input_type="submit") == "STATE_CHANGE"
    assert classify_browser_action("click", name="Add to cart", input_type="submit") == "SAFE_INTERACTION"
    assert classify_browser_action("click", name="添加到购物车", input_type="button") == "SAFE_INTERACTION"
    assert classify_browser_action("click", name="Checkout") == "STATE_CHANGE"
    assert classify_browser_action("click", name="Delete account") == "DESTRUCTIVE"


def test_browser_cart_intent_recognizes_common_chinese_request():
    assert TaskRuntimeService._browser_cart_intent("把黑色裤子添加到购物车")
    assert TaskRuntimeService._browser_cart_intent("Add the black trousers to my cart")
    assert not TaskRuntimeService._browser_cart_intent("Find black trousers")


def test_browser_cart_evidence_requires_a_new_observed_confirmation_or_count():
    before = {"count": 1, "confirmation": False}
    after = {"count": 2, "confirmation": False}
    assert TaskRuntimeService._browser_cart_verified(before, after)
    assert TaskRuntimeService._browser_cart_verified(before, {"count": None, "confirmation": True})
    assert not TaskRuntimeService._browser_cart_verified(before, {"count": 1, "confirmation": False})
    assert TaskRuntimeService._browser_cart_state(
        {"text": "Added to your cart", "elements": [{"name": "Cart (2)"}]}
    ) == {
        "badge_text": "Cart (2)",
        "badge_text_visible": False,
        "count": 2,
        "confirmation": True,
        "confirmation_text": "Added to your cart",
    }
    assert TaskRuntimeService._browser_cart_state({"text": "已添加到购物车", "elements": []})["confirmation"]


def test_browser_goal_completion_needs_page_or_cart_evidence():
    plan = BrowserAgentPlan(goal_status="completed", completion_evidence=["Black trousers"])
    observation = {
        "url": "https://shop.example/products/black-trousers",
        "title": "Black trousers",
        "text": "Black trousers",
    }

    assert not TaskRuntimeService._browser_goal_verified(
        "Find black trousers", plan, observation, [], ["not present"], cart_intent=True
    )
    assert TaskRuntimeService._browser_goal_verified(
        "Find black trousers",
        plan,
        observation,
        [{"status": "success"}],
        [],
        cart_intent=False,
    )
    assert not TaskRuntimeService._browser_goal_verified(
        "Find black trousers",
        plan,
        {"url": "/category/black", "title": "Black collection", "text": "Black collection"},
        [{"status": "success"}],
        [],
        cart_intent=False,
    )
    assert TaskRuntimeService._browser_goal_verified(
        "Add black trousers to cart",
        plan,
        observation,
        [{"action": "add_to_cart", "cart_verified": True}],
        [],
        cart_intent=True,
    )
    assert not TaskRuntimeService._browser_goal_verified(
        "Add black trousers to cart",
        plan,
        observation,
        [{"action": "add_to_cart", "cart_verified": False}],
        [],
        cart_intent=True,
    )


def test_browser_loop_guards_repeated_controls_and_url_bounces():
    history = [
        {"action": "click", "target_id": "el_2"},
        {"action": "click", "target_id": "el_2"},
    ]
    candidate = {"action_type": "click", "target_id": "el_2"}
    assert TaskRuntimeService._browser_repeats_same_target(history, candidate)
    assert not TaskRuntimeService._browser_repeats_same_target(history, {"action_type": "click", "target_id": "el_4"})
    assert not TaskRuntimeService._browser_repeats_same_target(history, {"action_type": "scroll", "target_id": "el_2"})
    assert TaskRuntimeService._browser_url_loop(["/a", "/b", "/a", "/b", "/a"])
    assert not TaskRuntimeService._browser_url_loop(["/home", "/pants", "/product", "/cart"])
    assert not TaskRuntimeService._browser_has_safe_back_target([])
    assert not TaskRuntimeService._browser_has_safe_back_target(["https://shop.example/404"])
    assert TaskRuntimeService._browser_has_safe_back_target(["https://shop.example/404", "about:blank"])
    assert TaskRuntimeService._browser_has_safe_back_target(
        ["https://shop.example/", "https://shop.example/products"]
    )


def test_browser_navigation_failure_keeps_actionable_redacted_cause():
    error = RuntimeError(
        "Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://shop.example/products?token=private-value"
    )

    blocked = TaskRuntimeService._browser_navigation_failure(
        error,
        "https://shop.example/products?token=private-value",
    )

    assert blocked.failure_type == "NAVIGATION_FAILED"
    assert blocked.details["stage"] == "page_navigation"
    assert blocked.details["error_type"] == "RuntimeError"
    assert "net::ERR_TUNNEL_CONNECTION_FAILED" in blocked.details["error_message"]
    assert blocked.details["requested_url"] == "https://shop.example/products"
    assert "private-value" not in str(blocked)
    assert "private-value" not in json.dumps(blocked.details)


def test_browser_jev_fallback_is_explicit_and_uses_only_valid_candidate_ids():
    candidates = [
        {"candidate_id": "pants", "action_type": "click"},
        {"candidate_id": "help", "action_type": "navigate"},
    ]
    selected, provider, reason = TaskRuntimeService._choose_browser_candidate(
        candidates,
        "pants",
        jev_result=DecisionResult(provider="fallback", fallback_used=True, reason="timeout"),
    )
    assert selected["candidate_id"] == "pants"
    assert provider == "ai-ranking"
    assert reason == "timeout"

    selected, provider, reason = TaskRuntimeService._choose_browser_candidate(
        candidates[:1],
        "pants",
        jev_result=DecisionResult(
            provider="fallback",
            fallback_used=True,
            reason="below_minimum_confidence",
            confidence=0.42,
        ),
    )
    assert selected["candidate_id"] == "pants"
    assert provider == "single-candidate"
    assert reason == "below_minimum_confidence"

    selected, provider, reason = TaskRuntimeService._choose_browser_candidate(
        candidates,
        "missing",
        jev_result=DecisionResult(provider="jev", choice="not_a_candidate", confidence=0.9),
    )
    assert selected["candidate_id"] == "pants"
    assert provider == "local-heuristic"
    assert reason == "jev_invalid_candidate"


def test_browser_agent_honors_required_jev_decision_for_a_single_candidate():
    assert TaskRuntimeService._browser_jev_needed(candidate_count=1, explicitly_required=True)
    assert TaskRuntimeService._browser_jev_needed(candidate_count=2, explicitly_required=False)
    assert not TaskRuntimeService._browser_jev_needed(candidate_count=1, explicitly_required=False)


def test_browser_rule_fallback_searches_only_observed_search_controls():
    goal = "打开浏览器访问百度，搜索 Selenium，然后进入 Selenium 官网"
    observation = {
        "url": "https://www.baidu.com/",
        "elements": [
            {
                "id": "el_search",
                "tag": "input",
                "type": "text",
                "name": "搜索框",
                "placeholder": "搜索",
                "value": "",
                "visible": True,
                "enabled": True,
            },
            {
                "id": "el_submit",
                "tag": "button",
                "role": "button",
                "name": "百度一下",
                "visible": True,
                "enabled": True,
            },
        ],
    }

    plan = TaskRuntimeService._browser_rule_fallback_plan(goal, observation, [])

    assert plan is not None
    assert len(plan.candidates) == 1
    assert plan.candidates[0].action_type == "fill"
    assert plan.candidates[0].target_id == "el_search"
    assert plan.candidates[0].value == "Selenium"
    assert plan.preferred_candidate_id is None


def test_browser_rule_fallback_submits_search_and_opens_observed_official_link():
    goal = "搜索 Selenium，然后进入 Selenium 官网"
    observation = {
        "url": "https://www.baidu.com/",
        "elements": [
            {
                "id": "el_search",
                "tag": "input",
                "type": "text",
                "name": "搜索框",
                "value": "Selenium",
                "visible": True,
                "enabled": True,
            },
            {
                "id": "el_submit",
                "tag": "button",
                "role": "button",
                "name": "百度一下",
                "visible": True,
                "enabled": True,
            },
        ],
    }
    history = [{"action": "fill", "value": "Selenium", "status": "success"}]

    submit_plan = TaskRuntimeService._browser_rule_fallback_plan(goal, observation, history)
    assert submit_plan is not None
    assert submit_plan.candidates[0].action_type == "click"
    assert submit_plan.candidates[0].target_id == "el_submit"

    results = {
        "url": "https://www.baidu.com/s?wd=Selenium",
        "elements": [
            {
                "id": "el_official",
                "tag": "a",
                "role": "link",
                "name": "Selenium 官网",
                "href": "https://www.selenium.dev/",
                "_href": "https://www.selenium.dev/",
                "visible": True,
                "enabled": True,
            }
        ],
    }
    official_plan = TaskRuntimeService._browser_rule_fallback_plan(
        goal, results, history, trusted_domains=["selenium.dev"]
    )

    assert official_plan is not None
    assert official_plan.candidates[0].action_type == "navigate"
    assert official_plan.candidates[0].target_id == "el_official"


def test_browser_rule_fallback_does_not_repeat_search_or_invent_controls():
    goal = "搜索 Selenium，然后进入 Selenium 官网"
    observation = {
        "url": "https://www.baidu.com/",
        "elements": [
            {
                "id": "el_search",
                "tag": "input",
                "type": "search",
                "name": "Search",
                "value": "Selenium",
                "visible": True,
                "enabled": True,
            }
        ],
    }

    waiting = TaskRuntimeService._browser_rule_fallback_plan(
        goal,
        observation,
        [{"action": "press_key", "value": "Enter", "status": "success"}],
    )
    assert waiting is not None
    assert waiting.candidates[0].action_type == "wait"
    assert waiting.candidates[0].value == "700"
    assert (
        TaskRuntimeService._browser_rule_fallback_plan(
            goal,
            observation,
            [
                {"action": "press_key", "value": "Enter", "status": "success"},
                {"action": "wait", "value": "700", "status": "partial"},
                {"action": "wait", "value": "700", "status": "partial"},
            ],
        )
        is None
    )
    assert (
        TaskRuntimeService._browser_rule_fallback_plan(
            goal,
            {"url": observation["url"], "elements": []},
            [],
        )
        is None
    )


def test_browser_rule_fallback_does_not_guess_an_unrelated_single_input():
    plan = TaskRuntimeService._browser_rule_fallback_plan(
        "打开百度，搜索 Selenium，然后进入 Selenium 官网",
        {
            "url": "https://www.baidu.com/",
            "elements": [
                {
                    "id": "el_email",
                    "tag": "input",
                    "type": "text",
                    "name": "Email address",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "id": "el_continue",
                    "tag": "button",
                    "role": "button",
                    "name": "Continue",
                    "visible": True,
                    "enabled": True,
                },
            ],
        },
        [],
    )

    assert plan is None


def test_browser_rule_fallback_can_identify_one_input_from_its_search_submit_control():
    plan = TaskRuntimeService._browser_rule_fallback_plan(
        "打开百度，搜索 Selenium，然后进入 Selenium 官网",
        {
            "url": "https://www.baidu.com/",
            "elements": [
                {
                    "id": "el_query",
                    "tag": "input",
                    "type": "text",
                    "name": "",
                    "visible": True,
                    "enabled": True,
                },
                {
                    "id": "el_submit",
                    "tag": "button",
                    "role": "button",
                    "name": "百度一下",
                    "visible": True,
                    "enabled": True,
                },
            ],
        },
        [],
    )

    assert plan is not None
    assert plan.candidates[0].target_id == "el_query"
    assert plan.candidates[0].action_type == "fill"


def test_browser_rule_fallback_completes_only_after_verified_official_site_navigation():
    goal = "搜索 Selenium，然后进入 Selenium 官网"
    observation = {
        "url": "https://www.selenium.dev/",
        "title": "Selenium WebDriver",
        "text": "Selenium documentation",
        "elements": [],
    }
    history = [
        {
            "action": "navigate",
            "status": "success",
            "target": "Selenium 官网",
            "url_after": "https://www.selenium.dev/",
        }
    ]

    assert TaskRuntimeService._browser_rule_fallback_plan(goal, observation, history) is None

    plan = TaskRuntimeService._browser_rule_fallback_plan(
        goal, observation, history, trusted_domains=["selenium.dev"]
    )

    assert plan is not None
    assert plan.goal_status == "completed"
    assert "www.selenium.dev" in plan.completion_evidence
    assert "selenium" in plan.completion_evidence
    assert not TaskRuntimeService._browser_goal_verified(goal, plan, observation, history, [], False)
    assert TaskRuntimeService._browser_goal_verified(
        goal, plan, observation, history, [], False, trusted_domains=["selenium.dev"]
    )

    mismatched_navigation = [{**history[0], "url_after": "https://example.test/"}]
    assert TaskRuntimeService._browser_rule_fallback_plan(
        goal, observation, mismatched_navigation, trusted_domains=["selenium.dev"]
    ) is None


def test_browser_official_site_verification_rejects_brand_spoofed_domains():
    goal = "搜索 Selenium，然后进入 Selenium 官网"
    assert TaskRuntimeService._browser_official_entry_url_allowed("https://www.baidu.com/", [])
    assert not TaskRuntimeService._browser_official_entry_url_allowed("https://evil.baidu.com/", [])
    assert not TaskRuntimeService._browser_official_entry_url_allowed("http://www.baidu.com/", [])
    assert TaskRuntimeService._browser_official_entry_url_allowed(
        "https://docs.selenium.dev/", ["selenium.dev"]
    )
    assert not TaskRuntimeService._browser_official_entry_url_allowed("https://docs.selenium.dev/", [])
    fake_results = {
        "url": "https://www.baidu.com/s?wd=Selenium",
        "elements": [{
            "id": "fake_official",
            "tag": "a",
            "name": "Selenium 官网",
            "href": "https://selenium.evil.com/",
            "_href": "https://selenium.evil.com/",
            "visible": True,
            "enabled": True,
        }],
    }
    assert TaskRuntimeService._browser_rule_fallback_plan(
        goal, fake_results, [], trusted_domains=["selenium.dev"]
    ) is None

    plan = BrowserAgentPlan(goal_status="completed", completion_evidence=["selenium.evil.com", "Selenium"])
    fake_page = {"url": "https://selenium.evil.com/", "title": "Selenium", "text": "Selenium official website"}
    fake_history = [{"action": "navigate", "status": "success", "url_after": fake_page["url"]}]
    assert not TaskRuntimeService._browser_goal_verified(
        goal, plan, fake_page, fake_history, [], False, trusted_domains=["selenium.dev"]
    )

    trusted_subdomain = {**fake_page, "url": "https://docs.selenium.dev/"}
    trusted_history = [{"action": "navigate", "status": "success", "url_after": trusted_subdomain["url"]}]
    assert TaskRuntimeService._browser_goal_verified(
        goal, plan, trusted_subdomain, trusted_history, [], False, trusted_domains=["selenium.dev"]
    )

    def rejection(action_type, href):
        return TaskRuntimeService._browser_navigation_candidate_rejection(
            goal,
            "https://www.baidu.com/s?wd=Selenium",
            action_type,
            {"tag": "a", "href": href, "_href": href},
            ["selenium.dev"],
        )

    assert rejection("navigate", "https://selenium.evil.com/") == "navigation_target_not_trusted"
    assert rejection("click", "https://selenium.evil.com/") == "navigation_target_not_trusted"
    assert rejection("navigate", "https://selenium.dev/") is None
    assert rejection("click", "https://www.baidu.com/search?q=Selenium") is None
    assert TaskRuntimeService._browser_navigation_candidate_rejection(
        goal,
        "https://www.baidu.com/s?wd=Selenium",
        "click",
        {"tag": "a", "href": "https://selenium.dev/", "_href": "https://selenium.dev/"},
        [],
    ) == "navigation_target_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://www.baidu.com/s?wd=Selenium",
        "https://selenium.evil.com/",
        ["selenium.dev"],
    ) == "navigation_landed_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://www.baidu.com/s?wd=Selenium",
        "https://docs.selenium.dev/",
        ["selenium.dev"],
    ) is None
    assert TaskRuntimeService._browser_navigation_candidate_rejection(
        goal,
        "https://selenium.dev/",
        "navigate",
        {"tag": "a", "href": "http://selenium.dev/", "_href": "http://selenium.dev/"},
        ["selenium.dev"],
    ) == "navigation_target_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://selenium.dev/",
        "http://selenium.dev/",
        ["selenium.dev"],
    ) == "navigation_landed_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://www.baidu.com/s?wd=Selenium",
        "https://www.selenium.dev/",
        ["selenium.dev"],
    ) is None
    assert TaskRuntimeService._browser_navigation_candidate_rejection(
        goal,
        "https://selenium.evil.com/",
        "click",
        {"tag": "a", "href": "https://selenium.evil.com/next", "_href": "https://selenium.evil.com/next"},
        ["selenium.dev"],
    ) == "navigation_target_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://selenium.evil.com/",
        "https://selenium.evil.com/next",
        ["selenium.dev"],
    ) == "navigation_landed_not_trusted"
    assert TaskRuntimeService._browser_navigation_candidate_rejection(
        goal,
        "https://selenium.dev/",
        "click",
        {"tag": "a", "href": "https://selenium.dev/next", "_href": "https://selenium.dev/next"},
        [],
    ) == "navigation_target_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://selenium.dev/",
        "https://selenium.dev/next",
        [],
    ) == "navigation_landed_not_trusted"
    assert TaskRuntimeService._browser_navigation_candidate_rejection(
        goal,
        "https://evil.baidu.com/s?wd=Selenium",
        "click",
        {
            "tag": "a",
            "href": "https://evil.baidu.com/next",
            "_href": "https://evil.baidu.com/next",
        },
        [],
    ) == "navigation_target_not_trusted"
    assert TaskRuntimeService._browser_navigation_landing_rejection(
        goal,
        "https://evil.baidu.com/s?wd=Selenium",
        "https://evil.baidu.com/next",
        [],
    ) == "navigation_landed_not_trusted"


@pytest.mark.asyncio
async def test_browser_agent_uses_explicit_rule_fallback_after_provider_error(client, test_db_session, monkeypatch):
    from app.api.tasks import task_runtime_service
    from qa_core.ai.registry import AIProviderRegistry

    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "打开百度，搜索 Selenium，然后进入 Selenium 官网",
            "inputs": {"url": "https://www.baidu.com/"},
        },
    )
    assert created.status_code == 201, created.text
    async with test_db_session() as session:
        task = await session.get(TaskORM, created.json()["id"])
        assert task is not None

    class BrokenProvider:
        provider_name = "openai-compatible"
        model = "space-bunny-free"

        async def complete(self, _request):
            raise RuntimeError("upstream timeout")

    async def reserve(_task_id):
        return True

    async def record_trace(*_args):
        return None

    monkeypatch.setattr(task_runtime_service, "_reserve_ai_call", reserve)
    monkeypatch.setattr(task_runtime_service, "_record_ai_trace", record_trace)
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: BrokenProvider())
    state = {"metrics": {}, "history": [], "subgoals": []}
    observation = {
        "url": "https://www.baidu.com/",
        "title": "百度一下，你就知道",
        "text": "",
        "accessibility_tree": "",
        "elements": [
            {
                "id": "el_search",
                "tag": "input",
                "type": "text",
                "name": "搜索框",
                "placeholder": "搜索",
                "value": "",
                "visible": True,
                "enabled": True,
            }
        ],
    }

    plan, ai_info = await task_runtime_service._browser_agent_candidates(task, observation, state)

    assert plan.candidates[0].action_type == "fill"
    assert plan.candidates[0].value == "Selenium"
    assert ai_info["provider"] == "rule-engine"
    assert ai_info["planner_mode"] == "rule-fallback"
    assert state["metrics"]["ai_fallback_active"] is True


@pytest.mark.asyncio
async def test_browser_agent_planner_prompt_is_bounded_and_omits_unrelated_input_values(
    client, test_db_session, monkeypatch
):
    from app.api.tasks import task_runtime_service
    from qa_core.ai.registry import AIProviderRegistry

    created = await client.post(
        "/api/tasks",
        json={"type": "EXPLORE_PAGE", "goal": "搜索 Selenium", "inputs": {"url": "https://example.test"}},
    )
    assert created.status_code == 201, created.text
    async with test_db_session() as session:
        task = await session.get(TaskORM, created.json()["id"])
        assert task is not None

    captured = {}

    class CapturingProvider:
        provider_name = "openai-compatible"
        model = "space-bunny-free"

        async def complete(self, request):
            captured["request"] = request
            response = {
                "candidates": [
                    {
                        "candidate_id": "search",
                        "action_type": "click",
                        "target_id": "el_search_button",
                        "target": "Search",
                        "reason_summary": "The observed search button submits the query.",
                        "expected_effect": "Search results appear.",
                        "risk": "LOW",
                    }
                ],
                "preferred_candidate_id": "search",
            }
            return AICompletionResponse(
                content=json.dumps(response),
                model=self.model,
                provider=self.provider_name,
                invocation_id="capture-invocation",
            )

    async def reserve(_task_id):
        return True

    async def record_trace(*_args):
        return None

    monkeypatch.setattr(task_runtime_service, "_reserve_ai_call", reserve)
    monkeypatch.setattr(task_runtime_service, "_record_ai_trace", record_trace)
    monkeypatch.setattr(AIProviderRegistry, "get_provider", lambda: CapturingProvider())

    elements = [
        {
            "id": "el_email",
            "tag": "input",
            "role": "textbox",
            "name": "Email",
            "type": "text",
            "value": "private@example.test",
            "visible": True,
            "enabled": True,
        },
        {
            "id": "el_search",
            "tag": "input",
            "role": "textbox",
            "name": "Search",
            "type": "text",
            "placeholder": "Search",
            "value": "Selenium",
            "visible": True,
            "enabled": True,
        },
        {
            "id": "el_search_button",
            "tag": "button",
            "role": "button",
            "name": "Search",
            "visible": True,
            "enabled": True,
        },
        {
            "id": "el_variant",
            "tag": "select",
            "role": "combobox",
            "name": "Size",
            "value": "M",
            "options": [{"value": str(i), "label": f"Option {i}", "enabled": True} for i in range(25)],
            "visible": True,
            "enabled": True,
        },
    ]
    elements.extend(
        {"id": f"el_link_{i}", "tag": "a", "role": "link", "name": f"Link {i}", "visible": True, "enabled": True}
        for i in range(36)
    )
    observation = {
        "url": "https://example.test/search",
        "title": "Search",
        "text": "visible text " * 1000,
        "accessibility_tree": "accessibility snapshot " * 1000,
        "elements": elements,
        "network": {"failed": 0},
        "state_hash": "state-1",
    }

    plan, _ai_info = await task_runtime_service._browser_agent_candidates(
        task, observation, {"metrics": {}, "history": [], "subgoals": []}
    )

    request = captured["request"]
    prompt = json.loads(request.prompt)
    controls = prompt["current_page"]["interactive_elements"]
    assert request.max_tokens == 2200
    assert request.timeout_seconds == 20
    assert request.max_retries == 0
    assert len(prompt["current_page"]["visible_text"]) == 3000
    assert len(prompt["current_page"]["accessibility_tree"]) == 4000
    assert len(controls) == 40
    assert "private@example.test" not in request.prompt
    assert next(row for row in controls if row["id"] == "el_search")["value"] == "Selenium"
    assert len(next(row for row in controls if row["id"] == "el_variant")["options"]) == 16
    assert plan.candidates[0].target_id == "el_search_button"


def test_browser_agent_runtime_events_keep_plain_status_and_advanced_decision_data():
    action = normalize_event(
        {
            "type": "browser.action_started",
            "payload": {"title": "正在执行：click · Pants", "summary": "The pants listing appears.", "action": "click"},
        },
        source="task",
        source_id="event-1",
        runtime_id="task-1",
        task_id="task-1",
    )
    decision = normalize_event(
        {
            "type": "decision_completed",
            "payload": {
                "title": "JEV 选择了浏览动作",
                "summary": "click · Pants",
                "candidate_summary": '[{"candidate_id":"pants"}]',
                "candidate_scores": '{"pants":0.9}',
            },
        },
        source="task",
        source_id="event-2",
        runtime_id="task-1",
        task_id="task-1",
    )

    assert action is not None and action.category == "browser"
    assert action.title == "正在执行：click · Pants"
    assert action.summary == "The pants listing appears."
    assert decision is not None and decision.category == "decision"
    assert decision.metadata["candidate_summary"] == '[{"candidate_id":"pants"}]'
    assert decision.metadata["candidate_scores"] == '{"pants":0.9}'

    provider_failure = normalize_event(
        {
            "type": "ai.trace",
            "payload": make_trace_event(
                "trace-1",
                "failed",
                stage="page_understanding",
                title="AI 页面分析失败",
                message="Provider 调用失败；页面没有执行本轮浏览操作。",
                metadata={
                    "provider_error": "timeout",
                    "planner_mode": "rule-fallback",
                    "upstream_provider": "openai-compatible",
                    "actions_already_executed": 2,
                    "current_url": "https://example.test/search",
                },
                status="FAILED",
            ).model_dump(mode="json"),
        },
        source="ai",
        source_id="event-3",
        runtime_id="task-1",
        task_id="task-1",
    )
    assert provider_failure is not None and provider_failure.category == "ai"
    assert provider_failure.summary == "Provider 调用失败；页面没有执行本轮浏览操作。"
    assert provider_failure.metadata["provider_error"] == "timeout"
    assert provider_failure.metadata["planner_mode"] == "rule-fallback"
    assert provider_failure.metadata["upstream_provider"] == "openai-compatible"
    assert provider_failure.metadata["actions_already_executed"] == 2
    assert provider_failure.metadata["current_url"] == "https://example.test/search"


@pytest.mark.asyncio
async def test_browser_agent_pause_keeps_step_pending_for_fresh_observation_on_resume(
    client, test_db_session, monkeypatch
):
    from app.api.tasks import task_runtime_service

    created = await client.post(
        "/api/tasks",
        json={
            "type": "EXPLORE_PAGE",
            "goal": "Pause browser for manual takeover",
            "inputs": {"url": "https://example.test"},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    async with test_db_session() as session:
        task = await session.get(TaskORM, task_id)
        assert task is not None
        step = (await TaskRepository(session).steps_for_task(task_id))[0]

    async def pause_after_action(_task_id, _step, *, deadline=None):
        async with test_db_session() as session:
            task = await session.get(TaskORM, task_id)
            assert task is not None
            task.status = TaskStatus.PAUSING.value
            await session.commit()
        return {"_pause_after_step": True, "current_url": "https://example.test/details"}

    monkeypatch.setattr(task_runtime_service, "_run_step_tool", pause_after_action)
    monkeypatch.setattr(task_runtime_service, "_workspace_source_snapshot", lambda _workspace_id: {})

    result = await task_runtime_service._execute_step(task, step)
    assert result == {"deferred_for_pause": True}
    assert await task_runtime_service._pause_at_boundary(task_id)
    paused = await task_runtime_service.get(task_id)
    assert paused is not None and paused.status == TaskStatus.PAUSED
    assert paused.steps[0].status == TaskStepStatus.PENDING
    assert paused.steps[0].outputs == {}
