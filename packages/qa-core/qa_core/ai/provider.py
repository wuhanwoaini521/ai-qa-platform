from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Protocol, runtime_checkable

import httpx

from qa_core.ai.models import (
    AICompletionRequest,
    AICompletionResponse,
    CodeAssistantResponse,
    FailureAnalysisResponse,
    LocatorSemanticReview,
    ProviderHealth,
    ProviderHealthStatus,
    RequirementAnalysisResponse,
    TestCaseGenerationResponse,
    TestDesignGenerationResponse,
)
from qa_core.failure.redactor import SensitiveRedactor

logger = logging.getLogger("qa_core.ai")


def clean_json_text(text: str) -> str:
    """Strip markdown code block fences if present in JSON completion."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


@runtime_checkable
class AIProvider(Protocol):
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse: ...
    async def check_health(self) -> ProviderHealthStatus: ...


class FakeAIProvider:
    """Deterministic Fake AI Provider for testing and offline development."""

    def __init__(self, model: str = "fake-qa-model") -> None:
        self.model = model
        self.provider_name = "fake"

    async def check_health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            provider=self.provider_name,
            status=ProviderHealth.AVAILABLE,
            message="Fake AI Provider is active and available.",
            model=self.model,
        )

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        start = time.perf_counter()
        prompt_id = request.prompt_id or ""
        p_lower = request.prompt.lower()

        structured: dict[str, Any] | None = None
        content = ""

        if prompt_id == "requirement_analysis" or "analyze the following software requirement" in p_lower:
            data = RequirementAnalysisResponse(
                summary="Requirement specifies core user flows with validation requirements and distinct state transitions.",
                risks=[
                    "Missing error handling specification for edge input values",
                    "Asynchronous state latency risks",
                ],
                ambiguities=[
                    "Session timeout threshold is undefined",
                    "Specific HTTP error codes for boundary conditions unlisted",
                ],
                suggested_test_dimensions=["FUNCTIONAL", "BOUNDARY", "NEGATIVE", "API", "UI"],
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        elif prompt_id == "test_design" or "generate structured test design proposals" in p_lower:
            data = TestDesignGenerationResponse(
                suggestions=[
                    {
                        "title": "Positive Core Path Verification",
                        "category": "FUNCTIONAL",
                        "description": "Verify standard end-to-end user navigation and data submission.",
                        "risk": "Low",
                    },
                    {
                        "title": "Boundary Input Length & Character Set Limits",
                        "category": "BOUNDARY",
                        "description": "Test field length boundaries and multi-byte UTF-8 string injections.",
                        "risk": "Medium",
                    },
                    {
                        "title": "Negative Authentication & Access Violation",
                        "category": "NEGATIVE",
                        "description": "Validate error alerts when unauthenticated or malformed tokens are supplied.",
                        "risk": "High",
                    },
                    {
                        "title": "API Contract and Schema Validation",
                        "category": "API",
                        "description": "Verify response status codes, payload structures, and response time SLAs.",
                        "risk": "Medium",
                    },
                ]
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        elif prompt_id == "test_case_generation" or "generate comprehensive test cases" in p_lower:
            data = TestCaseGenerationResponse(
                test_cases=[
                    {
                        "title": "Verify Successful User Flow Completion",
                        "preconditions": "User is authenticated and target page is rendered.",
                        "steps": [
                            "Navigate to target page",
                            "Enter valid test payload",
                            "Click submit button",
                            "Verify success notification",
                        ],
                        "expected_result": "Success message is displayed and database record is persisted.",
                        "priority": "P0",
                        "tags": ["smoke", "regression", "core"],
                    },
                    {
                        "title": "Verify Invalid Input Error Handling",
                        "preconditions": "User is on test form view.",
                        "steps": ["Enter empty or malformed input", "Click submit button"],
                        "expected_result": "Inline validation message appears and submission is blocked.",
                        "priority": "P1",
                        "tags": ["negative", "validation"],
                    },
                ]
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        elif prompt_id == "failure_diagnosis" or "diagnose the following test failure" in p_lower:
            data = FailureAnalysisResponse(
                classification="LOCATOR_CHANGED" if "locator" in p_lower else "TIMING_ISSUE",
                root_cause="Target element locator could not be resolved in the DOM during interaction step.",
                evidence=[
                    "Locator search failed after timeout",
                    "DOM element matching selector was absent in snapshot",
                ],
                hypotheses=[
                    "UI component rendered with updated data-testid",
                    "Element dynamic rendering was delayed by network request",
                ],
                recommended_actions=[
                    "Update selector to resilient data-testid",
                    "Add explicit state assertion before interaction",
                ],
                confidence=0.92,
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        elif prompt_id == "locator_review" or "semantic equivalence review" in p_lower:
            data = LocatorSemanticReview(
                is_semantically_equivalent=True,
                confidence=0.88,
                explanation="Proposed selector targets the exact same interactive button within the component subtree.",
                risk_warning=None,
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        elif prompt_id == "code_assistant" or "qa assistant request" in p_lower:
            data = CodeAssistantResponse(
                reply="Analyzed test structure: recommend modularizing page interactions using Page Object Model conventions.",
                suggested_code=None,
                target_file=None,
                action_type="reply",
                suggestions=["Extract selectors to pages/", "Wrap assertions in expect() statements"],
            )
            structured = data.model_dump()
            content = json.dumps(structured, indent=2)

        else:
            content = "QA Assistant analysis completed based on workspace knowledge and test requirements."

        duration = (time.perf_counter() - start) * 1000.0
        return AICompletionResponse(
            content=content,
            structured_data=structured,
            input_tokens=150,
            output_tokens=220,
            model=self.model,
            provider=self.provider_name,
            duration_ms=duration,
            fallback_used=False,
            retry_count=0,
            prompt_version=request.prompt_version,
        )


class OpenAICompatibleProvider:
    """Production OpenAI-compatible Provider connecting to OpenAI or Gateway."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.provider_name = "openai-compatible"

    async def check_health(self) -> ProviderHealthStatus:
        if not self.api_key:
            return ProviderHealthStatus(
                provider=self.provider_name,
                status=ProviderHealth.DISABLED,
                message="AI API Key is not configured in environment.",
                model=self.model,
                base_url=self.base_url,
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if res.status_code == 200:
                    return ProviderHealthStatus(
                        provider=self.provider_name,
                        status=ProviderHealth.AVAILABLE,
                        message="Provider connection healthy.",
                        model=self.model,
                        base_url=self.base_url,
                    )
                elif res.status_code in (401, 403):
                    return ProviderHealthStatus(
                        provider=self.provider_name,
                        status=ProviderHealth.AUTH_ERROR,
                        message="Authentication failed: invalid or unauthorized API key.",
                        model=self.model,
                        base_url=self.base_url,
                    )
                elif res.status_code == 429:
                    return ProviderHealthStatus(
                        provider=self.provider_name,
                        status=ProviderHealth.RATE_LIMITED,
                        message="API rate limit exceeded.",
                        model=self.model,
                        base_url=self.base_url,
                    )
                else:
                    return ProviderHealthStatus(
                        provider=self.provider_name,
                        status=ProviderHealth.UNAVAILABLE,
                        message=f"Gateway returned status {res.status_code}.",
                        model=self.model,
                        base_url=self.base_url,
                    )
        except httpx.TimeoutException:
            return ProviderHealthStatus(
                provider=self.provider_name,
                status=ProviderHealth.TIMEOUT,
                message="Health check timed out.",
                model=self.model,
                base_url=self.base_url,
            )
        except Exception as e:
            redacted = SensitiveRedactor.redact_text(str(e))
            return ProviderHealthStatus(
                provider=self.provider_name,
                status=ProviderHealth.UNAVAILABLE,
                message=f"Connection error: {redacted}",
                model=self.model,
                base_url=self.base_url,
            )

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        if not self.api_key:
            raise RuntimeError("Cannot execute completion: API key is not configured.")

        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        retry_count = 0
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                    # 401, 403, 400: Never retry
                    if resp.status_code in (401, 403, 400):
                        err_text = SensitiveRedactor.redact_text(resp.text)
                        raise ValueError(f"OpenAI API error {resp.status_code}: {err_text}")

                    # 429, 5xx: Retry with bounded exponential backoff
                    if resp.status_code in (429, 500, 502, 503, 504):
                        if attempt < self.max_retries:
                            retry_count += 1
                            backoff = min(1.0 * (2**attempt), 8.0)
                            logger.warning(
                                "OpenAI status %d, retrying in %.2fs (attempt %d/%d)",
                                resp.status_code,
                                backoff,
                                attempt + 1,
                                self.max_retries,
                            )
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            resp.raise_for_status()

                    resp.raise_for_status()
                    data = resp.json()

                    raw_content = data["choices"][0]["message"]["content"] or ""
                    usage = data.get("usage", {})
                    input_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")

                    # Attempt structured parse if schema was requested
                    structured: dict[str, Any] | None = None
                    cleaned = clean_json_text(raw_content)
                    try:
                        structured = json.loads(cleaned)
                    except Exception:
                        structured = None

                    duration = (time.perf_counter() - start) * 1000.0
                    return AICompletionResponse(
                        content=raw_content,
                        structured_data=structured,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        model=self.model,
                        provider=self.provider_name,
                        duration_ms=duration,
                        fallback_used=False,
                        retry_count=retry_count,
                        prompt_version=request.prompt_version,
                    )

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    retry_count += 1
                    backoff = min(1.0 * (2**attempt), 8.0)
                    logger.warning(
                        "Network/Timeout error: %s, retrying in %.2fs",
                        SensitiveRedactor.redact_text(str(e)),
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    break
            except Exception as e:
                last_exception = e
                break

        duration = (time.perf_counter() - start) * 1000.0
        if isinstance(last_exception, ValueError):
            raise last_exception
        redacted_err = SensitiveRedactor.redact_text(str(last_exception))
        raise RuntimeError(f"OpenAI completion failed after {retry_count} retries: {redacted_err}")


class FallbackAIProvider:
    """Chains primary provider with secondary and fallback providers (Gate 5.8)."""

    def __init__(self, primary: AIProvider, fallbacks: list[AIProvider] | None = None) -> None:
        self.primary = primary
        self.fallbacks = fallbacks or [FakeAIProvider()]

    async def check_health(self) -> ProviderHealthStatus:
        primary_health = await self.primary.check_health()
        if primary_health.status == ProviderHealth.AVAILABLE:
            return primary_health
        for fb in self.fallbacks:
            fb_health = await fb.check_health()
            if fb_health.status == ProviderHealth.AVAILABLE:
                return ProviderHealthStatus(
                    provider=f"{primary_health.provider} (fallback to {fb_health.provider})",
                    status=ProviderHealth.AVAILABLE,
                    message=f"Primary provider is {primary_health.status.value}; fallback active.",
                    model=fb_health.model,
                )
        return primary_health

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        try:
            return await self.primary.complete(request)
        except Exception as e:
            logger.warning(
                "Primary AI provider failed: %s. Engaging fallback chain.",
                SensitiveRedactor.redact_text(str(e)),
            )
            for fb in self.fallbacks:
                try:
                    res = await fb.complete(request)
                    res.fallback_used = True
                    return res
                except Exception as fb_err:
                    logger.warning(
                        "Fallback provider failed: %s",
                        SensitiveRedactor.redact_text(str(fb_err)),
                    )
            # If all fallbacks fail, return safe empty response without crashing test execution
            return AICompletionResponse(
                content="AI Analysis Unavailable (Provider unreachable).",
                structured_data=None,
                input_tokens=None,
                output_tokens=None,
                model="unavailable",
                provider="disabled",
                duration_ms=0.0,
                fallback_used=True,
                retry_count=0,
                prompt_version=request.prompt_version,
            )
