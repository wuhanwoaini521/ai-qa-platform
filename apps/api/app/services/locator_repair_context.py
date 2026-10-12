from __future__ import annotations

from contextvars import ContextVar, Token

_current_locator_repair_id: ContextVar[str | None] = ContextVar("current_locator_repair_id", default=None)


def current_locator_repair_id() -> str | None:
    return _current_locator_repair_id.get()


def bind_locator_repair(repair_id: str) -> Token[str | None]:
    return _current_locator_repair_id.set(repair_id)


def reset_locator_repair(token: Token[str | None]) -> None:
    _current_locator_repair_id.reset(token)
