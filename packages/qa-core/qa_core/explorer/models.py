from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ActionRisk(str, Enum):
    SAFE = "SAFE"
    MODERATE = "MODERATE"
    DESTRUCTIVE = "DESTRUCTIVE"


class ActionCandidate(BaseModel):
    action_type: str  # "CLICK", "FILL", "NAVIGATE"
    selector: str
    value: str | None = None
    risk: ActionRisk = ActionRisk.SAFE


class PageObservation(BaseModel):
    url: str
    title: str = ""
    interactive_elements: list[str] = Field(default_factory=list)


class ExplorationTrace(BaseModel):
    session_id: str
    target_url: str
    observations: list[PageObservation] = Field(default_factory=list)
    actions_executed: list[ActionCandidate] = Field(default_factory=list)
