from __future__ import annotations

from qa_core.ai.budget import AIBudgetGuard, BudgetExceededError
from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    AIInvocationRecord,
    AIProviderType,
    AIStreamChunk,
    CodeAssistantResponse,
    FailureAnalysisResponse,
    LocatorSemanticReview,
    ProviderHealth,
    ProviderHealthStatus,
    RequirementAnalysisResponse,
    TestCaseGenerationItem,
    TestCaseGenerationResponse,
    TestDesignGenerationResponse,
    TestDesignSuggestion,
)
from qa_core.ai.provider import (
    AIProvider,
    FakeAIProvider,
    FallbackAIProvider,
    OpenAICompatibleProvider,
    stream_provider_completion,
)
from qa_core.ai.registry import AIProviderRegistry
from qa_core.ai.trace import AITraceEvent, make_trace_event

__all__ = [
    "AIProvider",
    "FakeAIProvider",
    "OpenAICompatibleProvider",
    "FallbackAIProvider",
    "AIProviderRegistry",
    "AIProviderType",
    "ProviderHealth",
    "ProviderHealthStatus",
    "AICompletionRequest",
    "AICompletionResponse",
    "AIStreamChunk",
    "AITraceEvent",
    "make_trace_event",
    "stream_provider_completion",
    "AIInvocationRecord",
    "RequirementAnalysisResponse",
    "TestDesignSuggestion",
    "TestDesignGenerationResponse",
    "TestCaseGenerationItem",
    "TestCaseGenerationResponse",
    "FailureAnalysisResponse",
    "LocatorSemanticReview",
    "CodeAssistantResponse",
    "AIBudgetGuard",
    "BudgetExceededError",
]
