from __future__ import annotations

import asyncio
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

import app.adapters.playwright.browser_runtime as browser_runtime_module
import pytest
from app.adapters.playwright.browser_runtime import PlaywrightBrowserRuntime
from app.ports.browser_runtime import BrowserRuntime
from app.services.recorder_service import (
    RECORDER_INIT_SCRIPT,
    RecorderGenerateRequest,
    RecorderLocator,
    RecorderStep,
    generate_python_case,
)

BROWSER_REQUEST_LOG = {}


def _fake_browser_runtime(monkeypatch, *, session_ttl_seconds=60, page_error=None, browser_close_error=None):
    class FakePage:
        url = "about:blank"

        def __init__(self):
            self.closed = False
            self.handlers: dict[str, list] = {}

        def set_default_timeout(self, _timeout):
            pass

        def set_default_navigation_timeout(self, _timeout):
            pass

        def on(self, event, *handlers):
            self.handlers.setdefault(event, []).extend(handlers)

        def is_closed(self):
            return self.closed

        async def close(self):
            self.closed = True
            for handler in list(self.handlers.get("close", [])):
                handler(self)

    class FakeContext:
        def __init__(self):
            self.pages = []
            self.closed = False

        async def new_page(self):
            if page_error:
                raise page_error
            page = FakePage()
            self.pages.append(page)
            return page

        def on(self, *_args):
            pass

        async def close(self):
            self.closed = True

    browsers = []

    class FakeBrowser:
        version = "123.0"

        def __init__(self):
            self.context = FakeContext()
            self.closed = asyncio.Event()
            self.close_calls = 0

        async def new_context(self, **_options):
            return self.context

        def is_connected(self):
            return not self.closed.is_set()

        async def close(self):
            self.close_calls += 1
            self.closed.set()
            if browser_close_error:
                raise browser_close_error

    class FakePlaywright:
        stop_calls = 0

        async def stop(self):
            self.stop_calls += 1

    playwright = FakePlaywright()

    class FakePlaywrightManager:
        async def start(self):
            return playwright

    async def launch(_playwright, **_options):
        browser = FakeBrowser()
        browsers.append(browser)
        return browser

    monkeypatch.setattr(browser_runtime_module, "launch_chromium", launch)
    runtime = PlaywrightBrowserRuntime(
        session_ttl_seconds=session_ttl_seconds,
        playwright_factory=FakePlaywrightManager,
    )
    return runtime, browsers, playwright


def test_browser_runtime_port_covers_adapter_lifecycle_and_capabilities():
    methods = {
        "create_session",
        "restore_session",
        "get_session",
        "get_page",
        "get_pages",
        "select_page",
        "add_page_listener",
        "remove_page_listener",
        "set_active_page",
        "add_init_script",
        "storage_state",
        "navigate",
        "restrict_navigation",
        "snapshot",
        "collect_controls",
        "collect_evidence",
        "verify_locator",
        "verify_page_locator",
        "execute_action",
        "recover_context",
        "is_timeout_error",
        "close_session",
        "close_all",
    }
    assert all(callable(getattr(BrowserRuntime, name, None)) for name in methods)
    assert all(callable(getattr(PlaywrightBrowserRuntime, name, None)) for name in methods)


@pytest.fixture
def browser_test_url():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.requests.append(self.path)
            if self.path == "/guard":
                body = (
                    f"<html><body><img src='http://localhost:{self.server.server_port}/blocked.png'>"
                    "<img src='/same-host.png'>"
                    f"<script>new WebSocket('ws://localhost:{self.server.server_port}/blocked-ws')</script></body></html>"
                ).encode()
                content_type = "text/html; charset=utf-8"
            elif self.path == "/worker.js":
                body = b"self.addEventListener('fetch', event => event.respondWith(fetch(event.request)));"
                content_type = "application/javascript"
            elif self.path.endswith(".png"):
                body = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1WQAAAAASUVORK5CYII="
                )
                content_type = "image/png"
            else:
                body = (
                    "<html><head><title>Runtime Contract</title></head><body>"
                    "<input type='text' value='secret-account'>"
                    "<input aria-label='Search products' placeholder='Search'>"
                    "<input type='submit' value='Find'>"
                    "<label for='color'>Color</label>"
                    "<select id='color' name='Color'><option value='red'>Red</option><option value='blue' selected>Blue</option></select>"
                    "<label for='sizes'>Sizes</label>"
                    "<select id='sizes' name='Sizes' multiple><option value='small'>Small</option><option value='large'>Large</option></select>"
                    "<input type='checkbox' aria-label='Gift wrap' checked>"
                    "<button onclick=\"document.querySelector('#status').textContent='Completed'\">Continue</button>"
                    "<p id='status'>Ready</p></body></html>"
                ).encode()
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    url = f"http://127.0.0.1:{server.server_port}/"
    BROWSER_REQUEST_LOG[url] = server.requests
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        BROWSER_REQUEST_LOG.pop(url, None)


@pytest.mark.asyncio
async def test_headless_browser_uses_standard_chrome_user_agent():
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session(headless=True)
    try:
        page = await runtime.get_page(session.id)
        user_agent = await page.evaluate("navigator.userAgent")
        assert "HeadlessChrome/" not in user_agent
        assert f"Chrome/{session.browser_version}" in user_agent
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_create_restore_snapshot_verify_action_and_close(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    created = await runtime.create_session(viewport={"width": 1024, "height": 768})
    assert not any(hasattr(created, name) for name in ("browser", "context", "page"))
    try:
        status = await runtime.navigate(created.id, browser_test_url)
        assert status == 200
        snapshot = await runtime.snapshot(created.id)
        assert snapshot.title == "Runtime Contract"
        assert "Ready" in snapshot.text
        assert snapshot.screenshot
        assert any(control["name"] == "Continue" for control in snapshot.controls)
        assert not any(control["name"] == "secret-account" for control in snapshot.controls)
        assert any(control["name"] == "Find" for control in snapshot.controls)
        search = next(control for control in snapshot.controls if control["name"] == "Search products")
        assert search["type"] == "text"
        color = next(control for control in snapshot.controls if control["name"] == "Color")
        assert color["value"] == "blue"
        assert color["role"] == "combobox"
        sizes = next(control for control in snapshot.controls if control["name"] == "Sizes")
        assert sizes["role"] == "listbox"
        sizes_locator = {"kind": "role", "value": "listbox", "name": "Sizes", "exact": True}
        assert (await runtime.verify_locator(created.id, sizes_locator, {"action": "select"}))["verified"] is True
        assert next(control for control in snapshot.controls if control["name"] == "Gift wrap")["checked"] is True

        color_locator = {"kind": "role", "value": "combobox", "name": "Color", "exact": True}
        assert (await runtime.verify_locator(created.id, color_locator, {"action": "select"}))["verified"] is True
        await runtime.execute_action(created.id, color_locator, {"type": "select", "value": "red"})
        assert (
            next(control for control in (await runtime.snapshot(created.id)).controls if control["name"] == "Color")[
                "value"
            ]
            == "red"
        )

        candidate = {"kind": "role", "value": "button", "name": "Continue", "exact": True}
        verification = await runtime.verify_locator(created.id, candidate, {"action": "click"})
        assert verification["verified"] is True
        await runtime.execute_action(created.id, candidate, {"type": "click"})
        after_action = await runtime.collect_evidence(created.id)
        assert "Completed" in after_action.text

        storage_state = await runtime.storage_state(created.id)
        restored = await runtime.restore_session(storage_state, environment={"journey": "golden"})
        assert restored.id != created.id
        assert restored.environment == {"journey": "golden"}
        await runtime.navigate(restored.id, browser_test_url)
        await runtime.close_session(restored.id)
        assert await runtime.get_session(restored.id) is None
    finally:
        await runtime.close_session(created.id)


@pytest.mark.asyncio
async def test_recorder_highlight_is_isolated_and_pick_mode_blocks_business_click(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.add_init_script(session.id, RECORDER_INIT_SCRIPT)
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        button = page.get_by_role("button", name="Continue")
        box = await button.bounding_box()
        assert box
        await page.evaluate("() => window.__qaRecorderSetPickMode(true)")
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await page.wait_for_timeout(60)
        hovered = await page.evaluate("() => window.__qaRecorderHovered")
        overlay = await page.evaluate("""() => {
          const host = document.querySelector('html > div[aria-hidden="true"]');
          const box = host?.shadowRoot?.getElementById('box');
          return { hostExists: !!host, pointerEvents: host && getComputedStyle(host).pointerEvents, display: box && getComputedStyle(box).display };
        }""")
        assert hovered["name"] == "Continue"
        assert overlay == {"hostExists": True, "pointerEvents": "none", "display": "block"}
        await page.evaluate("""() => {
          const button=document.querySelector('button');
          button.addEventListener('pointerdown',()=>document.querySelector('#status').textContent='PointerDown');
          button.addEventListener('pointerup',()=>document.querySelector('#status').textContent='PointerUp');
          button.addEventListener('touchstart',()=>document.querySelector('#status').textContent='TouchStart');
          button.addEventListener('touchend',()=>document.querySelector('#status').textContent='TouchEnd');
          window.addEventListener('pointerdown',()=>document.querySelector('#status').textContent='WindowPointerDown',true);
          button.addEventListener('mousedown',()=>document.querySelector('#status').textContent='MouseDown');
          button.addEventListener('keydown',()=>document.querySelector('#status').textContent='KeyDown');
          window.addEventListener('keydown',()=>document.querySelector('#status').textContent='WindowKeyDown',true);
          window.addEventListener('keyup',()=>document.querySelector('#status').textContent='WindowKeyUp',true);
          button.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
          button.dispatchEvent(new Event('touchstart',{bubbles:true,cancelable:true}));
          button.dispatchEvent(new Event('touchend',{bubbles:true,cancelable:true}));
          button.focus();
        }""")
        assert await page.locator("#status").inner_text() == "Ready"
        await page.keyboard.press("Enter")
        assert await page.locator("#status").inner_text() == "Ready"

        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        assert await page.locator("#status").inner_text() == "Ready"
        picked = await page.evaluate("() => window.__qaRecorderDrain()")
        assert len(picked) == 1 and picked[0]["action"] == "pick"

        duplicate = await page.evaluate("""() => {
          const button = document.createElement('button'); button.textContent = 'Continue'; document.body.append(button);
        }""")
        verification = await runtime.verify_locator(
            session.id,
            {"kind": "role", "value": "button", "name": "Continue", "exact": True},
            {"action": "click"},
        )
        assert duplicate is None
        assert verification["match_count"] == 2
        assert verification["unique"] is False and verification["verified"] is False
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_recorder_captures_fill_select_click_and_redacts_credentials(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.add_init_script(session.id, RECORDER_INIT_SCRIPT)
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        await page.get_by_role("textbox", name="Search products").fill("winter coat")
        await page.wait_for_timeout(450)
        filled = await page.evaluate("() => window.__qaRecorderDrain()")
        assert any(item["action"] == "fill" and item["value"] == "winter coat" for item in filled)

        await page.locator("#color").select_option("red")
        selected = await page.evaluate("() => window.__qaRecorderDrain()")
        assert any(item["action"] == "select" and item["value"] == "red" for item in selected)

        await page.get_by_role("button", name="Continue").click()
        await page.wait_for_timeout(300)
        clicked = await page.evaluate("() => window.__qaRecorderDrain()")
        assert any(item["action"] == "click" and item["name"] == "Continue" for item in clicked)

        await page.evaluate("""() => {
          const password = document.createElement('input'); password.type='password'; password.name='login-password'; password.setAttribute('value','attribute-password-secret'); document.body.append(password);
          const email = document.createElement('input'); email.type='text'; email.name='email'; document.body.append(email);
          const phone = document.createElement('input'); phone.type='text'; phone.name='contact_phone'; document.body.append(phone);
          const firstName = document.createElement('input'); firstName.type='text'; firstName.name='first_name'; document.body.append(firstName);
          const privateSelect = document.createElement('select'); privateSelect.name='account_token'; privateSelect.innerHTML='<option value="private-option-secret">private-option-secret</option>'; document.body.append(privateSelect);
        }""")
        await page.locator('input[name="login-password"]').fill("recorder-secret-value")
        await page.locator('input[name="email"]').fill("person@example.test")
        await page.locator('input[name="contact_phone"]').fill("415-555-0132")
        await page.locator('input[name="first_name"]').fill("Ada Lovelace")
        await page.locator('select[name="account_token"]').select_option("private-option-secret")
        await page.wait_for_timeout(450)
        private_events = await page.evaluate("() => window.__qaRecorderDrain()")
        private_fills = [item for item in private_events if item["action"] == "fill"]
        assert len(private_fills) == 4
        assert all(item["value"] is None and item["value_redacted"] for item in private_fills), private_fills
        leaked = [
            secret
            for secret in (
                "recorder-secret-value",
                "attribute-password-secret",
                "person@example.test",
                "415-555-0132",
                "Ada Lovelace",
                "private-option-secret",
            )
            if secret in str(private_events)
        ]
        assert not leaked
        safe_url = await page.evaluate("""() => {
          history.pushState({}, '', '?customer=Alice&access_token=private');
          return window.__qaRecorderDrain().at(-1).url;
        }""")
        assert safe_url == browser_test_url

        private_locator = await page.evaluate("""() => {
          const button=document.createElement('button'); button.textContent='Open profile';
          button.id='person@example.test'; button.setAttribute('data-testid','415-555-0132');
          document.body.append(button); window.__qaRecorderSetPickMode(true);
          button.dispatchEvent(new MouseEvent('click',{bubbles:true,composed:true}));
          return window.__qaRecorderDrain()[0];
        }""")
        assert "person@example.test" not in str(private_locator)
        assert "415-555-0132" not in str(private_locator)
        assert not any(item.get("kind") == "test_id" for item in private_locator["candidates"])
    finally:
        await runtime.close_session(session.id)


def test_generated_recorder_script_executes_in_real_browser(browser_test_url):
    request = RecorderGenerateRequest(
        steps=[
            RecorderStep(action="navigate", url=browser_test_url),
            RecorderStep(action="click", locator=RecorderLocator(kind="role", value="button", name="Continue")),
            RecorderStep(
                action="assert_text",
                locator=RecorderLocator(kind="id", value="status"),
                value="Completed",
            ),
        ]
    )
    source = generate_python_case(request)
    namespace = {}
    exec(compile(source, "test_generated_recorder.py", "exec"), namespace)
    namespace["test_recorded_case"]()


@pytest.mark.asyncio
async def test_recorder_captures_open_shadow_target(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.add_init_script(session.id, RECORDER_INIT_SCRIPT)
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        await page.evaluate("""() => {
          const host = document.createElement('qa-widget');
          const root = host.attachShadow({mode:'open'});
          root.innerHTML = '<button aria-label="Shadow action">Run</button>';
          document.body.append(host);
        }""")
        button = page.get_by_role("button", name="Shadow action")
        box = await button.bounding_box()
        assert box
        await page.evaluate("() => window.__qaRecorderSetPickMode(true)")
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        picked = await page.evaluate("() => window.__qaRecorderDrain()")
        assert picked[0]["name"] == "Shadow action"
        assert picked[0]["shadow_path"] == ["qa-widget"]
        verification = await runtime.verify_locator(
            session.id,
            {"kind": "role", "value": "button", "name": "Shadow action", "exact": True},
            {"action": "click"},
        )
        assert verification["verified"] is True
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_restricts_top_level_navigation_to_allowed_hosts(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.restrict_navigation(session.id, {"127.0.0.1"})
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        port = urlsplit(browser_test_url).port
        await page.evaluate("url => { window.location.assign(url); }", f"http://localhost:{port}/blocked")
        await page.wait_for_timeout(250)
        snapshot = await runtime.snapshot(session.id, include_screenshot=False)
        assert urlsplit(snapshot.url).hostname != "localhost"
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_restricts_subresource_requests_to_allowed_hosts(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.restrict_navigation(session.id, {"127.0.0.1"})
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        guard_url = browser_test_url.rstrip("/") + "/guard"
        await runtime.navigate(session.id, guard_url)
        await page.wait_for_load_state("networkidle")
        # The local fixture server is bound only to 127.0.0.1; the disallowed
        # localhost host alias is blocked before it can reach the handler.
        assert "/same-host.png" in BROWSER_REQUEST_LOG[browser_test_url]
        assert "/blocked.png" not in BROWSER_REQUEST_LOG[browser_test_url]
        assert "/blocked-ws" not in BROWSER_REQUEST_LOG[browser_test_url]
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_can_block_service_workers_for_discovery(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session(block_service_workers=True)
    try:
        await runtime.navigate(session.id, browser_test_url)
        page = await runtime.get_page(session.id)
        await page.evaluate("navigator.serviceWorker.register('/worker.js').catch(() => null)")
        await page.wait_for_timeout(250)
        registrations = await page.evaluate("navigator.serviceWorker.getRegistrations().then(items => items.length)")
        assert registrations == 0
        assert runtime._resources[session.id].context.service_workers == []
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_rejects_invalid_and_expired_sessions(browser_test_url):
    runtime = PlaywrightBrowserRuntime(session_ttl_seconds=60)
    with pytest.raises(ValueError, match=r"http\(s\)"):
        await runtime.navigate("missing", "file:///tmp/private")

    session = await runtime.create_session()
    with pytest.raises(ValueError, match="invalid, expired or unavailable"):
        await runtime.navigate("missing", browser_test_url)
    session.last_activity_monotonic -= 61
    assert await runtime.get_session(session.id) is None
    assert session.status == "EXPIRED"


@pytest.mark.asyncio
async def test_browser_runtime_recovers_context_and_reports_browser_crash(browser_test_url):
    runtime = PlaywrightBrowserRuntime()
    session = await runtime.create_session()
    try:
        await runtime.navigate(session.id, browser_test_url)
        recovered = await runtime.recover_context(session.id)
        assert recovered is session
        assert session.status == "READY"
        assert session.current_url == browser_test_url
        assert (await runtime.snapshot(session.id, include_screenshot=False)).title == "Runtime Contract"

        await runtime._resources[session.id].browser.close()
        assert await runtime.get_session(session.id) is None
        assert session.status == "CRASHED"
    finally:
        await runtime.close_session(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_expires_idle_session_without_another_request(monkeypatch):
    runtime, browsers, playwright = _fake_browser_runtime(monkeypatch, session_ttl_seconds=0.03)
    session = await runtime.create_session()

    await asyncio.wait_for(browsers[0].closed.wait(), timeout=1)

    assert session.status == "EXPIRED"
    assert session.id not in runtime._sessions
    assert browsers[0].context.closed
    assert playwright.stop_calls == 1


@pytest.mark.asyncio
async def test_browser_runtime_adopts_a_surviving_tab_when_the_active_page_closes(monkeypatch):
    runtime, browsers, _playwright = _fake_browser_runtime(monkeypatch)
    session = await runtime.create_session()
    first_page = await runtime.get_page(session.id)
    popup = await browsers[0].context.new_page()
    runtime.set_active_page(session.id, popup)

    await popup.close()

    assert session.status == "READY"
    assert await runtime.get_page(session.id) is first_page
    assert await runtime.get_session(session.id) is session


@pytest.mark.asyncio
async def test_browser_runtime_retires_a_session_whose_last_tab_closed(monkeypatch):
    runtime, browsers, _playwright = _fake_browser_runtime(monkeypatch)
    session = await runtime.create_session()

    await browsers[0].context.pages[0].close()

    assert await runtime.get_session(session.id) is None
    assert session.status == "CRASHED"
    with pytest.raises(ValueError, match="invalid, expired or unavailable"):
        await runtime.get_page(session.id)


@pytest.mark.asyncio
async def test_browser_runtime_close_all_releases_every_session(monkeypatch):
    runtime, browsers, playwright = _fake_browser_runtime(monkeypatch)
    sessions = [await runtime.create_session(), await runtime.create_session()]

    await runtime.close_all()

    assert [session.status for session in sessions] == ["CLOSED", "CLOSED"]
    assert not runtime._sessions
    assert all(browser.context.closed and browser.close_calls == 1 for browser in browsers)
    assert playwright.stop_calls == 1


@pytest.mark.asyncio
async def test_browser_runtime_setup_failure_preserves_error_and_attempts_all_cleanup(monkeypatch):
    runtime, browsers, playwright = _fake_browser_runtime(
        monkeypatch,
        page_error=RuntimeError("page setup failed"),
        browser_close_error=RuntimeError("browser close failed"),
    )

    with pytest.raises(RuntimeError, match="page setup failed") as failure:
        await runtime.create_session()

    assert browsers[0].close_calls == 1
    assert playwright.stop_calls == 1
    assert any("Browser cleanup failed" in note for note in failure.value.__notes__)
