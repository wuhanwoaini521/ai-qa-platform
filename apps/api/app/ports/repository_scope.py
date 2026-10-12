from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol


class RepositoryScope(Protocol):
    """Application-facing repositories and one transaction boundary."""

    tasks: Any
    evidence: Any
    failures: Any
    failure_analyses: Any
    breakpoints: Any
    projects: Any
    requirements: Any
    test_cases: Any
    test_designs: Any
    test_runs: Any
    automation_bindings: Any
    workspaces: Any
    provider_settings: Any
    decision_settings: Any
    ai_budgets: Any
    jobs: Any
    locator_history: Any
    locator_repairs: Any
    browser_sessions: Any
    runner_profiles: Any
    workers: Any
    golden_demo: Any

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class RepositoryScopeFactory(Protocol):
    """Application port implemented by a persistence adapter."""

    def __call__(self) -> AbstractAsyncContextManager[RepositoryScope]: ...
