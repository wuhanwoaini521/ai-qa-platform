from __future__ import annotations

from project_model.models import FailureRepairState, LocatorRepairFunnelResponse

from app.ports.repository_scope import RepositoryScopeFactory


class LocatorRepairFunnelService:
    def __init__(self, repository_scope: RepositoryScopeFactory) -> None:
        self.repository_scope = repository_scope

    async def summarize(self, project_id: str) -> LocatorRepairFunnelResponse:
        async with self.repository_scope() as repositories:
            metrics = await repositories.locator_repairs.funnel(project_id)

        stage_counts = {state.value: metrics["state_counts"].get(state.value, 0) for state in FailureRepairState}
        return LocatorRepairFunnelResponse(
            project_id=project_id,
            total_repairs=sum(stage_counts.values()),
            stage_counts=stage_counts,
            blocking_reasons=metrics["blocking_reasons"],
            ai_invocations=metrics["ai_invocations"],
        )
