from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from qa_core.failure.redactor import SensitiveRedactor


class AITraceEvent(BaseModel):
    """Safe, provider-neutral progress event for one AI execution run."""

    run_id: str
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage: str
    title: str
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_metadata(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return SensitiveRedactor.redact_value(value)

    @field_validator("content")
    @classmethod
    def redact_content(cls, value: str | None) -> str | None:
        return SensitiveRedactor.redact_text(value) if value is not None else None


def make_trace_event(
    run_id: str,
    event_type: str,
    *,
    stage: str,
    title: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    content: str | None = None,
) -> AITraceEvent:
    return AITraceEvent(
        run_id=run_id,
        type=event_type,
        stage=stage,
        title=title,
        message=message,
        metadata=metadata or {},
        content=content,
    )
