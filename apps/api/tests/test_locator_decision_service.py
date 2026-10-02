from __future__ import annotations

import pytest
from app.services.locator_decision_service import LocatorDecisionService
from project_model.models import DecisionResult


@pytest.fixture(autouse=True)
def isolated_locator_history(test_db_session):
    """Candidate history must use the test database, never the developer database."""


def test_candidate_generation_preserves_only_observed_locator_strategies():
    event = {
        "dom_depth": 4,
        "candidates": [
            {"kind": "role", "value": "button", "name": "Add to cart", "evidence": {"uniqueness": True}},
            {"kind": "label", "value": "Email", "evidence": {"uniqueness": True}},
            {"kind": "test_id", "value": "add-to-cart"},
            {"kind": "placeholder", "value": "Search products"},
            {"kind": "text", "value": "Add to cart", "exact": True},
            {"kind": "css", "value": "button.primary"},
            {"kind": "xpath", "value": "//button[@data-testid='add-to-cart']"},
        ],
    }

    candidates = LocatorDecisionService.generate_candidates(event)

    assert {item["strategy"] for item in candidates} == {
        "role",
        "label",
        "test_id",
        "placeholder",
        "text",
        "css",
        "xpath",
    }
    assert [item["candidate_id"] for item in candidates] == [f"candidate_{index}" for index in range(1, 8)]
    assert all("static_score" in item and "evidence" in item for item in candidates)
    assert all("confidence" not in item for item in candidates)
    assert all(item["evidence"]["dom_depth"] == 4 for item in candidates)


def test_candidate_generation_does_not_invent_unobserved_strategies():
    candidates = LocatorDecisionService.generate_candidates({"candidates": [{"kind": "test_id", "value": "save"}]})

    assert len(candidates) == 1
    assert candidates[0]["strategy"] == "test_id"
    assert candidates[0]["candidate_id"] == "candidate_1"


@pytest.mark.asyncio
async def test_jev_context_and_trace_do_not_receive_url_credentials_or_query_values():
    captured = {}

    class StubDecisionService:
        async def choose(self, request, **_kwargs):
            captured["state"] = request.state
            return DecisionResult(provider="fallback", fallback_used=True, reason="provider_disabled")

    service = LocatorDecisionService(decision_service=StubDecisionService())
    event = {
        "url": "https://user:password@example.test/account?access_token=sentinel#private",
        "action": "click",
        "candidates": [{"kind": "role", "value": "button", "name": "Save"}],
    }
    candidates = service.generate_candidates(event)
    result = await service.decide(run_id="run_url_redaction", event=event, candidates=candidates)

    safe_url = "https://example.test/account"
    assert captured["state"]["context"]["url"] == safe_url
    assert "sentinel" not in str(captured["state"])
    assert "password" not in str(captured["state"])
    assert "sentinel" not in str(result["trace"])
