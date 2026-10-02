"""Real local shop, browser and evidence. No internet or shared cart state required."""

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def shop_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(Path(__file__).parent / "site")))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.fixture
def shop_data():
    return json.loads((Path(__file__).parent / "data" / "shop.json").read_text(encoding="utf-8"))


@pytest.fixture
def page(request):
    with sync_playwright() as engine:
        browser = engine.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(3000)
        page.set_default_navigation_timeout(15000)
        yield page
        artifacts = Path(
            os.environ.get("QA_ARTIFACT_DIR", str(Path(__file__).parents[2] / "runtime" / "artifacts" / "demo-shop"))
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        name = request.node.name
        page.screenshot(path=str(artifacts / f"{name}.png"), full_page=True)
        (artifacts / f"{name}.html").write_text(page.content(), encoding="utf-8")
        context.tracing.stop(path=str(artifacts / f"{name}.zip"))
        context.close()
        browser.close()
