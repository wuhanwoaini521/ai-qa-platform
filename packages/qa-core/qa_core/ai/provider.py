from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class AICompletionRequest(BaseModel):
    prompt: str
    system_instruction: str = "You are a QA automation assistant."
    temperature: float = 0.2
    max_tokens: int = 1500


class AICompletionResponse(BaseModel):
    content: str
    tokens_used: int = 120
    model: str = "fake-qa-agent"


@runtime_checkable
class AIProvider(Protocol):
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse: ...


class FakeAIProvider(AIProvider):
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        if "explain" in request.prompt.lower():
            return AICompletionResponse(
                content="This test verifies the user interaction flow, navigating to target paths and asserting DOM elements with Playwright assertions.",
                tokens_used=100,
            )
        if "refactor" in request.prompt.lower():
            return AICompletionResponse(
                content="Recommendation: Extract inline selectors into a dedicated Page Object Model under `pages/` for enhanced reusability.",
                tokens_used=110,
            )
        return AICompletionResponse(
            content="QA Assistant analysis completed based on current workspace context and test specs.",
            tokens_used=90,
        )
