from __future__ import annotations

import os
from typing import Callable, Mapping

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
    _runtime_config: dict[str, str] | None = None
    _middleware: Callable[[AIProvider], AIProvider] | None = None

    @classmethod
    def set_middleware(cls, middleware: Callable[[AIProvider], AIProvider] | None) -> None:
        """Install application governance without coupling qa-core to persistence."""
        cls._middleware = middleware

    @classmethod
    def register(cls, name: str, factory: Callable[[], AIProvider]) -> None:
        cls._factories[name.lower()] = factory

    @classmethod
    def configure_runtime(cls, config: Mapping[str, str] | None) -> None:
        """Set an API-managed provider configuration without changing environment fallbacks."""
        cls._runtime_config = dict(config) if config is not None else None

    @classmethod
    def get_provider(cls, name: str | None = None, api_key: str | None = None) -> AIProvider:
        provider = cls._build_provider(name, api_key)
        return cls._middleware(provider) if cls._middleware else provider

    @classmethod
    def _build_provider(cls, name: str | None = None, api_key: str | None = None) -> AIProvider:
        config = cls._runtime_config or {
            "provider": os.getenv("QA_AI_PROVIDER", "fake"),
            "api_key": os.getenv("QA_AI_API_KEY", ""),
            "base_url": os.getenv("QA_AI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("QA_AI_MODEL", "gpt-4o-mini"),
            "timeout": os.getenv("QA_AI_TIMEOUT", "30.0"),
            "max_retries": os.getenv("QA_AI_MAX_RETRIES", "3"),
        }
        provider_name = (name or config.get("provider", "fake")).lower()

        if provider_name in (AIProviderType.FAKE.value, "fake"):
            return FakeAIProvider()

        if provider_name in (AIProviderType.OPENAI_COMPATIBLE.value, "openai", "openai-compatible"):
            key = api_key if api_key is not None else config.get("api_key", "")
            base_url = config.get("base_url", "https://api.openai.com/v1")
            model = config.get("model", "gpt-4o-mini")
            timeout = float(config.get("timeout", "30.0"))
            max_retries = int(config.get("max_retries", "3"))

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

        raise ValueError(f"Unsupported AI provider: {provider_name}")

    @classmethod
    def reset(cls) -> None:
        cls._factories.clear()
        cls._runtime_config = None
        cls._middleware = None
