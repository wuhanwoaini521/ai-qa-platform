from __future__ import annotations

from typing import Protocol


class DatabaseHealthProbe(Protocol):
    async def check(self) -> dict[str, object]: ...
