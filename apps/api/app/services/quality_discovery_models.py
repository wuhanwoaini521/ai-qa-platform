from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class DiscoveryMode(StrEnum):
    EXPLORE = "EXPLORE"
    VALIDATE = "VALIDATE"
    AUDIT = "AUDIT"


class DiscoveryStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class DiscoveryRunCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    start_url: str = Field(min_length=8, max_length=2048)
    mode: DiscoveryMode = DiscoveryMode.EXPLORE
    requirement_id: str | None = Field(default=None, max_length=36)
    requirement_text: str = Field(default="", max_length=20_000)
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Start URL must be a valid http(s) URL without embedded credentials.")
        if parts.query or parts.fragment:
            raise ValueError(
                "Start URL must not include query or fragment data; it may contain credentials or session tokens."
            )
        return value.strip()

    @field_validator("allowed_domains")
    @classmethod
    def normalize_allowed_domains(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            host = value.strip().lower().rstrip(".")
            if (
                not host
                or "/" in host
                or ":" in host
                or "@" in host
                or "?" in host
                or "#" in host
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
                or ("." not in host and host != "localhost")
            ):
                raise ValueError("Allowed domains must contain host names only.")
            normalized.append(host)
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_requirement_input(self):
        if self.requirement_id and self.requirement_text.strip():
            raise ValueError("Choose an existing Requirement or paste Requirement text, not both.")
        if self.mode in {DiscoveryMode.VALIDATE, DiscoveryMode.AUDIT} and not (
            self.requirement_id or self.requirement_text.strip()
        ):
            raise ValueError(f"{self.mode.value} mode requires a Requirement.")
        return self


class RequirementCheck(BaseModel):
    target: str = Field(min_length=1, max_length=160)
    attribute: Literal["enabled", "selected", "visible"]
    expected: bool
    when: Literal["always", "size_unselected", "size_selected", "after_action"] = "always"
    criterion: str = Field(default="", max_length=500)


class ExpectedState(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    condition: str = Field(default="", max_length=500)
    expected: str = Field(default="", max_length=500)


class ExpectedTransition(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)
    criterion: str = Field(default="", max_length=500)


class RequirementSignal(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    actors: list[str] = Field(default_factory=list, max_length=12)
    preconditions: list[str] = Field(default_factory=list, max_length=12)
    business_rules: list[str] = Field(default_factory=list, max_length=20)
    actions: list[str] = Field(default_factory=list, max_length=20)
    expected_behavior: str = Field(default="", max_length=1000)
    expected_states: list[ExpectedState] = Field(default_factory=list, max_length=16)
    expected_transitions: list[ExpectedTransition] = Field(default_factory=list, max_length=16)
    negative_states: list[str] = Field(default_factory=list, max_length=12)
    exceptions: list[str] = Field(default_factory=list, max_length=12)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    checks: list[RequirementCheck] = Field(default_factory=list, max_length=8)
    risk: str = Field(default="unknown", max_length=40)
    unknown: list[str] = Field(default_factory=list, max_length=12)
    ambiguous: bool = False


class RequirementAnalysisItem(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    expected_behavior: str = Field(default="", max_length=1000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    checks: list[RequirementCheck] = Field(default_factory=list, max_length=8)
    risk: str = Field(default="unknown", max_length=40)
    ambiguous: bool = False


class RequirementAnalysis(BaseModel):
    requirements: list[RequirementAnalysisItem] = Field(default_factory=list, max_length=4)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)


class FeatureSignal(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    target_id: str | None = Field(default=None, max_length=32)
    evidence_text: str = Field(default="", max_length=240)
    confidence: float = Field(default=0.5, ge=0, le=1)


class DiscoveryGoal(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    feature: str = Field(default="", max_length=160)
    requirement_id: str | None = Field(default=None, max_length=80)
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    rationale: str = Field(default="", max_length=300)


class DiscoveryPlan(BaseModel):
    page_type: str = Field(default="unknown", max_length=80)
    features: list[FeatureSignal] = Field(default_factory=list, max_length=20)
    goals: list[DiscoveryGoal] = Field(default_factory=list, max_length=20)
    candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    done: bool = False
    reason_summary: str = Field(default="", max_length=300)


class DiscoveryBlocked(RuntimeError):
    pass
