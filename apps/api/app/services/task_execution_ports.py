from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

from app.ports.browser_runtime import BrowserRuntime


@dataclass
class TaskExecutionPorts:
    """Task capabilities shared with execution services, separate from scheduler state."""

    browser_runtime: BrowserRuntime
    active_runtime_step: ContextVar[str | None]
    active_task_deadline: ContextVar[float | None]
    child_runs: dict[str, str]
    repository_scope: Callable[..., Any]
    input: Callable[..., Any]
    load_task: Callable[..., Any]
    record_ai_trace: Callable[..., Any]
    browser_agent_event: Callable[..., Any]
    persist_browser_agent_state: Callable[..., Any]
    persist_browser_agent_artifact: Callable[..., Any]
    persist_browser_agent_evidence: Callable[..., Any]
    artifact: Callable[..., Any]
    evidence: Callable[..., Any]
    execute_browser_candidate: Callable[..., Any]
    recorder_storage_state: Callable[..., Any]
    call_code_ai: Callable[..., Any]
    inspect_source: Callable[..., Any]
    review_source: Callable[..., Any]
    validate_python_test: Callable[..., Any]
    workspace_source_digest: Callable[..., Any]
    write_approved_source: Callable[..., Any]
    persist_artifact: Callable[..., Any]
