from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from qa_core.ai.trace import AITraceEvent


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
    FALLBACK_ONLY = "FALLBACK_ONLY"
    DISABLED = "DISABLED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


class AIProviderType(str, Enum):
    FAKE = "fake"
    OPENAI_COMPATIBLE = "openai-compatible"
    CUSTOM = "custom"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AICompletionRequest(BaseModel):
    request_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    prompt: str = Field(max_length=128000)
    system_instruction: str = "You are a QA automation assistant."
    temperature: float = 0.2
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    response_schema: type[BaseModel] | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None
    # One completion request is one conversation by default. Callers that make
    # multiple related completions can pass the same ID to keep OpenCode routing stable.
    session_id: str = Field(default_factory=lambda: uuid4().hex)


class AICompletionResponse(BaseModel):
    invocation_id: str | None = None
    content: str
    structured_data: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str = "fake-qa-agent"
    provider: str = "fake"
    duration_ms: float = 0.0
    fallback_used: bool = False
    retry_count: int = 0
    prompt_version: str | None = None


class AIStreamChunk(BaseModel):
    """One provider-neutral piece of a streamed completion."""

    content_delta: str = ""
    invocation_id: str | None = None
    usage: dict[str, int | float | None] | None = None
    finish_reason: str | None = None
    provider: str = "unknown"
    model: str = ""
    fallback_used: bool = False


class ProviderHealthStatus(BaseModel):
    provider: str
    status: ProviderHealth
    message: str = ""
    model: str = ""
    base_url: str | None = None


# --- Structured Output Schemas (Gate 5.5 & Gate 5.6) ---


class RequirementAnalysisResponse(BaseModel):
    summary: str
    risks: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    suggested_test_dimensions: list[str] = Field(default_factory=list)


class TestDesignSuggestion(BaseModel):
    title: str
    category: str = "FUNCTIONAL"
    description: str = ""
    risk: str = "Medium"


class TestDesignGenerationResponse(BaseModel):
    suggestions: list[TestDesignSuggestion] = Field(default_factory=list)


class TestCaseGenerationItem(BaseModel):
    title: str
    preconditions: str = ""
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""
    priority: str = "P1"
    tags: list[str] = Field(default_factory=list)


class TestCaseGenerationResponse(BaseModel):
    test_cases: list[TestCaseGenerationItem] = Field(default_factory=list)


class TestAuthorResponse(BaseModel):
    suggested_file_path: str
    generated_code: str
    explanation: str = ""
    test_specification: dict[str, Any] = Field(default_factory=dict)


class FailureAnalysisResponse(BaseModel):
    classification: str = "UNKNOWN"
    root_cause: str = ""
    evidence: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    provider: str = ""
    fallback_used: bool = False
    duration_ms: float | None = None
    execution_trace: list[AITraceEvent] = Field(default_factory=list)


class LocatorSemanticReview(BaseModel):
    is_semantically_equivalent: bool
    confidence: float = Field(default=0.85, ge=0, le=1)
    explanation: str = ""
    risk_warning: str | None = None


class CodeAssistantResponse(BaseModel):
    reply: str
    suggested_code: str | None = None
    target_file: str | None = None
    action_type: str = "reply"
    suggestions: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    fallback_used: bool = False


class BrowserActionCandidate(BaseModel):
    """One proposed action tied to a control in the current browser observation."""

    candidate_id: str = Field(min_length=1, max_length=48, pattern=r"^[a-zA-Z0-9_-]+$")
    action_type: Literal[
        "navigate",
        "click",
        "fill",
        "select",
        "scroll",
        "hover",
        "wait",
        "inspect",
        "back",
        "open_product",
        "filter",
        "choose_variant",
        "add_to_cart",
    ]
    target_id: str | None = Field(default=None, max_length=32)
    target: str = Field(default="", max_length=200)
    locator_strategy: (
        Literal["role", "test_id", "label", "placeholder", "id", "name", "text", "href", "page"] | None
    ) = None
    locator: dict[str, Any] | None = None
    value: str | None = Field(default=None, max_length=500)
    reason_summary: str = Field(default="", max_length=400)
    expected_effect: str = Field(default="", max_length=400)
    risk: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    evidence: list[str] = Field(default_factory=list, max_length=8)


class BrowserAgentPlan(BaseModel):
    """Bounded AI proposal; execution still validates every target and effect."""

    subgoals: list[str] = Field(default_factory=list, max_length=12)
    current_subgoal_index: int = Field(default=0, ge=0, le=11)
    current_subgoal: str = Field(default="", max_length=300)
    candidates: list[BrowserActionCandidate] = Field(default_factory=list, max_length=5)
    preferred_candidate_id: str | None = Field(default=None, max_length=48)
    goal_status: Literal["in_progress", "completed", "blocked"] = "in_progress"
    completion_evidence: list[str] = Field(default_factory=list, max_length=8)


class AIInvocationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    task: str
    provider: str
    model: str
    started_at: datetime = Field(default_factory=utc_now)
    duration_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    fallback_used: bool = False
    status: str = "SUCCESS"
    error_type: str | None = None
    prompt_version: str | None = None
