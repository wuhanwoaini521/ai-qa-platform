import pytest
from app.persistence.models import TaskORM
from app.repositories.task_repo import TaskRepository
from app.services.event_normalizer import normalize_event
from app.services.task_runtime_service import TaskRuntimeService
from project_model.models import DecisionResult
from project_model.task_models import TaskStatus, TaskStepStatus
from pydantic import ValidationError
from qa_core.ai.browser_safety import classify_browser_action
from qa_core.ai.models import BrowserActionCandidate, BrowserAgentPlan


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
    ) == {"badge_text": "Cart (2)", "count": 2, "confirmation": True}
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
        candidates,
        "missing",
        jev_result=DecisionResult(provider="jev", choice="not_a_candidate", confidence=0.9),
    )
    assert selected["candidate_id"] == "pants"
    assert provider == "local-heuristic"
    assert reason == "jev_invalid_candidate"


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
