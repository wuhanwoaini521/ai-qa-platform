from __future__ import annotations

from collections.abc import Awaitable, Callable

from project_model.models import DecisionResult

from app.ports.repository_scope import RepositoryScopeFactory
from app.services.decision_service import DecisionService


class _BudgetExhaustedDecisionService:
    async def choose(self, request, *, run_id=None):
        return DecisionResult(provider="fallback", fallback_used=True, reason="task_ai_budget_exhausted")


class TaskDecisionService:
    """Own Jev provider access for task decisions and locator selection."""

    def __init__(
        self,
        repository_scope: RepositoryScopeFactory,
        reserve_ai_call: Callable[[str], Awaitable[bool]],
    ) -> None:
        self.repository_scope = repository_scope
        self.reserve_ai_call = reserve_ai_call

    async def choose(self, request, *, task_id: str, run_id: str):
        async def reserve_task_call() -> bool:
            return await self.reserve_ai_call(task_id)

        return await DecisionService(repository_scope=self.repository_scope).choose(
            request,
            task_id=task_id,
            run_id=run_id,
            reserve_task_call=reserve_task_call,
        )

    async def ask_score(self, request, *, task_id: str, run_id: str):
        async def reserve_task_call() -> bool:
            return await self.reserve_ai_call(task_id)

        return await DecisionService(repository_scope=self.repository_scope).ask_score(
            request,
            task_id=task_id,
            run_id=run_id,
            reserve_task_call=reserve_task_call,
        )

    def locator_provider(self, *, budget_available: bool):
        return (
            DecisionService(repository_scope=self.repository_scope)
            if budget_available
            else _BudgetExhaustedDecisionService()
        )
