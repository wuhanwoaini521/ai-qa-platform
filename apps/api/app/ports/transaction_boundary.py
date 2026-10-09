from __future__ import annotations

from typing import Protocol


class TransactionBoundary(Protocol):
    """Commit or roll back one application use case transaction."""

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
