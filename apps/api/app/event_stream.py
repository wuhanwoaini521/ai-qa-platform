"""Encode typed domain events at the HTTP transport boundary."""

import json


def event_frame(event_type: str, payload, *, event_id: str | int | None = None) -> str:
    if callable(getattr(payload, "model_dump", None)):
        payload = payload.model_dump(mode="json")
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
