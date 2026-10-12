from __future__ import annotations

from project_model.models import FailureReplaySummary
from pydantic import BaseModel, Field

from qa_core.ai.trace import AITraceEvent


class LocatorCandidate(BaseModel):
    selector: str
    strategy: str  # e.g., "data-testid", "role-and-name", "semantic-text", "id"
    confidence: float
    reason: str


class LocatorRepairProposal(BaseModel):
    old_locator: str
    source_locator: str | None = None
    proposed_locator: str
    confidence: float | None = None
    strategy: str
    reason: str
    candidate_id: str | None = None
    provider: str = "local-strategy"
    model: str | None = None
    latency_ms: float | None = None
    ai_provider: str | None = None
    ai_fallback_used: bool = False
    verified: bool = False
    verification_reason: str | None = None
    verification_replay: FailureReplaySummary = Field(default_factory=FailureReplaySummary)
    resolved_classification: str | None = None
    decision_summary: dict[str, object] = Field(default_factory=dict)
    code_diff: str = ""
    file_path: str | None = None
    source_sha256: str | None = None
    applied: bool = False
    execution_trace: list[AITraceEvent] = Field(default_factory=list)
