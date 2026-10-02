from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.browser_proxy import browser_proxy_options
from app.services.recorder_service import (
    BrowserRecorderService,
    RecorderGenerateRequest,
    RecorderLocator,
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
async def test_recorder_uses_jev_choice_and_verifies_it_with_playwright():
    class LocatorStub:
        async def count(self):
            return 1

        async def is_visible(self):
            return True

        async def is_enabled(self):
            return True

        async def click(self, **_kwargs):
            return None

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
    page = MagicMock()
    page.get_by_test_id.return_value = LocatorStub()
    service = BrowserRecorderService(decision_service, settings_service)
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

    selection = await service._select_locator_candidate(page, event, "recorder-session")

    assert selection["selected_candidate"]["kind"] == "test_id"
    assert selection["summary"]["provider"] == "jev"
    assert selection["summary"]["confidence"] == 0.91
    assert selection["verification"] == {
        "unique": True,
        "visible": True,
        "enabled": True,
        "editable": None,
        "clickable": True,
        "verified": True,
    }
    assert any(item["type"] == "decision_completed" for item in selection["trace"])
    decision_service.choose.assert_awaited_once()


def test_browser_proxy_splits_credentials_and_bypasses_local_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "browser_proxy_url", "http://alice:p%40ss@proxy.example.com:3128")
    monkeypatch.setattr(settings, "browser_proxy_bypass", "localhost,127.0.0.1")

    assert browser_proxy_options() == {
        "server": "http://proxy.example.com:3128",
        "username": "alice",
        "password": "p@ss",
        "bypass": "localhost,127.0.0.1",
    }


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
async def test_failed_initial_navigation_keeps_session_open(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock(url="about:blank")
    page.goto = AsyncMock(side_effect=RuntimeError("ERR_NETWORK_ACCESS_DENIED"))
    context = MagicMock()
    context.add_init_script = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    service = BrowserRecorderService()
    monkeypatch.setattr(service, "_start_playwright", AsyncMock(return_value=playwright))
    monkeypatch.setattr("app.services.recorder_service.browser_proxy_options", lambda: None)

    session = await service.create_session(
        "owner", RecorderSessionCreate(project_id="project", start_url="https://www.google.com")
    )

    assert await service.get(session.id, "owner") is session
    assert session.requested_url == "https://www.google.com"
    assert session.navigation_error == "ERR_NETWORK_ACCESS_DENIED"
    context.close.assert_not_awaited()
    browser.close.assert_not_awaited()
    await service.close(session.id, "owner")


@pytest.fixture(autouse=True)
def isolated_ai_persistence(test_db_session):
    """All provider governance and locator history use the isolated test database."""
