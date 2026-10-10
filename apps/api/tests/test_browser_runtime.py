from __future__ import annotations

import asyncio
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

import pytest
from app.adapters.playwright.browser_runtime import PlaywrightBrowserRuntime
from app.ports.browser_runtime import BrowserRuntime

BROWSER_REQUEST_LOG = {}


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
                body = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1WQAAAAASUVORK5CYII=")
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
        assert next(control for control in (await runtime.snapshot(created.id)).controls if control["name"] == "Color")[
            "value"
        ] == "red"

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
    runtime = PlaywrightBrowserRuntime(session_ttl_seconds=0.01)
    with pytest.raises(ValueError, match=r"http\(s\)"):
        await runtime.navigate("missing", "file:///tmp/private")

    session = await runtime.create_session()
    with pytest.raises(ValueError, match="invalid, expired or unavailable"):
        await runtime.navigate("missing", browser_test_url)
    await asyncio.sleep(0.03)
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
