"""Request context propagates through asyncio without sharing state between callers."""

from contextvars import ContextVar

request_id_context: ContextVar[str | None] = ContextVar("qa_request_id", default=None)
