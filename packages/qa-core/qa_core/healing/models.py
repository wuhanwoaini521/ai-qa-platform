from __future__ import annotations

from pydantic import BaseModel


class LocatorCandidate(BaseModel):
    selector: str
    strategy: str  # e.g., "data-testid", "role-and-name", "semantic-text", "id"
    confidence: float
    reason: str


class LocatorRepairProposal(BaseModel):
    old_locator: str
    proposed_locator: str
    confidence: float
    strategy: str
    reason: str
    code_diff: str = ""
    file_path: str | None = None
    applied: bool = False
