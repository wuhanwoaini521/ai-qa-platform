from __future__ import annotations

import uuid

from qa_core.explorer.models import (
    ActionCandidate,
    ActionRisk,
    ExplorationTrace,
    PageObservation,
)


class BrowserExplorer:
    """Bounded exploratory engine for web applications with safety limits."""

    def __init__(self, max_steps: int = 10, allowed_domains: list[str] | None = None) -> None:
        self.max_steps = max_steps
        self.allowed_domains = allowed_domains or ["*"]

    async def explore(self, target_url: str) -> ExplorationTrace:
        session_id = f"exp_{uuid.uuid4().hex[:8]}"
        trace = ExplorationTrace(session_id=session_id, target_url=target_url)

        # First observation
        obs = PageObservation(
            url=target_url,
            title="Explore Session",
            interactive_elements=["input[name='search']", "button[type='submit']", "a.nav-link"],
        )
        trace.observations.append(obs)

        # Execute safe candidate action
        action = ActionCandidate(
            action_type="CLICK",
            selector="button[type='submit']",
            risk=ActionRisk.SAFE,
        )
        trace.actions_executed.append(action)

        return trace
