from __future__ import annotations

import os
from typing import Callable

from qa_core.ai.models import AIProviderType
from qa_core.ai.provider import (
    AIProvider,
    FakeAIProvider,
    FallbackAIProvider,
    OpenAICompatibleProvider,
)


class AIProviderRegistry:
    """Central registry and factory for pluggable AI providers."""

    _factories: dict[str, Callable[[], AIProvider]] = {}
    _instance: AIProvider | None = None

    @classmethod
    def register(cls, name: str, factory: Callable[[], AIProvider]) -> None:
        cls._factories[name.lower()] = factory

    @classmethod
    def get_provider(cls, name: str | None = None, api_key: str | None = None) -> AIProvider:
        provider_name = (name or os.getenv("QA_AI_PROVIDER", "fake")).lower()

        if provider_name in (AIProviderType.FAKE.value, "fake"):
            return FakeAIProvider()

        if provider_name in (AIProviderType.OPENAI_COMPATIBLE.value, "openai", "openai-compatible"):
            key = api_key or os.getenv("QA_AI_API_KEY", "")
            base_url = os.getenv("QA_AI_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("QA_AI_MODEL", "gpt-4o-mini")
            timeout = float(os.getenv("QA_AI_TIMEOUT", "30.0"))
            max_retries = int(os.getenv("QA_AI_MAX_RETRIES", "3"))

            primary = OpenAICompatibleProvider(
                api_key=key,
                base_url=base_url,
                model=model,
                timeout=timeout,
                max_retries=max_retries,
            )
            # Wrap in Fallback with Fake provider backup so platform runs never break
            return FallbackAIProvider(primary=primary, fallbacks=[FakeAIProvider()])

        if provider_name in cls._factories:
            return cls._factories[provider_name]()

        # Default fallback
        return FakeAIProvider()

    @classmethod
    def reset(cls) -> None:
        cls._factories.clear()
        cls._instance = None
