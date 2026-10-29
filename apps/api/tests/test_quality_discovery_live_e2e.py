"""Real-browser acceptance for the live Quality Discovery stream.

The browser is the real Chromium runtime launching the real page served by the test; the site places
its controls at known absolute coordinates so the geometry that reaches the live view can be compared
with the page, not merely checked for "not null". AI planning and the Jev decision are fixtures
(no model is costed twice here) — everything a viewer *sees* (frames, URLs, element inventory,
highlights) comes from the real browser.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from app.adapters.playwright.browser_runtime import PlaywrightBrowserRuntime
from app.container import get_quality_discovery_service
from app.main import app
from app.services.decision_service import DecisionService
from app.services.quality_discovery_service import QualityDiscoveryService
from app.services.workspace_service import WorkspaceService
from app.settings import settings
from project_model.models import DecisionResult
from test_quality_discovery import DiscoveryFixtureAI

#: Control positions in the served page, in CSS pixels from the top-left of the viewport.
LAYOUT = {
    "Search": {"x": 120, "y": 60, "width": 200, "height": 28},
    "Products": {"x": 120, "y": 120, "width": 150, "height": 24},
}
GEOMETRY_TOLERANCE = 8

PAGES = {
    "home": (
        "<main><h1>QA Shop</h1>"
        "<a href='/search' style='position:absolute;left:120px;top:120px;width:150px;height:24px'>Products</a>"
        "</main>"
    ),
    "search": (
        "<main><h1>Search products</h1>"
        "<form action='/search'>"
        "<input id='q' name='q' type='search' role='textbox' aria-label='Search' placeholder='Search' "
        "style='position:absolute;left:120px;top:60px;width:200px;height:28px'>"
        "<button type='submit' style='position:absolute;left:340px;top:60px;width:90px;height:28px'>Search</button>"
        "</form></main>"
    ),
    "results": "<main><h1>Search results</h1><p>Canvas tote</p></main>",
}


class _Site(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query).get("q", [""])[0]
        if parsed.path in {"/", "/index.html"}:
            body = PAGES["home"]
        elif parsed.path == "/search" and query:
            body = PAGES["results"]
        else:
            body = PAGES["search"]
        payload = (
            "<!doctype html><html><head><title>QA Shop</title>"
            "<style>html,body{margin:0;padding:0}*{box-sizing:border-box}</style></head>"
            f"<body>{body}</body></html>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


@pytest.fixture
def live_discovery_site():
    site = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    thread = threading.Thread(target=site.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{site.server_port}/"
    finally:
        site.shutdown()
        site.server_close()
        thread.join(timeout=2)


@pytest_asyncio.fixture
async def discovery_runtime_cleanup(client):
    tracked = []
    yield tracked

    current = asyncio.current_task()
    for service, project_id, runtime in tracked:
        runs = await service.list(project_id, limit=100)
        run_ids = [run.id for run in runs]
        for run in runs:
            if run.status not in service.TERMINAL:
                await service.stop(run.id)

        executors = [service._tasks[run_id] for run_id in run_ids if run_id in service._tasks]
        pending_executors = set()
        if executors:
            _, pending_executors = await asyncio.wait(executors, timeout=3)
        for task in pending_executors:
            task.cancel()

        # Runtime shutdown owns cancellation of stalled close tasks and stops its Playwright driver.
        await asyncio.wait_for(runtime.close_all(), timeout=30)
        if executors:
            _, pending_executors = await asyncio.wait(executors, timeout=3)
        if pending_executors:
            await asyncio.wait_for(runtime.close_all(), timeout=30)
            _, pending_executors = await asyncio.wait(pending_executors, timeout=3)
        assert not pending_executors, [task.get_name() for task in pending_executors]

        finalizers = list(service._finalization_tasks)
        if finalizers:
            _, pending_finalizers = await asyncio.wait(finalizers, timeout=5)
            for task in pending_finalizers:
                task.cancel()
            if pending_finalizers:
                await asyncio.gather(*pending_finalizers, return_exceptions=True)

        await asyncio.sleep(0)
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done() and task.get_name().startswith("quality-discovery")
        ]
        assert not pending, [task.get_name() for task in pending]
        assert not runtime._sessions and not runtime._resources
        assert runtime._expiry_task is None
        assert runtime._playwright is None
        assert runtime._playwright_stop_task is None
        assert not runtime._closing_tasks
        assert not runtime._closing_all
        assert all(run.status in service.TERMINAL for run in await service.list(project_id, limit=100))


def _control(elements: list[dict], name: str) -> dict:
    match = next((item for item in elements if item.get("name") == name), None)
    assert match is not None, f"no control named {name!r} in the live inventory: {elements}"
    return match


def _assert_geometry(element: dict, expected: dict) -> None:
    box = element.get("bounding_box")
    assert isinstance(box, dict), f"{element.get('name')!r} reached the live view without geometry: {element}"
    for key in ("x", "y", "width", "height"):
        assert abs(float(box[key]) - expected[key]) <= GEOMETRY_TOLERANCE, (
            f"{element['name']!r} reported {key}={box[key]}, the page puts it at {expected[key]}"
        )


async def _read_stream(client, run_id: str, *, budget_seconds: float, ready) -> tuple[list[dict], bool]:
    """Collect SSE frames until ``ready(frames)`` holds. Returns the frames and whether we stopped early."""
    frames: list[dict] = []
    stopped_early = False

    async def _consume() -> None:
        async with client.stream("GET", f"/api/discovery/runs/{run_id}/stream") as response:
            assert response.status_code == 200, response.status_code
            event_type: str | None = None
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    frames.append({"event": event_type or payload.get("type"), "data": payload})
                    if ready(frames):
                        return

    try:
        await asyncio.wait_for(_consume(), timeout=budget_seconds)
    except (asyncio.TimeoutError, TimeoutError):
        stopped_early = True
    return frames, stopped_early


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.e2e
async def test_live_discovery_stream_carries_real_frames_geometry_and_highlights(
    client, test_db_session, tmp_path, monkeypatch, live_discovery_site, discovery_runtime_cleanup
):
    pytest.importorskip("playwright")
    target = live_discovery_site
    workspace_dir = tmp_path / "workspaces"
    workspace_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "workspace_storage_dir", workspace_dir)
    monkeypatch.setattr(settings, "artifact_storage_dir", tmp_path / "artifacts")

    ai = DiscoveryFixtureAI()
    decisions: list[str] = []

    async def choose_candidate(_service, request, **_kwargs):
        candidates = request.state["candidates"]
        if not decisions:
            matches = [item for item in candidates if item["target"] == "Products"]
        else:
            matches = [
                item
                for item in candidates
                if item["target_role"] in {"textbox", "button"} and item["target"] not in decisions
            ]
        assert matches, f"expected a safe observed action after {decisions}, got {candidates}"
        chosen = matches[0]
        decisions.append(chosen["target"])
        return DecisionResult(
            choice=chosen["key"],
            provider="jev-controlled-fixture",
            model="local-acceptance",
            confidence=0.99,
            probabilities={chosen["key"]: 0.99},
            reason="Choose a read-only navigation/search action from observed controls.",
        )

    monkeypatch.setattr(DecisionService, "choose", choose_candidate)
    monkeypatch.setattr(DecisionService, "ask_score", lambda *_args, **_kwargs: None)

    runtime = PlaywrightBrowserRuntime()
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime,
        decisions=DecisionService(),
        provider_factory=lambda: ai,
        workspace_service=WorkspaceService(base_dir=workspace_dir),
    )
    monkeypatch.setattr(service, "_assert_real_ai_available", lambda: None)
    monkeypatch.setitem(app.dependency_overrides, get_quality_discovery_service, lambda: service)

    # Record what the real adapter produced, so the streamed frames can be tied back to it.
    captured: list[bytes] = []
    painted: list[int] = []
    real_capture = runtime.capture_frame
    real_paint = runtime.paint_highlights

    async def capture_frame(session_id: str, **kwargs):
        data = await real_capture(session_id, **kwargs)
        if data:
            captured.append(data)
        return data

    async def paint_highlights(session_id: str, boxes):
        drawn = await real_paint(session_id, boxes)
        painted.append(drawn)
        return drawn

    monkeypatch.setattr(runtime, "capture_frame", capture_frame)
    monkeypatch.setattr(runtime, "paint_highlights", paint_highlights)

    project = await client.post("/api/projects", json={"name": "Live discovery acceptance"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    discovery_runtime_cleanup.append((service, project_id, runtime))
    created = await client.post(
        "/api/discovery/runs",
        json={"project_id": project_id, "start_url": target, "mode": "EXPLORE"},
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]

    def ready(frames: list[dict]) -> bool:
        kinds = [frame["event"] for frame in frames]
        return "run.finished" in kinds or ("browser.frame" in kinds and kinds.count("element.inventory") >= 2)

    frames, _stopped_early = await _read_stream(client, run_id, budget_seconds=90, ready=ready)
    kinds = [frame["event"] for frame in frames]
    assert kinds and kinds[0] == "snapshot", f"the stream must open with the run snapshot, got {kinds[:5]}"
    assert "browser.frame" in kinds, f"no live frame reached the viewer: {kinds}"
    assert "element.inventory" in kinds, f"no element inventory reached the viewer: {kinds}"

    # Settle the run before anything else: an exploration task must never outlive the test fixture.
    run = (await client.get(f"/api/discovery/runs/{run_id}")).json()
    if run["status"] in {"QUEUED", "RUNNING"}:
        assert (await client.post(f"/api/discovery/runs/{run_id}/stop")).status_code == 202
    for _ in range(150):
        run = (await client.get(f"/api/discovery/runs/{run_id}")).json()
        if run["status"] not in {"QUEUED", "RUNNING"}:
            break
        await asyncio.sleep(0.2)

    # 1. Frames are the real browser's screenshots, not a placeholder.
    streamed = [
        base64.b64decode(frame["data"]["metadata"]["frame"]) for frame in frames if frame["event"] == "browser.frame"
    ]
    assert streamed, "the frame events carried no payload"
    assert all(data.startswith(b"\xff\xd8") for data in streamed), "streamed frames are not JPEG data"
    assert max(len(data) for data in streamed) > 2_000, "streamed frames are too small to be a real screenshot"
    assert captured, "the adapter never captured a frame"
    assert any(data in captured for data in streamed), "streamed frames do not match what the adapter captured"

    frame_meta = next(frame["data"]["metadata"] for frame in frames if frame["event"] == "browser.frame")
    assert frame_meta["url"].startswith(target), f"the frame was captured on {frame_meta['url']}"
    assert frame_meta["mime_type"] == "image/jpeg"
    viewport = frame_meta["viewport"]
    assert viewport["width"] > 0 and viewport["height"] > 0, viewport

    # 2. Element geometry is measured from the real DOM, not guessed or defaulted.
    inventories = [frame["data"]["metadata"] for frame in frames if frame["event"] == "element.inventory"]
    elements = [element for inventory in inventories for element in inventory["elements"]]
    assert elements, "the live view never received an element inventory"
    search = _control(elements, "Search")
    assert search["bounding_box"] is not None and search["role"] == "textbox"
    _assert_geometry(search, LAYOUT["Search"])
    products = _control(elements, "Products")
    _assert_geometry(products, LAYOUT["Products"])
    assert any(element.get("locator") for element in elements), "no element reached the view with a locator"

    # 3. A frame carrying an in-page highlight proves the overlay was painted on the real page.
    assert painted and max(painted) > 0, "the discovery highlight was never painted onto the real page"

    # 4. The run produced its own evidence (states, actions, screenshots), not a placeholder.
    assert run["status"] in {"COMPLETED", "STOPPED"}, {key: run.get(key) for key in ("status", "error", "progress")}
    assert run["result"]["states"], "the run recorded no observed state"
    assert run["result"]["states"][0]["screenshot_evidence_id"], "the state has no screenshot evidence"
    assert decisions, "the controlled decision policy never ran"

    # 5. Nothing was invented when the AI fixture was in use: every decision is attributed.
    assert all(item["provider"] == "jev-controlled-fixture" for item in run["result"]["decisions"])
    assert "ai.unavailable" not in kinds, "the fixture AI reported an outage"
