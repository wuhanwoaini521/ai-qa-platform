from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from app.adapters.playwright.browser_runtime import PlaywrightBrowserRuntime
from app.ports.browser_runtime import BrowserRuntime


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
            body = (
                "<html><head><title>Runtime Contract</title></head><body>"
                "<button onclick=\"document.querySelector('#status').textContent='Completed'\">Continue</button>"
                "<p id='status'>Ready</p></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


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
