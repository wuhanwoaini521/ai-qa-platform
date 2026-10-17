"""Live Quality Discovery: event contract, frame pump, stream authentication and AI degradation.

The live view is a fan-out over the run's own persisted events, so these tests pin four things: the
contract shape, the fact that a slow or absent viewer can never disturb a run, the fact that the
stream endpoint is reachable only through the same project ACL and short-lived ticket as every other
stream in the app, and the fact that an AI outage degrades exploration instead of failing it.

Every test here is offline: the browser runtime is a fixture, and the decision step uses an offline
stand-in for Jev, so neither an unreachable AI provider nor an unreachable Jev can make these tests
flaky. Real provider behaviour is exercised by the E2E suite, not here.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from types import SimpleNamespace

import pytest
from app.api.authz import is_stream_route, stream_ticket_scope
from app.container import get_quality_discovery_service
from app.main import app as fastapi_app
from app.services import quality_discovery_service as discovery_module
from app.services.quality_discovery_live import DISCOVERY_EVENT_TYPES, DiscoveryLiveHub, event_payload
from app.services.quality_discovery_service import DiscoveryStatus, QualityDiscoveryService
from conftest import bearer_client, login_token
from project_model.models import DecisionResult
from qa_core.ai.provider import AIProviderError
from test_quality_discovery import DiscoveryFixtureAI, DiscoveryFixtureBrowserRuntime

pytestmark = pytest.mark.integration

PASSWORD = "pw-123456"
#: Bounds the SSE reads below: a live run is never awaited to completion here.
STREAM_LIMIT = 400


class _OfflineDecisions:
    """Offline stand-in for Jev: the service's own candidate order decides."""

    async def choose(self, request, **_kwargs) -> DecisionResult:
        return DecisionResult(
            choice=request.options[0].key,
            confidence=0.95,
            minimum_confidence=0.60,
            provider="test",
            model="offline",
            usage={},
        )


class _FramingRuntime(DiscoveryFixtureBrowserRuntime):
    """Fixture runtime plus the viewport frame and control geometry the live stream needs."""

    def __init__(self) -> None:
        super().__init__()
        self.frames_served = 0

    async def snapshot(self, session_id: str, **kwargs):
        snapshot = await super().snapshot(session_id, **kwargs)
        for index, control in enumerate(snapshot.controls):
            control.setdefault("bounding_box", {"x": 8, "y": 8 + index * 24, "width": 120, "height": 20})
            control.setdefault("in_viewport", True)
        return snapshot

    async def capture_frame(self, session_id: str, **_kwargs) -> bytes:
        self.frames_served += 1
        return b"\xff\xd8\xff\xe0frame"


class _UnavailableAI:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *_args, **_kwargs):
        self.calls += 1
        raise AIProviderError("timeout", "AI Provider 在 20 秒内未返回任何结果。")


@contextlib.asynccontextmanager
async def _live_service(test_db_session, *, runtime=None, provider_factory=None):
    """Serve discovery from fixtures so stream tests never touch the network."""
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=runtime or DiscoveryFixtureBrowserRuntime(),
        provider_factory=provider_factory or (lambda: DiscoveryFixtureAI()),
        decisions=_OfflineDecisions(),
    )
    fastapi_app.dependency_overrides[get_quality_discovery_service] = lambda: service
    try:
        yield service
    finally:
        fastapi_app.dependency_overrides.pop(get_quality_discovery_service, None)


async def _started_run(client, name: str, **extra) -> str:
    project = await client.post("/api/projects", json={"name": name})
    assert project.status_code == 201, project.text
    created = await client.post(
        "/api/discovery/runs",
        json={
            "project_id": project.json()["id"],
            "start_url": "http://shop.example.test/",
            "mode": "EXPLORE",
            **extra,
        },
    )
    assert created.status_code == 202, created.text
    return created.json()["id"]


async def _await_terminal(client, run_id: str, iterations: int = 1200) -> dict:
    body: dict = {}
    for _ in range(iterations):
        body = (await client.get(f"/api/discovery/runs/{run_id}")).json()
        if body["status"] in QualityDiscoveryService.TERMINAL:
            return body
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} never reached a terminal status; last={body}")


async def _read_frames(
    client, run_id: str, *, until, limit: int = STREAM_LIMIT, headers: dict | None = None
) -> list[dict]:
    """Read SSE frames until ``until(frames)`` holds, then detach."""
    frames: list[dict] = []
    async with client.stream("GET", f"/api/discovery/runs/{run_id}/stream", headers=headers) as response:
        if response.status_code != 200:
            detail = (await response.aread())[:400]
            raise AssertionError(f"stream returned {response.status_code}: {detail!r}")
        assert response.headers["content-type"].startswith("text/event-stream")
        event_name = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: ") and event_name:
                frames.append({"event": event_name, "data": json.loads(line.removeprefix("data: "))})
                if until(frames) or len(frames) >= limit:
                    return frames
    return frames


def test_live_event_contract_is_stable():
    payload = event_payload("page.state", seq=7, message="已观察", metadata={"state_id": "s1"})
    assert set(payload) == {"type", "seq", "message", "metadata", "at"}
    assert payload["type"] == "page.state" and payload["seq"] == 7
    assert "browser.frame" in DISCOVERY_EVENT_TYPES and "element.inventory" in DISCOVERY_EVENT_TYPES
    assert "run.finished" in DISCOVERY_EVENT_TYPES


def test_live_hub_fans_out_per_subscriber_and_ends_on_terminal_event():
    async def scenario():
        hub = DiscoveryLiveHub()
        seen: list[str] = []

        async def consume():
            async for payload in hub.subscribe("run_live"):
                seen.append(payload["type"])

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        hub.publish("run_live", event_payload("state.observed", seq=1))
        hub.publish("run_live", event_payload("run.finished", seq=2))
        await asyncio.wait_for(task, timeout=1)
        return seen

    assert asyncio.run(scenario()) == ["state.observed", "run.finished"]


def test_live_hub_drops_the_oldest_payload_instead_of_blocking_the_run():
    async def scenario():
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        DiscoveryLiveHub._put(queue, event_payload("frame.1", seq=1))
        DiscoveryLiveHub._put(queue, event_payload("frame.2", seq=2))
        return queue.get_nowait()["type"]

    assert asyncio.run(scenario()) == "frame.2"


def test_stream_ticket_scope_covers_the_discovery_stream_only():
    path = "/api/discovery/runs/run_123/stream"
    assert is_stream_route(path) is True
    assert stream_ticket_scope(path) == "discovery:run_123"
    assert stream_ticket_scope("/api/discovery/runs/run_123/events") is None


def test_event_generator_replays_history_then_finishes_for_a_terminal_run(monkeypatch):
    service = QualityDiscoveryService(None, browser_runtime=DiscoveryFixtureBrowserRuntime())
    row = SimpleNamespace(
        status=DiscoveryStatus.BLOCKED.value,
        progress={"states": 1, "actions": 0},
        result={"events": [{"id": "e1", "type": "state.observed", "message": "已观察", "metadata": {}}]},
    )
    monkeypatch.setattr(service, "get", lambda run_id: asyncio.sleep(0, result=row))

    async def collect():
        return [frame async for frame in service.event_generator("run_terminal")]

    frames = asyncio.run(collect())
    assert [frame.splitlines()[0] for frame in frames] == ["event: snapshot", "event: run.finished"]
    assert "state.observed" in frames[0]
    assert '"BLOCKED"' in frames[-1]


def test_frame_pump_publishes_jpeg_frames_only_while_a_viewer_is_attached(monkeypatch):
    runtime = _FramingRuntime()
    frozen_config = _config_with_fast_frames()
    monkeypatch.setattr(discovery_module, "get_config", lambda: frozen_config)
    service = QualityDiscoveryService(None, browser_runtime=runtime)
    monkeypatch.setattr(
        service, "get", lambda run_id: asyncio.sleep(0, result=SimpleNamespace(status="RUNNING", progress={}))
    )
    service.track_live_browser("run_pump", session_id="session_1", url="https://shop.example.test/cart")

    async def scenario():
        frames: list[dict] = []

        async def consume():
            async for payload in service.live.subscribe("run_pump"):
                if payload["type"] == "browser.frame":
                    frames.append(payload)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        assert service.live.has_subscribers("run_pump")
        pump = asyncio.create_task(service._pump_frames("run_pump"))
        for _ in range(200):
            if frames:
                break
            await asyncio.sleep(0.01)
        pump.cancel()
        task.cancel()
        return frames

    frames = asyncio.run(scenario())
    assert frames, "an attached viewer must receive browser frames"
    assert frames[0]["metadata"]["mime_type"] == "image/jpeg"
    assert frames[0]["metadata"]["url"] == "https://shop.example.test/cart"
    assert frames[0]["metadata"]["frame"]
    assert runtime.frames_served >= 1


def _config_with_fast_frames():
    base = discovery_module.get_config()
    return base.model_copy(update={"discovery": base.discovery.model_copy(update={"live_frame_interval_ms": 100})})


async def test_live_stream_carries_frames_and_element_inventory_for_a_running_run(client, test_db_session):
    runtime = _FramingRuntime()
    frozen_config = _config_with_fast_frames()
    async with _live_service(test_db_session, runtime=runtime):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(discovery_module, "get_config", lambda: frozen_config)
            run_id = await _started_run(client, "Live Discovery Frames")
            frames = await _read_frames(
                client,
                run_id,
                until=lambda read: (
                    any(f["event"] == "browser.frame" for f in read)
                    and any(f["event"] == "element.inventory" for f in read)
                ),
            )
        assert frames[0]["event"] == "snapshot"
        kinds = [frame["event"] for frame in frames]
        assert "element.inventory" in kinds, kinds
        assert "browser.frame" in kinds, kinds
        inventory = next(frame for frame in frames if frame["event"] == "element.inventory")
        elements = inventory["data"]["metadata"]["elements"]
        assert {element["name"] for element in elements} >= {"Search", "Products", "Cart"}
        assert all(element["bounding_box"] is not None for element in elements)
        frame = next(frame for frame in frames if frame["event"] == "browser.frame")
        assert frame["data"]["metadata"]["url"] == "http://shop.example.test/"
        assert base64.b64decode(frame["data"]["metadata"]["frame"]) == b"\xff\xd8\xff\xe0frame"


async def test_discovery_stream_is_invisible_to_unrelated_users(client, test_db_session):
    async with _live_service(test_db_session):
        run_id = await _started_run(client, "Live Discovery Private")
        email = "live.discovery.outsider@example.com"
        created = await client.post(
            "/api/users",
            json={"email": email, "full_name": "outsider", "role": "QA_ENGINEER", "password": PASSWORD},
        )
        assert created.status_code == 201, created.text
        async with bearer_client(await login_token(client, email, PASSWORD)) as outsider:
            # 404, not 403: the stream must not even reveal that the run exists.
            assert (await outsider.get(f"/api/discovery/runs/{run_id}/stream")).status_code == 404
            assert (await outsider.get(f"/api/discovery/runs/{run_id}/events")).status_code == 404


async def test_discovery_stream_ticket_is_scoped_to_its_run(client, anonymous_client, test_db_session):
    async with _live_service(test_db_session):
        run_id = await _started_run(client, "Live Discovery Ticket")
        other_run_id = await _started_run(client, "Live Discovery Other")
        issued = await client.post("/api/auth/stream-ticket", json={"kind": "discovery", "resource_id": run_id})
        assert issued.status_code == 200, issued.text
        headers = {"Authorization": f"Bearer {issued.json()['stream_ticket']}"}
        wrong_run = await anonymous_client.get(f"/api/discovery/runs/{other_run_id}/stream", headers=headers)
        assert wrong_run.status_code == 401
        frames = await _read_frames(anonymous_client, run_id, until=lambda read: bool(read), limit=1, headers=headers)
        assert frames[0]["event"] == "snapshot"


async def test_ai_provider_failure_degrades_to_deterministic_exploration(client, test_db_session):
    ai = _UnavailableAI()
    async with _live_service(test_db_session, provider_factory=lambda: ai, runtime=_FramingRuntime()):
        run_id = await _started_run(client, "Live Discovery Degrade", requirement_text="搜索商品后可以看到搜索结果。")
        body = await _await_terminal(client, run_id)

    assert ai.calls > 0, "the provider must actually have been called"
    assert body["status"] != DiscoveryStatus.FAILED.value, body.get("error")
    events = [event["type"] for event in body["result"]["events"]]
    assert "ai.unavailable" in events, events
    # The browser work must survive the AI outage: observation continues after the failure.
    assert "state.observed" in events, events
    assert events.index("state.observed") > events.index("ai.unavailable"), events
    assert body["result"]["states"], "collected page evidence must not be lost when the AI is down"
    assert body["result"]["decisions"], "Jev must still choose from service-generated candidates"


async def _drain_generator(service, run_id: str, *, budget: float) -> list[str]:
    """Collect the raw SSE frames of one stream, failing loudly instead of hanging."""
    frames: list[str] = []

    async def consume() -> None:
        async for frame in service.event_generator(run_id):
            frames.append(frame)

    await asyncio.wait_for(consume(), timeout=budget)
    return frames


async def test_viewer_attaching_after_finalization_is_not_left_waiting(test_db_session, monkeypatch):
    """A run can finalize between the stream's status read and its subscription.

    In that window the terminal event is published while no subscriber is attached AND the frame pump
    has already been cancelled by finalization, so nothing can wake the viewer up. Before the safety
    net in ``event_generator`` this blocked the read (and the test process) forever.
    """
    service = QualityDiscoveryService(
        test_db_session,
        browser_runtime=DiscoveryFixtureBrowserRuntime(),
        provider_factory=lambda: DiscoveryFixtureAI(),
        decisions=_OfflineDecisions(),
    )
    run_id = "qd_late_viewer_unit"
    # The terminal event was published with nobody attached, so it went nowhere.
    service.live.publish(run_id, event_payload("run.finished", seq=9, metadata={"status": "COMPLETED"}))
    assert not service.live.has_subscribers(run_id)

    monkeypatch.setattr(discovery_module, "LIVE_STREAM_IDLE_TIMEOUT_S", 0.2)
    calls = {"count": 0}

    async def get(_run_id: str):
        calls["count"] += 1
        status = "RUNNING" if calls["count"] == 1 else "COMPLETED"
        return SimpleNamespace(status=status, progress={}, result={})

    monkeypatch.setattr(service, "get", get)
    # Model the pump that finalization already cancelled: present, but it never publishes again.
    stale_pump = asyncio.create_task(asyncio.sleep(30))
    service._pumps[run_id] = stale_pump
    try:
        frames = await _drain_generator(service, run_id, budget=10)
    finally:
        stale_pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stale_pump

    assert frames[0].startswith("event: snapshot"), frames[:1]
    assert frames[-1].startswith("event: run.finished"), frames[-1]
    assert '"COMPLETED"' in frames[-1]
    assert calls["count"] >= 2, "the stream must re-read the run row instead of waiting forever"
