from datetime import datetime, timezone

import pytest
from app.services.event_normalizer import normalize_event, public_metadata


@pytest.mark.parametrize(
    "event_type,expected,category",
    [
        ("RUN_STARTED", "run.started", "lifecycle"),
        ("RUN_FINISHED", "run.completed", "lifecycle"),
        ("TEST_FINISHED", "test.completed", "test"),
        ("BROWSER_TELEMETRY", "browser.telemetry", "browser"),
        ("step.failed", "step.failed", "step"),
        ("artifact.created", "artifact.created", "artifact"),
        ("future.event", "future.event", "system"),
    ],
)
def test_actual_event_vocabularies(event_type, expected, category):
    event = normalize_event(
        {"type": event_type}, source="run", source_id="event-1", runtime_id="runtime", test_run_id="test"
    )
    assert event.type == expected and event.category == category
    assert event.timestamp is None and event.duration_ms is None


def test_trace_run_id_is_never_misrepresented_as_a_test_run_id_and_cot_is_excluded():
    raw = {
        "type": "ai.trace",
        "payload": {
            "run_id": "trace-only",
            "type": "decision_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": "decision",
            "title": "Selected candidate",
            "message": "provider decision",
            "content": "private reasoning",
            "metadata": {
                "provider": "jev",
                "confidence": 0.8,
                "prompt": "private prompt",
                "scratchpad": "secret",
                "authorization": "Bearer abc",
                "nested": {"cookie": "secret"},
            },
        },
    }
    event = normalize_event(
        raw, source="task", source_id="42", runtime_id="task", task_id="task", test_run_id="actual-test"
    )
    assert event.trace_run_id == "trace-only" and event.test_run_id == "actual-test"
    assert event.task_id == "task" and event.category == "decision"
    assert event.metadata == {"provider": "jev", "confidence": 0.8}
    assert "private" not in event.model_dump_json() and "secret" not in event.model_dump_json()


def test_child_run_mapping_and_frame_exclusion():
    event = normalize_event(
        {"type": "step.progress", "payload": {"type": "child_run.started", "run_id": "child", "step_id": "step"}},
        source="task",
        source_id="42",
        runtime_id="parent",
        task_id="parent",
    )
    assert event.test_run_id == "child" and event.trace_run_id is None and event.step_id == "step"
    assert event.type == "child_run.started" and event.category == "test"
    assert (
        normalize_event({"type": "BROWSER_FRAME", "frame": "base64"}, source="run", source_id="1", runtime_id="r")
        is None
    )


def test_metadata_is_scalar_whitelisted_and_uses_existing_redactor():
    assert public_metadata(
        {
            "provider": "jev",
            "url": "https://user:pass@example.com/path?api_key=private",
            "confidence": float("nan"),
            "minimum_confidence": 0.6,
            "attempted_choice": "search",
            "candidate_count": 3,
            "secret": "hidden",
        }
    ) == {
        "provider": "jev",
        "url": "https://example.com/path",
        "minimum_confidence": 0.6,
        "attempted_choice": "search",
        "candidate_count": 3,
    }
    assert public_metadata(None) == {}


def test_missing_trace_time_stays_unavailable():
    event = normalize_event(
        {"run_id": "trace", "type": "model.started", "stage": "model", "title": "Model started"},
        source="ai",
        source_id="trace-event",
        runtime_id="runtime",
    )
    assert event.timestamp is None
    assert event.trace_run_id == "trace" and event.test_run_id is None


def test_task_blocked_event_derives_blocked_status():
    event = normalize_event(
        {"type": "task.blocked"}, source="task", source_id="blocked", runtime_id="task", task_id="task"
    )
    assert event.status == "BLOCKED"


def test_diagnosis_trace_has_failure_category_not_generic_ai():
    event = normalize_event(
        {"run_id": "trace", "type": "diagnosis_completed", "stage": "diagnosis", "title": "Diagnosis"},
        source="ai",
        source_id="e",
        runtime_id="r",
    )
    assert event.category == "failure"


def test_browser_recorded_time_and_safe_metadata_exclude_request_body():
    event = normalize_event(
        {
            "type": "browser.network_logs",
            "timestamp": "2026-10-02T00:00:00Z",
            "url": "https://example.com?token=hidden",
            "method": "GET",
            "request": {"authorization": "private"},
            "frame": "base64",
        },
        source="browser",
        source_id="s:event",
        runtime_id="r",
        test_run_id="r",
    )
    assert event.category == "browser" and event.timestamp is not None
    assert event.metadata == {"url": "https://example.com", "method": "GET"}
    assert "private" not in event.model_dump_json() and "base64" not in event.model_dump_json()


def test_public_metadata_bounds_individual_fields_after_redacting_credentials():
    metadata = public_metadata({"model": "x" * 100000, "provider": "authorization=private"})
    assert len(metadata["model"]) == 500
    assert "private" not in metadata["provider"]


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf")])
def test_invalid_trace_durations_stay_unavailable(duration):
    event = normalize_event(
        {"run_id": "trace", "type": "model.completed", "stage": "model", "title": "Complete", "duration_ms": duration},
        source="ai",
        source_id="trace-event",
        runtime_id="runtime",
    )
    assert event.duration_ms is None
