from __future__ import annotations

from qa_core.ai.budget import AIBudgetGuard, BudgetExceededError
from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    AIInvocationRecord,
    AIProviderType,
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
)
from qa_core.ai.registry import AIProviderRegistry

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
