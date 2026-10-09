from qa_core.ai.budget import AIBudgetGuard
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator

from app.settings import get_config


def build_ai_budget_guard() -> AIBudgetGuard:
    budget = get_config().ai.budget
    return AIBudgetGuard(
        enabled=budget.enabled,
        max_requests=budget.max_requests_per_run,
        max_input_tokens=budget.max_input_tokens_per_run,
        max_output_tokens=budget.max_output_tokens_per_run,
    )


def build_ai_orchestrator() -> ProductionQAOrchestrator:
    return ProductionQAOrchestrator(budget_guard=build_ai_budget_guard())
