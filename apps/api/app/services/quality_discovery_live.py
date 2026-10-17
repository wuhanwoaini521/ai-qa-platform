"""Live fan-out for an in-flight Quality Discovery run.

``result["events"]`` on the run row stays the single source of truth (bounded by
``discovery.max_events``); this hub only mirrors each appended event to stream subscribers and keeps
the newest browser frame per run. It is a fan-out, not a second execution path and not a second
event store: nothing here is persisted, and the frame slot is dropped when the run ends.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

#: Event vocabulary of the live discovery stream. ``snapshot`` and ``browser.frame`` are stream-only.
DISCOVERY_EVENT_TYPES = (
    "snapshot",
    "run.status",
    "page.opened",
    "page.state",
    "element.inventory",
    "action.planned",
    "action.executed",
    "ai.decision",
    "ai.unavailable",
    "finding",
    "evidence.captured",
    "coverage.updated",
    "browser.frame",
    "error",
    "run.finished",
)

TERMINAL_EVENT_TYPES = frozenset({"run.finished"})


def event_payload(event_type: str, *, seq: int, message: str = "", metadata: dict | None = None) -> dict[str, Any]:
    return {
        "type": event_type,
        "seq": seq,
        "message": message,
        "metadata": metadata or {},
        "at": datetime.now(timezone.utc).isoformat(),
    }


class DiscoveryLiveHub:
    """Per-run pub/sub with bounded buffering; publishing never blocks and never raises."""

    def __init__(self, *, max_queue: int = 256) -> None:
        self.max_queue = max_queue
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._frames: dict[str, dict] = {}

    def has_subscribers(self, run_id: str) -> bool:
        return bool(self._subscribers.get(run_id))

    def publish(self, run_id: str, payload: dict) -> None:
        queues = self._subscribers.get(run_id)
        if not queues:
            return
        for queue in list(queues):
            self._put(queue, payload)
        if payload.get("type") in TERMINAL_EVENT_TYPES:
            self.release(run_id)

    def publish_frame(self, run_id: str, payload: dict) -> None:
        self._frames[run_id] = payload
        self.publish(run_id, payload)

    def release(self, run_id: str) -> None:
        """Drop everything held for a run; called when it ends and when it is finalized."""
        self._frames.pop(run_id, None)

    async def subscribe(self, run_id: str) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        self._subscribers.setdefault(run_id, set()).add(queue)
        try:
            while True:
                payload = await queue.get()
                yield payload
                if payload.get("type") in TERMINAL_EVENT_TYPES:
                    return
        finally:
            queues = self._subscribers.get(run_id)
            if queues is not None:
                queues.discard(queue)
                if not queues:
                    self._subscribers.pop(run_id, None)
                    # Last viewer left: a frame kept for late joiners would otherwise be retained
                    # for the lifetime of the process.
                    self.release(run_id)

    @staticmethod
    def _put(queue: asyncio.Queue, payload: dict) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # A slow viewer must never stall the run: drop the oldest frame/event instead.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass
