"""Bounded QA documents carried by existing requirements, designs and test cases.

The knowledge graph is a projection of these references and existing relational entities;
these documents do not constitute a second entity store.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcceptanceCriterion(DocumentModel):
    id: str = Field(pattern=r"^AC-[A-Za-z0-9-]+$", max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    negative_required: bool = False


class BusinessRule(DocumentModel):
    id: str = Field(pattern=r"^BR-[A-Za-z0-9-]+$", max_length=64)
    description: str = Field(min_length=1, max_length=1000)
    criterion_ids: list[str] = Field(default_factory=list, max_length=30)


class BusinessFlowStep(DocumentModel):
    id: str = Field(pattern=r"^FLOW-[A-Za-z0-9-]+$", max_length=64)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=500)
    next_ids: list[str] = Field(default_factory=list, max_length=12)
    criterion_ids: list[str] = Field(default_factory=list, max_length=30)


class RequirementRisk(DocumentModel):
    id: str = Field(pattern=r"^RISK-[A-Za-z0-9-]+$", max_length=64)
    title: str = Field(min_length=1, max_length=160)
    severity: Literal["High", "Medium", "Low"]
    probability: Literal["High", "Medium", "Low"] = "Medium"
    impact: str = Field(max_length=1000)
    criterion_ids: list[str] = Field(default_factory=list, max_length=30)
    suggested_coverage: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(default="", max_length=1000)


class RequirementAmbiguity(DocumentModel):
    id: str = Field(max_length=64)
    question: str = Field(min_length=1, max_length=1000)
    impact: str = Field(default="", max_length=500)


class ExpectedApplicationState(DocumentModel):
    name: str = Field(min_length=1, max_length=120)
    condition: str = Field(default="", max_length=500)
    expected: str = Field(default="", max_length=500)


class ExpectedApplicationTransition(DocumentModel):
    source: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)
    criterion: str = Field(default="", max_length=500)


class RequirementFeatureExpectation(DocumentModel):
    id: str = Field(max_length=80)
    source_id: str = Field(max_length=80)
    feature: str = Field(min_length=1, max_length=200)
    actors: list[str] = Field(default_factory=list, max_length=12)
    preconditions: list[str] = Field(default_factory=list, max_length=12)
    business_rules: list[str] = Field(default_factory=list, max_length=20)
    actions: list[str] = Field(default_factory=list, max_length=20)
    expected_behavior: str = Field(default="", max_length=1000)
    expected_states: list[ExpectedApplicationState] = Field(default_factory=list, max_length=16)
    expected_transitions: list[ExpectedApplicationTransition] = Field(default_factory=list, max_length=16)
    negative_states: list[str] = Field(default_factory=list, max_length=12)
    exceptions: list[str] = Field(default_factory=list, max_length=12)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=12)
    risk: str = Field(default="unknown", max_length=40)
    unknown: list[str] = Field(default_factory=list, max_length=12)
    ambiguous: bool = False


class StructuredRequirementModel(DocumentModel):
    source_id: str = Field(max_length=80)
    features: list[RequirementFeatureExpectation] = Field(default_factory=list, max_length=40)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)


class CoverageReferences(DocumentModel):
    criterion_ids: list[str] = Field(default_factory=list, max_length=30)
    rule_ids: list[str] = Field(default_factory=list, max_length=30)
    risk_ids: list[str] = Field(default_factory=list, max_length=30)
    flow_ids: list[str] = Field(default_factory=list, max_length=30)


class TestScenario(DocumentModel):
    id: str = Field(pattern=r"^SCN-[A-Za-z0-9-]+$", max_length=64)
    title: str = Field(min_length=1, max_length=200)
    intent: str = Field(min_length=1, max_length=1500)
    path_type: Literal["normal", "alternative", "negative"] = "normal"
    technique: Literal[
        "happy_path",
        "negative",
        "boundary",
        "equivalence",
        "decision_table",
        "state_transition",
        "pairwise",
        "risk_based",
        "error_guessing",
    ] = "happy_path"
    domain: Literal["UI", "API", "Python", "Domain"] = "UI"
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    coverage: CoverageReferences = Field(default_factory=CoverageReferences)
    actions: list[str] = Field(default_factory=list, max_length=30)
    expected_outcomes: list[str] = Field(default_factory=list, max_length=20)
    rationale: str = Field(default="", max_length=1000)


class AnalysisStage(DocumentModel):
    id: str
    title: str
    status: Literal["pending", "running", "passed", "failed", "skipped"]
    summary: str = Field(default="", max_length=1500)
    duration_ms: float = 0
    source: str = "deterministic"
    at: str = ""


class AnalysisRecord(DocumentModel):
    id: str
    status: Literal["REFERENCE", "RUNNING", "SUCCESS", "FAILED", "FALLBACK"]
    started_at: str
    finished_at: str | None = None
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    input_hash: str = ""
    error_code: str | None = None
    error: str | None = None
    stages: list[AnalysisStage] = Field(default_factory=list, max_length=12)
    decisions: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    analysis_snapshot: RequirementAnalysis | None = None


class RequirementAnalysis(DocumentModel):
    summary: str = Field(min_length=1, max_length=2000)
    business_flow: list[BusinessFlowStep] = Field(max_length=24)
    actors: list[str] = Field(default_factory=list, max_length=20)
    entities: list[str] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    ambiguities: list[RequirementAmbiguity] = Field(default_factory=list, max_length=20)
    risks: list[RequirementRisk] = Field(min_length=1, max_length=20)
    scenarios: list[TestScenario] = Field(min_length=1, max_length=24)
    coverage_gaps: list[str] = Field(default_factory=list, max_length=30)


class RequirementDocument(DocumentModel):
    display_id: str = Field(default="", max_length=64)
    criteria: list[AcceptanceCriterion] = Field(default_factory=list, max_length=30)
    rules: list[BusinessRule] = Field(default_factory=list, max_length=30)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    analysis: RequirementAnalysis | None = None
    history: list[AnalysisRecord] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_references(self):
        groups = [self.criteria, self.rules]
        if self.analysis:
            groups += [self.analysis.business_flow, self.analysis.risks, self.analysis.scenarios]
        for group in groups:
            ids = [item.id for item in group]
            if len(ids) != len(set(ids)):
                raise ValueError("Document entity IDs must be unique within their kind")
        criteria = {item.id for item in self.criteria}
        for item in self.rules:
            if not set(item.criterion_ids) <= criteria:
                raise ValueError("Business rule refers to an unknown acceptance criterion")
        if self.analysis:
            flow_ids = {item.id for item in self.analysis.business_flow}
            for step in self.analysis.business_flow:
                if not set(step.next_ids) <= flow_ids or not set(step.criterion_ids) <= criteria:
                    raise ValueError("Business flow refers to an unknown node or criterion")
            for risk in self.analysis.risks:
                if not set(risk.criterion_ids) <= criteria:
                    raise ValueError("Risk refers to an unknown acceptance criterion")
            for scenario in self.analysis.scenarios:
                self.validate_coverage(scenario.coverage)
        return self

    def validate_coverage(self, coverage: CoverageReferences):
        known = {
            "criterion_ids": {item.id for item in self.criteria},
            "rule_ids": {item.id for item in self.rules},
            "risk_ids": {item.id for item in self.analysis.risks} if self.analysis else set(),
            "flow_ids": {item.id for item in self.analysis.business_flow} if self.analysis else set(),
        }
        for key, refs in coverage.model_dump().items():
            if not set(refs) <= known[key]:
                raise ValueError(f"Unknown {key} in coverage references")


class TestOracle(DocumentModel):
    kind: Literal["UI", "Domain", "Data", "API", "Python", "Network"]
    description: str = Field(min_length=1, max_length=1000)
    criterion_ids: list[str] = Field(default_factory=list, max_length=30)


class ModernTestModel(DocumentModel):
    display_id: str = Field(default="", max_length=64)
    intent: str = Field(min_length=1, max_length=1500)
    scenario_id: str | None = None
    coverage: CoverageReferences = Field(default_factory=CoverageReferences)
    path_type: Literal["normal", "alternative", "negative"] = "normal"
    technique: str = Field(default="happy_path", max_length=50)
    data: dict[str, Any] = Field(default_factory=dict)
    oracles: list[TestOracle] = Field(default_factory=list, max_length=20)
    evidence: list[Literal["Screenshot", "DOM", "Network", "Trace", "Logs"]] = Field(default_factory=list, max_length=5)
    missing: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded_data(self):
        import json

        if len(json.dumps(self.data, ensure_ascii=False)) > 6000:
            raise ValueError("Test data context exceeds 6000 characters")
        return self


class CoverageMetric(DocumentModel):
    key: str
    label: str
    covered: int
    total: int
    percentage: float | None
    items: list[dict[str, Any]] = Field(default_factory=list)


class KnowledgeNode(DocumentModel):
    id: str
    kind: str
    label: str
    summary: str = ""
    href: str = ""
    status: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdge(DocumentModel):
    source: str
    target: str
    relation: str


class ProjectKnowledge(DocumentModel):
    project_id: str
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    coverage: list[CoverageMetric]
    gaps: list[dict[str, Any]]
    counts: dict[str, int]
    truncated: bool = False
