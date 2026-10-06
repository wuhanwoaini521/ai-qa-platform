from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from qa_core.execution.live_browser_plugin import LIVE_BROWSER_PLUGIN_NAME, LIVE_BROWSER_PLUGIN_SOURCE
from qa_core.execution.pytest_runner import PytestRunner


def _write_test_browser_support(tmp_path: Path) -> None:
    (tmp_path / "browser_support.py").write_text(
        "def launch_test_browser(playwright):\n"
        "    try:\n"
        "        return playwright.chromium.launch()\n"
        "    except Exception as error:\n"
        "        message = str(error).lower()\n"
        "        if not any(marker in message for marker in ('spawn eperm', 'winerror 5', 'permission denied', 'access is denied', \"executable doesn't exist\")):\n"
        "            raise\n"
        "        for channel in ('msedge', 'chrome'):\n"
        "            try:\n"
        "                return playwright.chromium.launch(channel=channel)\n"
        "            except Exception:\n"
        "                pass\n"
        "        raise error\n",
        encoding="utf-8",
    )


def test_generated_live_browser_plugin_source_compiles():
    compile(LIVE_BROWSER_PLUGIN_SOURCE, "qa_platform_live_browser_plugin.py", "exec")


@pytest.mark.asyncio
async def test_short_navigation_captures_actual_page_before_browser_close(tmp_path):
    class Website(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Product catalog</h1><button>View product</button>")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Website)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    _write_test_browser_support(tmp_path)
    (tmp_path / f"{LIVE_BROWSER_PLUGIN_NAME}.py").write_text(LIVE_BROWSER_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "test_short.py").write_text(
        "import os\nfrom playwright.sync_api import sync_playwright\nfrom browser_support import launch_test_browser\n"
        "def test_navigate_and_close():\n"
        "    with sync_playwright() as p:\n"
        "        browser = launch_test_browser(p)\n"
        "        page = browser.new_page()\n"
        "        page.goto(os.environ['WEBSITE_URL'])\n"
        "        assert page.get_by_role('heading').inner_text() == 'Product catalog'\n"
        "        for index in range(105):\n"
        "            with page.expect_request_finished():\n"
        "                assert page.evaluate(\"async index => {const response=await fetch('/?entry='+index);await response.text();return response.status;}\", index) == 200\n"
        "        browser.close()\n",
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    telemetry = tmp_path / "live"
    events = []

    async def observe(event):
        events.append(event)

    try:
        result = await PytestRunner().run_suite(
            tmp_path,
            nodeids=["test_short.py"],
            environment={
                "PYTHONPATH": str(tmp_path),
                "QA_PLATFORM_LIVE_BROWSER_LOG": str(telemetry),
                "QA_ARTIFACT_DIR": str(artifacts),
                "WEBSITE_URL": url,
            },
            browser_event_path=telemetry,
            on_browser_event=observe,
            extra_pytest_args=["-p", LIVE_BROWSER_PLUGIN_NAME],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert result.exit_code == 0, "\n".join(result.raw_logs)
    from datetime import datetime

    assert all(datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0 for event in events)
    finished = next(event for event in events if event["type"] == "session.finished")
    assert finished["page_evidence"]["url"] == url
    assert len(finished["page_evidence"]["network_logs"]) == 100
    assert all(entry.get("timestamp") for entry in finished["page_evidence"]["network_logs"])
    assert any(event["type"] == "frame" and event.get("url") == url and event.get("frame") for event in events)
    snapshot = artifacts / f"browser-{finished['session_id']}-last.jpg"
    assert snapshot.read_bytes().startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_real_browser_created_inside_test_and_fixture_both_emit_frames_and_evidence(tmp_path):
    _write_test_browser_support(tmp_path)
    (tmp_path / f"{LIVE_BROWSER_PLUGIN_NAME}.py").write_text(LIVE_BROWSER_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import pytest\nfrom playwright.sync_api import sync_playwright\nfrom browser_support import launch_test_browser\n"
        "@pytest.fixture\ndef page():\n    with sync_playwright() as p:\n        browser = launch_test_browser(p)\n        yield browser.new_page()\n        browser.close()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_browser.py").write_text(
        """from playwright.sync_api import sync_playwright
from browser_support import launch_test_browser
HTML = '<button>Help</button><p id="result"></p>'
def exercise(page):
    page.set_content(HTML)
    page.evaluate("document.querySelector('button').onclick=()=>{console.info(123);document.querySelector('#result').textContent='ready'}")
    page.get_by_role("button", name="Help").click()
    page.wait_for_timeout(250)
    assert page.locator("#result").inner_text() == "ready"
def test_inline_browser():
    with sync_playwright() as p:
        browser = launch_test_browser(p)
        exercise(browser.new_page())
        browser.close()
def test_fixture_browser(page):
    exercise(page)
""",
        encoding="utf-8",
    )
    events = []

    async def observe(event):
        events.append(event)

    telemetry = tmp_path / "live"
    result = await PytestRunner().run_suite(
        tmp_path,
        nodeids=["test_browser.py"],
        environment={"PYTHONPATH": str(tmp_path), "QA_PLATFORM_LIVE_BROWSER_LOG": str(telemetry)},
        browser_event_path=telemetry,
        on_browser_event=observe,
        extra_pytest_args=["-p", LIVE_BROWSER_PLUGIN_NAME],
    )
    assert result.exit_code == 0, "\n".join(result.raw_logs)
    finished = [event for event in events if event["type"] == "session.finished"]
    assert len(finished) == 2
    for event in finished:
        evidence = event["page_evidence"]
        assert evidence["recent_steps"][0]["status"] == "PASSED"
        assert evidence["recent_steps"][0]["file"] == "test_browser.py"
        assert evidence["recent_steps"][0]["line"] > 0
        assert evidence["console_logs"][0]["text"] == "123"
        assert evidence["controls"][0]["name"] == "Help"
        assert any(
            frame["type"] == "frame" and frame.get("frame") and frame["nodeid"] == event["nodeid"] for frame in events
        )


@pytest.mark.asyncio
async def test_network_body_is_bounded_redacted_and_has_real_duration(tmp_path):
    import json

    class Website(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(
                {
                    "product": "Everyday Tee",
                    "price": 29,
                    "password": "fixture-secret",
                    "profile": {"email": "synthetic@example.invalid"},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Website)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _write_test_browser_support(tmp_path)
    (tmp_path / f"{LIVE_BROWSER_PLUGIN_NAME}.py").write_text(LIVE_BROWSER_PLUGIN_SOURCE, encoding="utf-8")
    (tmp_path / "test_network.py").write_text(
        "from playwright.sync_api import sync_playwright\n"
        "from browser_support import launch_test_browser\n"
        "import os\n"
        "def test_json():\n"
        "    with sync_playwright() as p:\n"
        "        browser=launch_test_browser(p)\n"
        "        page=browser.new_page()\n"
        "        page.goto(os.environ['WEBSITE_URL'])\n"
        "        assert page.locator('body').inner_text().find('Everyday Tee') >= 0\n"
        "        browser.close()\n",
        encoding="utf-8",
    )
    events = []

    async def observe(event):
        events.append(event)

    try:
        result = await PytestRunner().run_suite(
            tmp_path,
            nodeids=["test_network.py"],
            environment={
                "PYTHONPATH": str(tmp_path),
                "QA_PLATFORM_LIVE_BROWSER_LOG": str(tmp_path / "live"),
                "WEBSITE_URL": f"http://127.0.0.1:{server.server_port}/",
            },
            browser_event_path=tmp_path / "live",
            on_browser_event=observe,
            extra_pytest_args=["-p", LIVE_BROWSER_PLUGIN_NAME],
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert result.exit_code == 0, "\n".join(result.raw_logs)
    entries = [event["entry"] for event in events if event["type"] == "network"]
    response = next(entry for entry in entries if entry.get("status") == 200)
    assert response["duration_ms"] >= 0 and response["method"] == "GET"
    assert response["response"]["body"]["product"] == "Everyday Tee"
    assert response["response"]["body"]["password"] == "[REDACTED]"
    assert response["response"]["body"]["profile"]["email"] == "[REDACTED]"
    assert "fixture-secret" not in json.dumps(entries)


@pytest.mark.asyncio
async def test_runner_tails_live_browser_events_from_a_test_worker(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")
    (tmp_path / "qa_live_test_plugin.py").write_text(
        "import json, os\n"
        "def pytest_runtest_setup(item):\n"
        "    path = os.environ['QA_PLATFORM_LIVE_BROWSER_LOG'] + '.main'\n"
        "    with open(path, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps({'type': 'session.started', 'worker_id': 'main', 'nodeid': item.nodeid}) + '\\n')\n"
        "        handle.flush()\n",
        encoding="utf-8",
    )
    telemetry_path = tmp_path / "live-events"
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    result = await PytestRunner().run_suite(
        tmp_path,
        nodeids=["tests/test_sample.py::test_sample"],
        environment={"PYTHONPATH": str(tmp_path), "QA_PLATFORM_LIVE_BROWSER_LOG": str(telemetry_path)},
        browser_event_path=telemetry_path,
        on_browser_event=on_event,
        extra_pytest_args=["-p", "qa_live_test_plugin"],
    )

    assert result.exit_code == 0, "\n".join(result.raw_logs)
    assert any(event.get("type") == "session.started" and event.get("worker_id") == "main" for event in events)


@pytest.mark.asyncio
async def test_runner_parses_pytest_xdist_worker_results(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_parallel.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('case', ['a', 'b', 'c'])\n"
        "def test_case(case):\n"
        "    assert case in {'a', 'b', 'c'}\n",
        encoding="utf-8",
    )

    result = await PytestRunner().run_suite(
        tmp_path,
        nodeids=["tests/test_parallel.py::test_case"],
        environment={"TMP": str(tmp_path), "TEMP": str(tmp_path)},
        parallel_workers=3,
    )

    assert result.exit_code == 0, "\n".join(result.raw_logs)
    assert result.total == 3
    assert result.passed == 3
    assert {item.nodeid for item in result.results} == {
        "tests/test_parallel.py::test_case[a]",
        "tests/test_parallel.py::test_case[b]",
        "tests/test_parallel.py::test_case[c]",
    }
