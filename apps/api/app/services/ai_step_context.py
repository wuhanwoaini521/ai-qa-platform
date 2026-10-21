"""Carry the active task step to whichever provider call happens inside it.

``TaskExecutionOrchestrator`` already records the running step in ``active_runtime_step``; this
variable lets the AI repository persist the same fact on the invocation row without threading a
parameter through every provider call.
"""

from contextvars import ContextVar, Token

_current_ai_step_id: ContextVar[str | None] = ContextVar("current_ai_step_id", default=None)


def current_ai_step_id() -> str | None:
    return _current_ai_step_id.get()


def ai_step_scope(step_id: str | None) -> Token:
    return _current_ai_step_id.set(step_id)


def reset_ai_step(token: Token) -> None:
    _current_ai_step_id.reset(token)
