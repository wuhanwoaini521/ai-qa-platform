"""Pure mapping of actual event vocabularies into safe Runtime events."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from qa_core.ai.trace import AITraceEvent
from qa_core.failure.redactor import SensitiveRedactor

from app.services.runtime_models import NormalizedRuntimeEvent

PUBLIC_METADATA = frozenset(
    {
        "provider",
        "model",
        "stage",
        "confidence",
        "minimum_confidence",
        "attempted_choice",
        "candidate_count",
        "selected",
        "candidate_id",
        "selected_locator",
        "engine",
        "choice",
        "verified",
        "verification_source",
        "unique",
        "visible",
        "enabled",
        "actionable",
        "fallback_used",
        "fallback_reason",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "token_source",
        "retry_count",
        "provider_error",
        "planner_mode",
        "upstream_provider",
        "upstream_model",
        "actions_already_executed",
        "current_url",
        "interactive_session_available",
        "manual_resume_available",
        "verification_artifact_id",
        "generated_chars",
        "key",
        "tool",
        "nodeid",
        "url",
        "action",
        "method",
        "level",
        "status_code",
        "locator",
        "status",
        "decision_id",
        "artifact_id",
        "approved",
        "skipped",
        "error_type",
        "failure_type",
        "candidate_summary",
        "candidate_scores",
        "expected_effect",
        "rejected_count",
        "subgoal_count",
        "network_requests",
        "network_failed",
        "state_hash",
        "action_count",
        "goal_completed",
        "operation",
        "jev_attempted",
        "ai_preference",
        "blocked_candidates",
    }
)
TRACE_TYPES = frozenset(
    {
        "workflow.step",
        "workflow.plan",
        "run.started",
        "context.loaded",
        "evidence.collected",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "decision.started",
        "decision.completed",
        "decision.fallback",
        "model.started",
        "model.progress",
        "model.completed",
        "validation.started",
        "validation.completed",
        "validation.failed",
        "run.completed",
        "run.failed",
        "run.cancelled",
        "analysis_started",
        "evidence_collected",
        "candidates_generated",
        "decision_started",
        "decision_completed",
        "verification_started",
        "verification_completed",
        "diagnosis_completed",
        "repair_suggested",
        "failed",
    }
)
RUN_TYPES = {
    "CONNECTED": "runtime.connected",
    "RUN_STARTED": "run.started",
    "RUN_FINISHED": "run.completed",
    "RUN_ERROR": "run.failed",
    "RUN_CANCELLED": "run.cancelled",
    "TEST_FINISHED": "test.completed",
    "LOG_STREAM": "log",
    "BROWSER_SESSION": "browser.session",
    "BROWSER_TELEMETRY": "browser.telemetry",
}


def public_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    value = {
        key: item
        for key, item in raw.items()
        if key in PUBLIC_METADATA
        and isinstance(item, (str, int, float, bool, type(None)))
        and not (isinstance(item, float) and not math.isfinite(item))
    }
    redacted = SensitiveRedactor.redact_value(value)
    # Event count bounds alone do not bound memory when one provider field is unbounded.
    return {key: item[:500] if isinstance(item, str) else item for key, item in redacted.items()}


def _text(value: Any) -> str:
    return SensitiveRedactor.redact_text(str(value or ""))[:500]


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def _duration(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def normalize_event(
    raw: dict[str, Any],
    *,
    source: str,
    source_id: str,
    runtime_id: str,
    task_id: str | None = None,
    test_run_id: str | None = None,
) -> NormalizedRuntimeEvent | None:
    original = str(raw.get("type") or "unknown")
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
    trace_id = None
    timestamp = _timestamp(raw.get("created_at") or raw.get("timestamp"))
    metadata = public_metadata(payload)
    status = payload.get("status") if isinstance(payload.get("status"), str) else None
    duration = _duration(payload.get("duration_ms"))
    title = _text(payload.get("key") or original)
    summary = ""
    event_type = RUN_TYPES.get(original, original)
    step_id = raw.get("step_id") or payload.get("step_id")
    if original == "BROWSER_FRAME":
        return None
    if original == "ai.trace" or source == "ai":
        if payload.get("type") not in TRACE_TYPES:
            return None  # Delta/content/reasoning events have no place in a public observatory.
        try:
            trace = AITraceEvent.model_validate(payload)
        except ValidationError:
            return None
        event_type, trace_id = trace.type, trace.run_id
        timestamp = _timestamp(payload.get("timestamp")) or timestamp
        title, summary = _text(trace.title), _text(trace.message)
        status, duration, step_id = trace.status, _duration(trace.duration_ms), trace.step_id or step_id
        metadata = public_metadata(trace.metadata)
    elif source == "task" and original != "BROWSER_TELEMETRY":
        title = _text(payload.get("title") or title)
        summary = _text(payload.get("summary") or summary)
        if original == "step.progress" and str(payload.get("type", "")).startswith("child_run."):
            event_type = payload["type"]
        # run_id in a Task payload denotes a child TestRun, never an AI trace.
        child_id = payload.get("run_id")
        if isinstance(child_id, str):
            test_run_id = child_id
    elif source == "browser" or original == "BROWSER_TELEMETRY":
        browser_payload = payload
        if original == "BROWSER_TELEMETRY":
            test_run_id = test_run_id or (str(raw["run_id"]) if raw.get("run_id") else None)
            entry = payload.get("entry")
            browser_payload = entry if isinstance(entry, dict) else payload
            channel = str(payload.get("channel") or "").lower()
            original = {
                "step": "browser.recent_steps",
                "network": "browser.network_logs",
                "console": "browser.console_logs",
            }.get(channel, "browser.telemetry")
            event_type = original
        if original == "browser.recent_steps":
            action = _text(browser_payload.get("action") or "操作")
            locator = _text(browser_payload.get("locator") or "")
            title = "Browser action"
            summary = " · ".join(part for part in (action, locator) if part)
            status = browser_payload.get("status") if isinstance(browser_payload.get("status"), str) else None
            duration = _duration(browser_payload.get("duration_ms")) or duration
            metadata = public_metadata(browser_payload)
        elif original == "browser.network_logs":
            method = _text(browser_payload.get("method") or "HTTP")
            url = SensitiveRedactor.redact_url(str(browser_payload.get("url") or ""))
            status_code = browser_payload.get("status")
            if isinstance(status_code, int) and not isinstance(status_code, bool):
                metadata["status_code"] = status_code
                status = "FAILED" if status_code >= 400 else "COMPLETED"
            failure = _text(browser_payload.get("failure") or "")
            title = "Network request"
            summary = " · ".join(part for part in (method, url, str(status_code) if status_code else failure) if part)
            duration = _duration(browser_payload.get("duration_ms")) or duration
            metadata = {**metadata, **public_metadata(browser_payload)}
        elif original == "browser.console_logs":
            level = _text(browser_payload.get("level") or "log")
            message = _text(browser_payload.get("text") or browser_payload.get("message") or "")
            title = "Console message"
            summary = " · ".join(part for part in (level, message) if part)
            metadata = public_metadata(browser_payload)
        else:
            title = "Browser telemetry"
            summary = _text(browser_payload.get("message") or browser_payload.get("status") or "")
            metadata = public_metadata(browser_payload)
    elif source == "run":
        test_run_id = test_run_id or (str(raw["run_id"]) if raw.get("run_id") else None)
        if original == "TEST_FINISHED":
            run_status = payload.get("status") if isinstance(payload.get("status"), str) else None
            event_type = "test.failed" if run_status and run_status.upper() in {"FAILED", "ERROR"} else "test.completed"
            title = _text(payload.get("nodeid") or payload.get("case_name") or "Test")
            status = run_status
            summary = _text(payload.get("summary") or "")
    if event_type.startswith(("decision", "verification")) or event_type == "candidates_generated":
        category = "decision"
    elif event_type.startswith("workflow."):
        category = "step"
    elif event_type.startswith(("failure.", "diagnosis", "repair")):
        category = "failure"
    elif original == "ai.trace" or source == "ai":
        category = "ai"
    elif event_type.startswith("step."):
        category = "step"
    elif event_type.startswith(("test.", "child_run.")):
        category = "test"
    elif event_type.startswith("browser."):
        category = "browser"
    elif event_type.startswith(("failure.", "diagnosis", "repair")):
        category = "failure"
    elif event_type.startswith("artifact."):
        category = "artifact"
    elif event_type.startswith(("task.", "run.", "runtime.")):
        category = "lifecycle"
    else:
        category = "system"
    if status is None:
        status = next(
            (
                value
                for suffix, value in {
                    "started": "RUNNING",
                    "completed": "COMPLETED",
                    "failed": "FAILED",
                    "blocked": "BLOCKED",
                    "cancelled": "CANCELLED",
                    "retrying": "RETRYING",
                }.items()
                if event_type.endswith(suffix)
            ),
            None,
        )
    return NormalizedRuntimeEvent(
        id=f"{source}:{source_id}",
        source=source,
        source_id=source_id,
        runtime_id=runtime_id,
        task_id=task_id,
        test_run_id=test_run_id,
        trace_run_id=trace_id,
        step_id=step_id if isinstance(step_id, str) else None,
        timestamp=timestamp,
        type=event_type,
        category=category,
        status=status,
        title=title,
        summary=summary,
        duration_ms=duration,
        metadata=metadata,
    )
