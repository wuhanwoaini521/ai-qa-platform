from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_model.models import DecisionRequest, DecisionResult


class DecisionProvider(Protocol):
    name: str

    async def choose(self, request: DecisionRequest) -> DecisionResult: ...


class DecisionProviderRegistry:
    """Small provider factory; product features only depend on DecisionService."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[object], DecisionProvider]] = {}

    def register(self, name: str, factory: Callable[[object], DecisionProvider]) -> None:
        self._factories[name.lower()] = factory

    def create(self, name: str, config: object) -> DecisionProvider:
        factory = self._factories.get(name.lower())
        if factory is None:
            raise ValueError(f"Decision provider '{name}' is not registered")
        return factory(config)
