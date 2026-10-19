from __future__ import annotations

from typing import Any


class TaskBlocked(RuntimeError):
    """The goal cannot continue safely without a user decision or unavailable dependency."""

    def __init__(self, message: str, *, failure_type: str = "STEP_BLOCKED", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.failure_type = failure_type
        self.details = details or {}


class TaskCancelled(Exception):
    """The goal was stopped by the user, so the runtime ends the task as cancelled, not blocked."""


class ApprovalRequired(Exception):
    pass
