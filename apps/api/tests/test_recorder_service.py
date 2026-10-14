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
                    action="click",
                    locator=RecorderLocator(kind="role", value="button", name="Submit"),
                    frame_path=["iframe#checkout"],
                    description="Submit order",
                ),
                RecorderStep(
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
    assert '.get_by_role("textbox", name="Search", exact=True).fill("Selenium")' in source
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
    assert 'page.goto("https://example.test/checkout")' in generated


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
    assert bundle["steps"][0]["url"] == "https://example.test/save"
    assert [item["candidate_id"] for item in bundle["steps"][0]["evidence"]["locator_candidates"]] == ["candidate_1"]
    assert "ada@example.test" not in str(bundle)
    assert "token=secret" not in str(bundle)


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


@pytest.fixture(autouse=True)
def isolated_ai_persistence(test_db_session):
    """All provider governance and locator history use the isolated test database."""
