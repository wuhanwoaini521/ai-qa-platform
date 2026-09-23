from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
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
    prompt: str
    system_instruction: str = "You are a QA automation assistant."
    temperature: float = 0.2
    max_tokens: int = 2000
    response_schema: type[BaseModel] | None = None
    prompt_id: str | None = None
    prompt_version: str | None = None


class AICompletionResponse(BaseModel):
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
    confidence: float = 0.8


class LocatorSemanticReview(BaseModel):
    is_semantically_equivalent: bool
    confidence: float = 0.85
    explanation: str = ""
    risk_warning: str | None = None


class CodeAssistantResponse(BaseModel):
    reply: str
    suggested_code: str | None = None
    target_file: str | None = None
    action_type: str = "reply"
    suggestions: list[str] = Field(default_factory=list)


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
