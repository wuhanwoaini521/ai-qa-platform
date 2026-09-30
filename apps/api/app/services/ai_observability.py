from __future__ import annotations

import logging
from uuid import uuid4


def log_ai_execution(
    logger: logging.Logger,
    *,
    feature: str,
    provider: str,
    model: str,
    duration_ms: float,
    status: str,
    fallback_used: bool,
    tool_count: int = 0,
    run_id: str | None = None,
) -> str:
    """Write a standard, credential-free summary for one AI execution."""
    execution_id = run_id or uuid4().hex
    logger.info(
        "AI run run_id=%s provider=%s model=%s feature=%s duration_ms=%.1f status=%s fallback_used=%s tool_count=%d",
        execution_id,
        provider,
        model,
        feature,
        duration_ms,
        status,
        fallback_used,
        tool_count,
    )
    return execution_id
