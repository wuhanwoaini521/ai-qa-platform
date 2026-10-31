import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.adapters.playwright.proxy import browser_proxy_options, launch_chromium
from app.services.recorder_service import (
    BrowserRecorderService,
    RecorderGenerateRequest,
    RecorderLocator,
    RecorderSession,
    RecorderSessionCreate,
    RecorderStep,
    RecorderStepsRevisionConflict,
    RecorderStreamReplaced,
    generate_python_case,
)
from app.settings import settings
from project_model.models import DecisionResult


def test_generator_creates_pytest_case_with_stable_frame_locator() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            test_name="submit_order",
            steps=[
                RecorderStep(action="navigate", url="http://127.0.0.1:8000/order", description="Open order"),
                RecorderStep(
                    id="step-submit",
                    action="click",
                    locator=RecorderLocator(kind="role", value="button", name="Submit"),
                    frame_path=["iframe#checkout"],
                    description="Submit order",
                ),
                RecorderStep(
                    id="step-confirm",
                    action="assert_text",
                    locator=RecorderLocator(kind="css", value="#status"),
                    value="Order saved",
                    description="Confirm order",
                ),
            ],
        )
    )

    compile(source, "recorded_case.py", "exec")
    assert "def test_submit_order():" in source
    assert 'page.frame_locator("iframe#checkout").get_by_role' in source
    assert 'expect(page.locator("#status")).to_contain_text("Order saved")' in source
    assert "qa_step_id=step-submit qa_evidence_id=recorder:step-submit" in source
    assert "qa_step_id=step-confirm qa_evidence_id=recorder:step-confirm" in source


def test_generator_supports_selecting_observed_discovery_values_without_changing_legacy_labels():
    source = generate_python_case(
        RecorderGenerateRequest(
            steps=[
                RecorderStep(
                    action="select",
                    locator=RecorderLocator(kind="label", value="Color"),
                    value="navy",
                    select_by_value=True,
                ),
                RecorderStep(
                    action="select",
                    locator=RecorderLocator(kind="label", value="Size"),
                    value="Large",
                ),
            ]
        )
    )

    assert '.select_option(value="navy")' in source
    assert '.select_option(label="Large")' in source


def test_generator_preserves_agent_search_submission_keypress() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            steps=[
                RecorderStep(
                    action="fill",
                    locator=RecorderLocator(kind="role", value="textbox", name="Search"),
                    value="Selenium",
                ),
                RecorderStep(
                    action="press", locator=RecorderLocator(kind="role", value="textbox", name="Search"), key="Enter"
                ),
            ]
        )
    )

    compile(source, "recorded_search.py", "exec")
    assert '.get_by_role("textbox", name="Search", exact=True).fill(os.getenv("QA_DATA_1_SEARCH", "Selenium"))' in source
    assert '.get_by_role("textbox", name="Search", exact=True).press("Enter")' in source


def test_locator_nth_zero_is_preserved_for_duplicate_matches() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            steps=[
                RecorderStep(
                    action="click",
                    locator=RecorderLocator(kind="role", value="button", name="Open", nth=0),
                )
            ]
        )
    )

    assert ".nth(0).click()" in source


def test_recorder_prefers_semantic_locator_candidates():
    steps = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "name": "Save",
                "candidates": [
                    {"kind": "css", "value": "button.primary"},
                    {"kind": "role", "value": "button", "name": "Save", "exact": True},
                    {"kind": "test_id", "value": "save"},
                ],
            }
        ]
    )

    assert steps[0]["locator"]["kind"] == "role"
    assert steps[0]["locator"]["name"] == "Save"


def test_recorder_step_uses_selected_candidate_and_keeps_decision_metadata():
    steps = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "candidates": [
                    {"kind": "role", "value": "button", "name": "Save", "exact": True},
                    {"kind": "test_id", "value": "save"},
                ],
                "locator_selection": {
                    "selected_candidate": {"kind": "test_id", "value": "save"},
                    "summary": {
                        "provider": "jev",
                        "model": "jev-test",
                        "confidence": 0.91,
                        "candidate_count": 2,
                        "candidate_id": "candidate_2",
                        "verified": True,
                        "fallback_reason": None,
                    },
                },
            }
        ]
    )

    assert steps[0]["locator"]["kind"] == "test_id"
    assert steps[0]["locator_decision"]["provider"] == "jev"
    assert steps[0]["locator_decision"]["confidence"] == 0.91


@pytest.mark.asyncio
async def test_recorder_uses_jev_choice_and_verifies_it_through_browser_runtime():
    settings_service = SimpleNamespace(
        get_runtime_config=AsyncMock(return_value=SimpleNamespace(enabled=True, timeout=2))
    )
    decision_service = SimpleNamespace(
        choose=AsyncMock(
            return_value=DecisionResult(
                choice="candidate_2",
                confidence=0.91,
                probabilities={"candidate_2": 0.91},
                provider="jev",
                model="jev-test",
            )
        )
    )
    browser_runtime = SimpleNamespace(
        verify_locator=AsyncMock(
            return_value={
                "match_count": 1,
                "unique": True,
                "visible": True,
                "enabled": True,
                "editable": None,
                "clickable": True,
                "verified": True,
            }
        )
    )
    service = BrowserRecorderService(decision_service, settings_service, browser_runtime=browser_runtime)
    event = {
        "action": "click",
        "tag": "button",
        "role": "button",
        "name": "Save",
        "text": "Save",
        "url": "https://example.test/form",
        "candidates": [
            {"kind": "role", "value": "button", "name": "Save", "exact": True},
            {"kind": "test_id", "value": "save"},
            {"kind": "css", "value": "button.primary"},
        ],
    }

    selection = await service._select_locator_candidate(None, event, "recorder-session", "browser-session")

    assert selection["selected_candidate"]["kind"] == "test_id"
    assert selection["summary"]["provider"] == "jev"
    assert selection["summary"]["confidence"] == 0.91
    assert selection["verification"] == {
        "match_count": 1,
        "unique": True,
        "visible": True,
        "enabled": True,
        "editable": None,
        "clickable": True,
        "verified": True,
    }
    assert any(item["type"] == "decision_completed" for item in selection["trace"])
    decision_service.choose.assert_awaited_once()
    assert browser_runtime.verify_locator.await_count == 4


@pytest.mark.asyncio
async def test_ai_locator_analysis_uses_verified_evidence_and_never_reports_fake_success(monkeypatch):
    from app.services import ai_runtime

    candidate = {
        "candidate_id": "candidate_1",
        "kind": "role",
        "value": "button",
        "name": "Save",
        "exact": True,
        "locator": 'get_by_role("button", name="Save")',
        "verification": {"match_count": 1, "unique": True, "visible": True, "enabled": True, "verified": True},
    }
    step = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "role": "button",
                "name": "Save",
                "url": "https://example.test/form?access_token=do-not-send",
                "frame_path": [],
                "candidates": [candidate],
                "locator_selection": {
                    "ranked_candidates": [candidate],
                    "selected_candidate": candidate,
                    "summary": {"provider": "local-strategy", "candidate_id": "candidate_1", "verified": True},
                    "verification": candidate["verification"],
                },
            }
        ]
    )[0]
    browser_runtime = SimpleNamespace(
        get_page=AsyncMock(return_value=SimpleNamespace(url="https://example.test/form")),
        verify_locator=AsyncMock(return_value=candidate["verification"]),
    )
    session = RecorderSession(
        id="recorder-session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step],
    )
    prompts = []

    class Orchestrator:
        async def complete(self, request):
            prompts.append(request.prompt)
            return SimpleNamespace(
                provider="openai-compatible",
                model="recorder-test-model",
                fallback_used=False,
                invocation_id="invocation-1",
                structured_data={
                    "candidate_id": "candidate_1",
                    "reason": "Unique semantic target",
                    "risk": "LOW",
                    "confidence": 0.9,
                },
            )

    monkeypatch.setattr(ai_runtime, "build_ai_orchestrator", lambda: Orchestrator())
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    result = await service.analyze_locator_with_ai(session, step["id"])
    assert result["status"] == "available"
    assert result["provider"] == "openai-compatible"
    assert result["candidate_id"] == "candidate_1"
    assert "do-not-send" not in prompts[0]
    assert "access_token" not in prompts[0]

    class FakeOrchestrator:
        async def complete(self, _request):
            return SimpleNamespace(
                provider="fake", model="fake", fallback_used=True, invocation_id=None, structured_data={}
            )

    monkeypatch.setattr(ai_runtime, "build_ai_orchestrator", lambda: FakeOrchestrator())
    unavailable = await service.analyze_locator_with_ai(session, step["id"])
    assert unavailable["status"] == "unavailable"
    assert unavailable["candidate_id"] is None
    assert unavailable["provider"] == "fake"


@pytest.mark.asyncio
async def test_ai_analysis_does_not_restore_a_step_edited_while_request_is_in_flight(monkeypatch):
    from app.services import ai_runtime

    candidate = {
        "candidate_id": "candidate_1",
        "kind": "role",
        "value": "button",
        "name": "Save",
        "exact": True,
        "locator": 'get_by_role("button", name="Save")',
    }
    step = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "role": "button",
                "name": "Save",
                "url": "https://example.test/form",
                "frame_path": [],
                "candidates": [candidate],
            }
        ]
    )[0]
    verification = {"match_count": 1, "unique": True, "visible": True, "enabled": True, "verified": True}
    browser_runtime = SimpleNamespace(
        get_page=AsyncMock(return_value=SimpleNamespace(url="https://example.test/form")),
        verify_locator=AsyncMock(return_value=verification),
    )
    session = RecorderSession(
        id="recorder-session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step],
    )

    class Orchestrator:
        async def complete(self, _request):
            session.steps[0] = RecorderStep.model_validate(
                {**session.steps[0], "action": "assert_visible", "description": "Edited while analyzing"}
            ).model_dump(mode="json")
            return SimpleNamespace(
                provider="openai-compatible",
                model="recorder-test-model",
                fallback_used=False,
                invocation_id="invocation-1",
                structured_data={"candidate_id": "candidate_1", "reason": "Verified target", "risk": "LOW"},
            )

    monkeypatch.setattr(ai_runtime, "build_ai_orchestrator", lambda: Orchestrator())
    result = await BrowserRecorderService(browser_runtime=browser_runtime).analyze_locator_with_ai(session, step["id"])

    assert session.steps[0]["action"] == "assert_visible"
    assert session.steps[0]["description"] == "Edited while analyzing"
    assert result["status"] == "invalid"
    assert result["candidate_id"] is None
    assert result["reason"] == "step_changed_during_analysis"


@pytest.mark.asyncio
async def test_locator_choice_is_reverified_before_it_updates_a_step():
    candidate = {
        "candidate_id": "candidate_1",
        "kind": "role",
        "value": "button",
        "name": "Save",
        "exact": True,
        "verification": {"verified": True},
    }
    step = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "role": "button",
                "name": "Save",
                "candidates": [candidate],
                "locator_selection": {"ranked_candidates": [candidate], "summary": {"provider": "local-strategy"}},
            }
        ]
    )[0]
    step["evidence"]["ai_analysis"] = {"status": "available", "candidate_id": "candidate_1"}
    verification = {"match_count": 1, "unique": True, "visible": True, "enabled": True, "verified": True}
    browser_runtime = SimpleNamespace(
        get_session=AsyncMock(return_value=object()),
        get_page=AsyncMock(return_value=SimpleNamespace(url="https://example.test/form")),
        verify_locator=AsyncMock(return_value=verification),
    )
    session = RecorderSession(
        id="recorder-session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step],
    )

    await BrowserRecorderService(browser_runtime=browser_runtime).apply_command(
        session,
        {
            "action": "verify_locator",
            "step_id": step["id"],
            "candidate_id": "candidate_1",
            "source": "ai",
        },
    )

    assert session.steps[0]["locator"]["kind"] == "role"
    assert session.steps[0]["evidence"]["decision"]["source"] == "ai"
    assert session.steps[0]["evidence"]["decision_history"][0]["candidate_id"] == "candidate_1"
    assert session.steps[0]["evidence"]["decision_history"][0]["source"] == "ai"
    browser_runtime.verify_locator.assert_awaited_once()


def test_browser_proxy_splits_credentials_and_bypasses_local_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "browser_proxy_url", "http://alice:p%40ss@proxy.example.com:3128")
    monkeypatch.setattr(settings, "browser_proxy_bypass", "localhost,127.0.0.1")

    assert browser_proxy_options() == {
        "server": "http://proxy.example.com:3128",
        "username": "alice",
        "password": "p@ss",
        "bypass": "localhost,127.0.0.1",
    }


@pytest.mark.asyncio
async def test_browser_launch_uses_installed_edge_when_bundled_chromium_is_denied() -> None:
    browser = object()
    launch = AsyncMock(side_effect=[RuntimeError("BrowserType.launch: spawn EPERM"), browser])
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    assert await launch_chromium(playwright) is browser
    assert launch.call_args_list[0].kwargs == {"headless": True}
    assert launch.call_args_list[1].kwargs == {"headless": True, "channel": "msedge"}


def test_recorder_step_evidence_is_versioned_bounded_and_redacts_private_input() -> None:
    secret = "P@ssword-DoNotPersist-123!"
    step = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "fill",
                "tag": "input",
                "type": "password",
                "role": "textbox",
                "name": "Account password",
                "value": secret,
                "value_redacted": True,
                "attributes": {"type": "password", "name": "account_password"},
                "url": "https://example.test/login?access_token=private",
                "frame_path": [],
                "bounding_box": {"x": 1, "y": 2, "width": 100, "height": 20},
                "parent_summary": "form login",
                "visible": True,
                "actionable": True,
                "candidates": [{"kind": "label", "value": "Account password", "exact": True}],
            }
        ]
    )[0]

    assert step["evidence"]["schema_version"] == 1
    assert step.get("value") is None and step["value_redacted"] is True
    assert step["evidence"]["element"]["attributes"]["name"] == "account_password"
    assert secret not in str(step)
    assert "access_token=private" not in str(step)

    private_steps = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "fill",
                "tag": "input",
                "name": "Contact phone",
                "attributes": {"name": "contact_phone"},
                "value": "415-555-0132",
            },
            {
                "action": "fill",
                "tag": "input",
                "name": "First name",
                "attributes": {"name": "first_name"},
                "value": "Ada Lovelace",
            },
        ]
    )
    assert all(item.get("value") is None and item["value_redacted"] for item in private_steps)
    assert "415-555-0132" not in str(private_steps)
    assert "Ada Lovelace" not in str(private_steps)

    session = RecorderSession(
        id="session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="session"),
        last_url="https://user:pass@example.test/account?email=ada%40example.test#token",
        requested_url="https://example.test/start?session=private",
        navigation_error="Navigation failed at https://example.test/path?access_token=private",
    )
    public_status = BrowserRecorderService.session_status(session)
    assert "user" not in str(public_status)
    assert "ada%40example.test" not in str(public_status)
    assert "private" not in str(public_status)

    private_url_step = RecorderStep(
        action="navigate",
        url="https://user:password@example.test/checkout?email=ada%40example.test#token",
    )
    generated = generate_python_case(RecorderGenerateRequest(steps=[private_url_step]))
    assert private_url_step.url == "https://example.test/checkout"
    assert "https://user:password@example.test" not in generated
    assert "ada%40example.test" not in generated
    assert 'page.goto(os.getenv("QA_BASE_URL", "https://example.test") + "/checkout")' in generated


def test_element_evidence_bundle_is_versioned_bounded_and_redacted() -> None:
    evidence = {
        "schema_version": 1,
        "element": {"tag": "button", "role": "button", "name": "Save", "text": "Save"},
        "context": {"url": "https://example.test/save?token=secret", "frame_path": []},
        "locator_candidates": [
            {
                "candidate_id": "candidate_1",
                "kind": "role",
                "value": "button",
                "name": "Save",
                "verification": {"verified": True},
            },
            {
                "candidate_id": "candidate_private",
                "kind": "text",
                "value": "ada@example.test",
                "verification": {"verified": True},
            },
        ],
        "decision": {"selected_candidate_id": "candidate_1", "source": "jev"},
        "decision_history": [{"candidate_id": "candidate_1", "source": "jev"}],
        "status": "available",
        "missing": [],
    }
    step = RecorderStep(
        action="click", evidence=evidence, locator=RecorderLocator(kind="role", value="button", name="Save")
    )
    session = RecorderSession(
        id="session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step.model_dump(mode="json")],
    )

    bundle = BrowserRecorderService.element_evidence_bundle(session)
    assert bundle["schema"] == "element-evidence-bundle"
    assert bundle["version"] == "v1.0"
    assert bundle["steps"][0]["step_id"] == step.id
    assert bundle["steps"][0]["evidence_id"] == f"recorder:{step.id}"
    assert bundle["steps"][0]["url"] == "https://example.test/save"
    assert [item["candidate_id"] for item in bundle["steps"][0]["evidence"]["locator_candidates"]] == ["candidate_1"]
    assert "ada@example.test" not in str(bundle)
    assert "token=secret" not in str(bundle)


@pytest.mark.parametrize("placeholder", ["***REDACTED***", "[REDACTED_EMAIL]", "<REDACTED_EMAIL>"])
@pytest.mark.parametrize("field", ["candidate_value", "candidate_name", "locator_value", "locator_name"])
def test_element_evidence_bundle_excludes_all_redaction_marker_forms(field: str, placeholder: str) -> None:
    candidate = {
        "candidate_id": "candidate_redacted" if field.startswith("candidate_") else "candidate_safe",
        "kind": "role",
        "value": placeholder if field == "candidate_value" else "button",
        "name": placeholder if field == "candidate_name" else "Submit",
        "verification": {"verified": True},
    }
    locator = RecorderLocator(
        kind="role",
        value=placeholder if field == "locator_value" else "button",
        name=placeholder if field == "locator_name" else "Submit",
    )
    step = RecorderStep(
        action="click",
        evidence={
            "schema_version": 1,
            "element": {"tag": "button", "role": "button", "name": "Submit", "text": "Submit"},
            "context": {"url": "https://example.test/", "frame_path": []},
            "locator_candidates": [candidate],
            "decision": {},
            "decision_history": [],
            "status": "available",
            "missing": [],
        },
        locator=locator,
    )
    session = RecorderSession(
        id="session",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step.model_dump(mode="json")],
    )

    bundle = BrowserRecorderService.element_evidence_bundle(session)
    evidence_candidates = bundle["steps"][0]["evidence"]["locator_candidates"]
    selected_locator = bundle["steps"][0]["locator"]
    if field.startswith("candidate_"):
        assert evidence_candidates == []
        assert selected_locator is not None
    else:
        assert evidence_candidates[0]["candidate_id"] == "candidate_safe"
        assert selected_locator is None


def test_sensitive_recorder_fill_uses_environment_without_embedding_a_secret() -> None:
    source = generate_python_case(
        RecorderGenerateRequest(
            steps=[
                RecorderStep(
                    id="step_abc123",
                    action="fill",
                    locator=RecorderLocator(kind="label", value="Password"),
                    value_redacted=True,
                    secret_env_var="QA_LOGIN_PASSWORD",
                )
            ]
        )
    )

    compile(source, "recorded_private_case.py", "exec")
    assert 'os.getenv("QA_LOGIN_PASSWORD")' in source
    assert "Set environment variable QA_LOGIN_PASSWORD" in source
    assert "P@ssword" not in source


def test_generated_case_uses_same_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    source = generate_python_case(RecorderGenerateRequest(steps=[]))
    namespace: dict[str, object] = {}
    exec(compile(source, "recorded_case.py", "exec"), namespace)
    monkeypatch.setenv("BROWSER_PROXY_URL", "socks5://proxy.example.com:1080")
    monkeypatch.setenv("BROWSER_PROXY_BYPASS", "localhost")

    assert namespace["_browser_proxy"]() == {
        "server": "socks5://proxy.example.com:1080",
        "bypass": "localhost",
    }
    assert "playwright.chromium.launch(headless=True, channel=channel" in source
    assert "'proxy': proxy" in source


@pytest.mark.asyncio
async def test_failed_initial_navigation_keeps_session_open() -> None:
    page = MagicMock(url="about:blank")
    runtime_session = SimpleNamespace(id="browser-session", current_url=page.url)
    browser_runtime = SimpleNamespace(
        create_session=AsyncMock(return_value=runtime_session),
        add_init_script=AsyncMock(),
        navigate=AsyncMock(side_effect=RuntimeError("ERR_NETWORK_ACCESS_DENIED")),
        close_session=AsyncMock(),
    )
    service = BrowserRecorderService(browser_runtime=browser_runtime)

    session = await service.create_session(
        "owner", RecorderSessionCreate(project_id="project", start_url="https://www.google.com")
    )

    assert await service.get(session.id, "owner") is session
    assert session.requested_url == "https://www.google.com"
    assert session.navigation_error == "ERR_NETWORK_ACCESS_DENIED"
    browser_runtime.close_session.assert_not_awaited()
    await service.close(session.id, "owner")
    browser_runtime.close_session.assert_awaited_once_with("browser-session")


@pytest.mark.asyncio
async def test_replayed_add_step_command_is_idempotent_by_step_id() -> None:
    browser_runtime = SimpleNamespace(
        get_session=AsyncMock(return_value=object()),
        get_page=AsyncMock(return_value=SimpleNamespace(url="about:blank")),
    )
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    step = {"id": "step-1", "action": "click", "description": "Open the panel"}
    command = {"action": "add_step", "step": step, "command_id": "client-command-1"}

    await service.apply_command(session, command)
    await service.apply_command(session, command)

    assert [item["id"] for item in session.steps] == ["step-1"]
    assert session.steps[0]["description"] == "Open the panel"


@pytest.mark.asyncio
async def test_replayed_navigation_command_id_does_not_repeat_browser_action() -> None:
    service = BrowserRecorderService(browser_runtime=SimpleNamespace())
    service._apply_command = AsyncMock(return_value="http://127.0.0.1:5183/")
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    command = {"action": "reload", "command_id": "navigation-command-1"}

    await service.apply_command(session, command)
    await service.apply_command(session, command)

    service._apply_command.assert_awaited_once_with(session, command)
    assert session.processed_navigation_command_ids == {"navigation-command-1": None}


@pytest.mark.parametrize(
    ("action", "method_name"),
    [("back", "go_back"), ("forward", "go_forward"), ("reload", "reload")],
)
@pytest.mark.asyncio
async def test_timed_out_non_idempotent_navigation_is_not_replayed_after_side_effect(
    action: str,
    method_name: str,
) -> None:
    side_effect_count = [0]

    async def apply_then_timeout(**_kwargs: object) -> None:
        side_effect_count[0] += 1
        raise TimeoutError("navigation wait timed out after the browser action")

    page = SimpleNamespace(
        url="http://127.0.0.1:5183/second",
        go_back=AsyncMock(side_effect=apply_then_timeout),
        go_forward=AsyncMock(side_effect=apply_then_timeout),
        reload=AsyncMock(side_effect=apply_then_timeout),
    )
    service = BrowserRecorderService(
        browser_runtime=SimpleNamespace(
            get_session=AsyncMock(return_value=object()),
            get_page=AsyncMock(return_value=page),
        )
    )
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    command = {"action": action, "command_id": f"navigation-{action}-1"}

    with pytest.raises(TimeoutError, match="after the browser action"):
        await service.apply_command(session, command)

    assert session.processed_navigation_command_ids == {command["command_id"]: None}
    assert await service.apply_command(session, command) is None
    getattr(page, method_name).assert_awaited_once()
    assert side_effect_count == [1]


@pytest.mark.asyncio
async def test_replayed_replace_steps_command_preserves_later_captured_steps() -> None:
    browser_runtime = SimpleNamespace(
        get_session=AsyncMock(return_value=object()),
        get_page=AsyncMock(return_value=SimpleNamespace(url="about:blank")),
    )
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    replacement_step = {"id": "replacement", "action": "click", "description": "Generated step"}
    captured_step = {"id": "captured", "action": "fill", "description": "Captured after replacement"}
    command = {
        "action": "replace_steps",
        "steps": [replacement_step],
        "command_id": "replace-1",
        "base_steps_revision": 0,
    }

    await service.apply_command(session, command)
    session.steps.append(captured_step)
    session.steps_revision += 1
    await service.apply_command(session, command)

    assert [step["id"] for step in session.steps] == ["replacement", "captured"]


@pytest.mark.asyncio
async def test_stale_replace_steps_command_does_not_overwrite_newer_recorded_steps() -> None:
    browser_runtime = SimpleNamespace(
        get_session=AsyncMock(return_value=object()),
        get_page=AsyncMock(return_value=SimpleNamespace(url="about:blank")),
    )
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[{"id": "existing", "action": "click", "description": "Existing"}],
        steps_revision=4,
    )
    command = {
        "action": "replace_steps",
        "steps": [{"id": "replacement", "action": "click", "description": "Stale replacement"}],
        "command_id": "replace-stale",
        "base_steps_revision": 4,
    }
    session.steps.append({"id": "newer", "action": "fill", "description": "Captured later"})
    session.steps_revision = 5

    with pytest.raises(RecorderStepsRevisionConflict, match="steps changed"):
        await service.apply_command(session, command)

    assert [step["id"] for step in session.steps] == ["existing", "newer"]


@pytest.mark.asyncio
async def test_step_metadata_command_is_applied_after_browser_runtime_expires() -> None:
    browser_runtime = SimpleNamespace(get_session=AsyncMock(return_value=None))
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[{"id": "step-1", "action": "click", "description": "Old description"}],
    )

    await service.apply_command(
        session,
        {
            "action": "edit_step",
            "step": {"id": "step-1", "action": "click", "description": "Updated description"},
            "command_id": "edit-1",
        },
    )

    assert session.steps[0]["description"] == "Updated description"
    browser_runtime.get_session.assert_not_awaited()


@pytest.mark.parametrize("operation", ["command", "snapshot", "ai-analysis", "jev-analysis"])
@pytest.mark.asyncio
async def test_recorder_close_waits_for_active_runtime_work(operation: str, monkeypatch) -> None:
    work_started = asyncio.Event()
    release_work = asyncio.Event()
    candidate = {
        "candidate_id": "candidate-1",
        "kind": "role",
        "value": "button",
        "name": "Save",
        "exact": True,
        "locator": 'get_by_role("button", name="Save")',
    }
    step = BrowserRecorderService.events_to_steps(
        [
            {
                "action": "click",
                "tag": "button",
                "role": "button",
                "name": "Save",
                "url": "https://example.test/form",
                "frame_path": [],
                "candidates": [candidate],
            }
        ]
    )[0]

    async def block_verify_locator(_browser_session_id, _candidate, _event):
        work_started.set()
        await release_work.wait()
        return {"match_count": 1, "unique": True, "visible": True, "enabled": True, "verified": True}

    browser_runtime = SimpleNamespace(
        close_session=AsyncMock(),
        get_page=AsyncMock(return_value=SimpleNamespace(url="https://example.test/form")),
        verify_locator=block_verify_locator,
    )
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
        steps=[step],
    )
    service._sessions[session.id] = session

    async def block_command(_session, _command):
        work_started.set()
        await release_work.wait()
        return None

    async def block_snapshot(_session):
        work_started.set()
        await release_work.wait()
        return {"type": "frame"}

    if operation == "command":
        service._apply_command = block_command
        active_work = asyncio.create_task(service.apply_command(session, {"action": "click"}))
    elif operation == "snapshot":
        service._page_snapshot = block_snapshot
        active_work = asyncio.create_task(service.page_snapshot(session))
    elif operation == "ai-analysis":
        from app.services import ai_runtime

        class FakeOrchestrator:
            async def complete(self, _request):
                return SimpleNamespace(
                    provider="fake", model="fake", fallback_used=True, invocation_id=None, structured_data={}
                )

        monkeypatch.setattr(ai_runtime, "build_ai_orchestrator", lambda: FakeOrchestrator())
        active_work = asyncio.create_task(service.analyze_locator_with_ai(session, step["id"]))
    else:
        from app.services.locator_decision_service import LocatorDecisionService

        async def decide(_pipeline, **kwargs):
            return {
                "summary": {"provider": "local-strategy", "fallback_used": True, "fallback_reason": "test"},
                "ranked_candidates": kwargs["candidates"],
                "trace": [],
            }

        monkeypatch.setattr(LocatorDecisionService, "decide", decide)
        active_work = asyncio.create_task(service.request_jev_locator_decision(session, step["id"]))
    await work_started.wait()

    closing = asyncio.create_task(service.close(session.id, session.owner_id))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(closing), timeout=0.02)
    browser_runtime.close_session.assert_not_awaited()

    release_work.set()
    await active_work
    await closing

    browser_runtime.close_session.assert_awaited_once_with(session.browser_session_id)
    assert await service.get(session.id, session.owner_id) is None


@pytest.mark.parametrize("operation", ["ai", "jev"])
@pytest.mark.asyncio
async def test_locator_analysis_queued_behind_close_is_rejected(operation: str) -> None:
    browser_runtime = SimpleNamespace(close_session=AsyncMock())
    service = BrowserRecorderService(browser_runtime=browser_runtime)
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    service._sessions[session.id] = session
    await session.lock.acquire()

    closing = asyncio.create_task(service.close(session.id, session.owner_id))
    await asyncio.sleep(0)
    if operation == "ai":
        analysis = asyncio.create_task(service.analyze_locator_with_ai(session, "missing-step"))
    else:
        analysis = asyncio.create_task(service.request_jev_locator_decision(session, "missing-step"))
    await asyncio.sleep(0)
    session.lock.release()

    await closing
    with pytest.raises(LookupError, match="closed or expired"):
        await analysis
    assert session.closed is True
    assert await service.get(session.id, session.owner_id) is None


@pytest.mark.asyncio
async def test_recorder_stream_generation_fences_old_commands_waiting_for_the_session_lock() -> None:
    service = BrowserRecorderService(browser_runtime=SimpleNamespace(close_session=AsyncMock()))
    session = RecorderSession(
        id="session-1",
        owner_id="owner",
        project_id="project",
        runtime_session=SimpleNamespace(id="browser-session"),
    )
    service._sessions[session.id] = session
    service._apply_command = AsyncMock(return_value=None)
    service._page_snapshot = AsyncMock(return_value={"type": "frame"})
    old_generation = await service.claim_websocket_stream(session)

    await session.lock.acquire()
    replacement = asyncio.create_task(service.claim_websocket_stream(session))
    await asyncio.sleep(0)
    stale_command = asyncio.create_task(
        service.apply_command(session, {"action": "click"}, stream_generation=old_generation)
    )
    await asyncio.sleep(0)
    session.lock.release()

    new_generation = await replacement
    assert new_generation == old_generation + 1
    with pytest.raises(RecorderStreamReplaced):
        await stale_command
    with pytest.raises(RecorderStreamReplaced):
        await service.page_snapshot(session, stream_generation=old_generation)

    assert await service.page_snapshot(session, stream_generation=new_generation) == {"type": "frame"}
    service._apply_command.assert_not_awaited()
    service._page_snapshot.assert_awaited_once_with(session)


@pytest.fixture(autouse=True)
def isolated_ai_persistence(test_db_session):
    """All provider governance and locator history use the isolated test database."""
