from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel
from qa_core.ai.budget import AIBudgetGuard, BudgetExceededError
from qa_core.ai.models import (
    LONG_GENERATION_TIMEOUT_SECONDS,
    AICompletionRequest,
    ProviderHealth,
)
from qa_core.ai.provider import (
    FakeAIProvider,
    FallbackAIProvider,
    OpenAICompatibleProvider,
)
from qa_core.author.models import AuthoringRequest
from qa_core.orchestrator.orchestrator import ProductionQAOrchestrator


@pytest.mark.asyncio
async def test_fake_ai_provider_tasks():
    provider = FakeAIProvider()

    # Health check
    health = await provider.check_health()
    assert health.status == ProviderHealth.FALLBACK_ONLY

    # Requirement analysis
    req_res = await provider.complete(
        AICompletionRequest(
            prompt="analyze the following software requirement: Cart Checkout", prompt_id="requirement_analysis"
        )
    )
    assert req_res.structured_data is not None
    assert "summary" in req_res.structured_data
    assert len(req_res.structured_data["suggested_test_dimensions"]) > 0

    # Test design
    design_res = await provider.complete(
        AICompletionRequest(prompt="generate structured test design proposals", prompt_id="test_design")
    )
    assert design_res.structured_data is not None
    assert len(design_res.structured_data["suggestions"]) > 0

    # Test case generation
    case_res = await provider.complete(
        AICompletionRequest(prompt="generate comprehensive test cases", prompt_id="test_case_generation")
    )
    assert case_res.structured_data is not None
    assert len(case_res.structured_data["test_cases"]) > 0

    # Failure diagnosis
    diag_res = await provider.complete(
        AICompletionRequest(
            prompt="diagnose the following test failure: Locator not found", prompt_id="failure_diagnosis"
        )
    )
    assert diag_res.structured_data is not None
    assert diag_res.structured_data["classification"] == "LOCATOR_CHANGED"
    assert len(diag_res.structured_data["evidence"]) > 0

    # Locator review
    review_res = await provider.complete(
        AICompletionRequest(prompt="semantic equivalence review", prompt_id="locator_review")
    )
    assert review_res.structured_data is not None
    assert review_res.structured_data["is_semantically_equivalent"] is False
    assert review_res.structured_data["confidence"] == 0


@pytest.mark.asyncio
async def test_budget_guard():
    guard = AIBudgetGuard(max_requests=2, max_input_tokens=500, max_output_tokens=300)
    assert guard.is_within_budget()

    guard.check_and_record_request()
    guard.record_tokens(input_tokens=100, output_tokens=50)
    assert guard.is_within_budget()

    guard.check_and_record_request()
    assert guard.requests_count == 2

    with pytest.raises(BudgetExceededError, match="request budget exceeded"):
        guard.check_and_record_request()

    guard2 = AIBudgetGuard(max_requests=10, max_input_tokens=100, max_output_tokens=50)
    with pytest.raises(BudgetExceededError, match="input token budget exceeded"):
        guard2.record_tokens(input_tokens=150, output_tokens=10)


@pytest.mark.asyncio
async def test_fallback_ai_provider():
    # Primary provider that fails
    class ErrorProvider:
        async def check_health(self):
            return FakeAIProvider().check_health()

        async def complete(self, request: AICompletionRequest):
            raise RuntimeError("API Connection Refused")

    primary = ErrorProvider()
    fallback = FakeAIProvider()
    chained = FallbackAIProvider(primary=primary, fallbacks=[fallback])

    res = await chained.complete(AICompletionRequest(prompt="Explain test"))
    assert res.fallback_used is True
    assert len(res.content) > 0


@pytest.mark.asyncio
async def test_openai_provider_mock_transport(monkeypatch):
    # Mock httpx responses
    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"summary": "All good", "risks": [], "ambiguities": [], "suggested_test_dimensions": ["FUNCTIONAL"]}'
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 30},
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_transport_handler)

    # Patch httpx.AsyncClient to use our mock transport
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: orig_client(transport=transport))

    provider = OpenAICompatibleProvider(api_key="sk-test-mock-key-12345", base_url="https://mock-ai.local/v1")
    health = await provider.check_health()
    assert health.status == ProviderHealth.AVAILABLE

    res = await provider.complete(
        AICompletionRequest(
            prompt="Analyze requirement",
            prompt_id="requirement_analysis",
        )
    )
    assert res.provider == "openai-compatible"
    assert res.structured_data is not None
    assert res.input_tokens == 50
    assert res.output_tokens == 30


@pytest.mark.asyncio
async def test_openai_provider_requests_json_mode_and_retries_invalid_schema(monkeypatch):
    class Summary(BaseModel):
        summary: str

    bodies = []

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        content = "QA Assistant analysis completed" if len(bodies) == 1 else '{"summary":"Grounded finding"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    transport = httpx.MockTransport(mock_transport_handler)
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: orig_client(transport=transport))

    provider = OpenAICompatibleProvider(api_key="sk-test-mock-key-12345", base_url="https://mock-ai.local/v1")
    response = await provider.complete(
        AICompletionRequest(prompt="Analyze requirement", response_schema=Summary, thinking_mode="disabled")
    )

    assert response.structured_data == {"summary": "Grounded finding"}
    assert response.retry_count == 1
    assert len(bodies) == 2
    assert all(body["response_format"] == {"type": "json_object"} for body in bodies)
    assert all(body["thinking"] == {"type": "disabled"} for body in bodies)
    assert "previous response did not match" in bodies[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_openai_provider_auth_error(monkeypatch):
    def mock_auth_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key provided"}})

    transport = httpx.MockTransport(mock_auth_error_handler)
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: orig_client(transport=transport))

    provider = OpenAICompatibleProvider(api_key="sk-invalid-key", base_url="https://mock-ai.local/v1")
    health = await provider.check_health()
    assert health.status == ProviderHealth.AUTH_ERROR

    with pytest.raises(ValueError, match="OpenAI API error 401"):
        await provider.complete(AICompletionRequest(prompt="Test auth fail"))


@pytest.mark.asyncio
async def test_orchestrator_production_capabilities():
    orchestrator = ProductionQAOrchestrator(ai_provider=FakeAIProvider())

    # Requirement analysis
    analysis = await orchestrator.analyze_requirement(
        title="Checkout Payment Processing",
        description="Users pay with credit card or PayPal",
        acceptance_criteria="Payment confirmation is shown",
    )
    assert len(analysis.suggested_test_dimensions) > 0

    # Test design generation
    designs = await orchestrator.generate_test_designs(
        title="Checkout Payment Processing",
        description="Users pay with credit card",
    )
    assert len(designs.suggestions) > 0

    # Test case generation
    cases = await orchestrator.generate_test_cases(
        requirement_title="Checkout Payment",
        design_title="Positive Credit Card Verification",
    )
    assert len(cases.test_cases) > 0

    # Test authoring with AST verification
    author_res = orchestrator.author_test(
        AuthoringRequest(
            requirement_title="Cart Add Flow",
            requirement_description="Add item to cart and verify cart counter",
            acceptance_criteria=["Item count updates to 1"],
        )
    )
    assert "test_cart_add_flow" in author_res.generated_code
    assert author_res.suggested_file_path.endswith(".py")

    # Failure diagnosis AI
    fail_res = await orchestrator.diagnose_failure_ai(
        error_message="TimeoutError: Locator('button#checkout') not found",
        stack_trace="File tests/test_checkout.py, line 20",
        test_nodeid="tests/test_checkout.py::test_checkout_flow",
    )
    assert fail_res.classification == "LOCATOR_CHANGED"
    assert len(fail_res.evidence) > 0
    assert len(fail_res.hypotheses) > 0

    # Locator semantic review
    review = await orchestrator.review_locator_candidate(
        old_locator="button#submit-payment",
        proposed_locator='[data-testid="pay-now-btn"]',
        strategy="data-testid",
    )
    assert review.is_semantically_equivalent is False
    assert review.confidence == 0


@pytest.mark.asyncio
async def test_a_generation_call_may_outlast_the_default_attempt_timeout(monkeypatch):
    """A 30s attempt cap timed every real test-case generation attempt out into a 502."""
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    transport = httpx.MockTransport(handler)
    orig_client = httpx.AsyncClient

    def patched(*args, **kwargs):
        seen.append(kwargs["timeout"])
        return orig_client(transport=transport)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    provider = OpenAICompatibleProvider(api_key="sk-test-mock-key-12345", base_url="https://mock-ai.local/v1")

    await provider.complete(
        AICompletionRequest(prompt="generate the cases", max_retries=0, timeout_seconds=LONG_GENERATION_TIMEOUT_SECONDS)
    )
    assert seen == [LONG_GENERATION_TIMEOUT_SECONDS]

    # A silent request keeps the configured default, and an interactive call can still shorten it.
    await provider.complete(AICompletionRequest(prompt="default budget", max_retries=0))
    assert seen[-1] == 30.0
    await provider.complete(AICompletionRequest(prompt="quick probe", max_retries=0, timeout_seconds=5))
    assert seen[-1] == 5.0
