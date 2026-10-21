from __future__ import annotations

from contextvars import ContextVar, Token

Lease = tuple[str, int]

_current: ContextVar[Lease | None] = ContextVar("task_lease", default=None)


def current_lease() -> Lease | None:
    """The lease the running task holds, when this process took one."""
    return _current.get()


def lease_scope(owner: str, token: int) -> Token[Lease | None]:
    return _current.set((owner, token))


def reset_lease(token: Token[Lease | None]) -> None:
    _current.reset(token)
