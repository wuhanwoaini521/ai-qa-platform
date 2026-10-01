from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from app.persistence.models import AIInvocationORM, DecisionProviderConfigORM
from app.services.decision_service import DecisionService
from app.services.jev_provider import DecisionProviderError, JevDecisionProvider
from app.services.secret_store import SecretStore
from project_model.models import DecisionOption, DecisionRequest
from sqlalchemy import select


class StubResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class StubClient:
    def __init__(self, response: StubResponse):
        self.response = response
        self.request_args = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.request_args = (url, kwargs)
        return self.response


class StubFailingClient(StubClient):
    def __init__(self, error):
        self.error = error

    async def post(self, url, **kwargs):
        raise self.error


@pytest.mark.unit
async def test_jev_provider_sends_dynamic_choice_request_and_normalizes_response(monkeypatch):
    stub = StubClient(
        StubResponse(
            200,
            {
                "model": "jev-1.13.0",
                "answers": {
                    "risk": {
                        "type": "choice",
                        "choice": "allow",
                        "confidence": 0.91,
                        "probabilities": {"allow": 0.91, "deny": 0.09},
                    }
                },
                "usage": {"input_tokens": 12, "output_tokens": 3, "secret": 999},
            },
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: stub)
    request = DecisionRequest(
        name="risk",
        state={"change_count": 4},
        instructions="Choose one",
        options=[DecisionOption(key="allow", description="Accept"), DecisionOption(key="deny", description="Reject")],
    )

    result = await JevDecisionProvider(
        api_key="jev-secret", model="jev-1.13.0", base_url="https://example.test/v1", timeout=7
    ).choose(request)

    url, args = stub.request_args
    assert url == "https://example.test/v1/systemone"
    assert args["headers"]["Authorization"] == "Bearer jev-secret"
    assert args["json"] == {
        "model": "jev-1.13.0",
        "state": {"change_count": 4},
        "questions": {
            "risk": {"type": "choice", "instructions": "Choose one", "criteria": {"allow": "Accept", "deny": "Reject"}}
        },
    }
    assert result.choice == "allow" and result.confidence == 0.91
    assert result.probabilities == {"allow": 0.91, "deny": 0.09}
    assert result.usage == {"input_tokens": 12, "output_tokens": 3}


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "invalid_api_key"),
        (403, "invalid_api_key"),
        (404, "unsupported_model"),
        (429, "rate_limited"),
        (503, "upstream_error"),
    ],
)
async def test_jev_provider_classifies_http_failures_without_leaking_response(monkeypatch, status, code):
    secret = "never-leak-this-key"
    stub = StubClient(StubResponse(status, {"error": secret}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: stub)
    request = DecisionRequest(name="x", state={}, options=[DecisionOption(key="yes", description="yes")])

    with pytest.raises(DecisionProviderError) as caught:
        await JevDecisionProvider(api_key=secret, model="m", base_url="https://example.test", timeout=2).choose(request)

    assert caught.value.code == code
    assert secret not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"answers": {"x": {"type": "choice", "choice": "outside"}}},
        {"answers": {"x": {"type": "text", "choice": "yes"}}},
    ],
)
async def test_jev_provider_rejects_malformed_or_unoffered_answers(monkeypatch, body):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: StubClient(StubResponse(200, body)))
    request = DecisionRequest(name="x", state={}, options=[DecisionOption(key="yes", description="yes")])
    with pytest.raises(DecisionProviderError) as caught:
        await JevDecisionProvider(api_key="secret", model="m", base_url="https://example.test", timeout=2).choose(
            request
        )
    assert caught.value.code == "invalid_response"


@pytest.mark.parametrize(
    "error, code",
    [
        (httpx.ReadTimeout("credential-like-value"), "timeout"),
        (httpx.ConnectError("credential-like-value"), "network_error"),
    ],
)
async def test_jev_provider_classifies_transport_failures_without_leaking_details(monkeypatch, error, code):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: StubFailingClient(error))
    request = DecisionRequest(name="x", state={}, options=[DecisionOption(key="yes", description="yes")])
    with pytest.raises(DecisionProviderError) as caught:
        await JevDecisionProvider(api_key="api-key", model="m", base_url="https://example.test", timeout=2).choose(
            request
        )
    assert caught.value.code == code
    assert "credential-like-value" not in str(caught.value)


class StubSettingsService:
    def __init__(self, *, enabled: bool, confidence: float = 0.6):
        from app.services.decision_settings_service import DecisionRuntimeConfig

        self.config = DecisionRuntimeConfig(
            provider="jev",
            enabled=enabled,
            api_key="test",
            model="m",
            base_url="https://example.test",
            timeout=2,
            minimum_confidence=confidence,
        )

    async def get_runtime_config(self):
        return self.config


class StubDecisionProvider:
    def __init__(self, confidence: float):
        self.confidence = confidence

    async def choose(self, request):
        from project_model.models import DecisionResult

        probabilities = {"yes": self.confidence} if self.confidence is not None else {}
        return DecisionResult(
            choice="yes", confidence=self.confidence, probabilities=probabilities, provider="jev", model="m"
        )


class StubRegistry:
    def __init__(self, provider):
        self.provider = provider

    def create(self, name, config):
        return self.provider


class NoopAIRepository:
    async def record_invocation(self, **kwargs):
        return None


@pytest.mark.unit
async def test_decision_service_falls_back_when_disabled_or_below_confidence():
    request = DecisionRequest(
        name="risk",
        state={},
        options=[
            DecisionOption(key="yes", description="Accept"),
            DecisionOption(key="unknown", description="Need review"),
        ],
    )
    disabled = DecisionService(settings_service=StubSettingsService(enabled=False), ai_repo=NoopAIRepository())
    disabled_result = await disabled.choose(request)
    assert disabled_result.choice == "unknown" and disabled_result.fallback_used
    assert disabled_result.reason == "provider_disabled"

    low_confidence = DecisionService(
        settings_service=StubSettingsService(enabled=True, confidence=0.6),
        provider_registry=StubRegistry(StubDecisionProvider(0.59)),
        ai_repo=NoopAIRepository(),
    )
    result = await low_confidence.choose(request)
    assert result.choice == "unknown" and result.fallback_used
    assert result.reason == "below_minimum_confidence"


@pytest.mark.unit
async def test_decision_service_accepts_missing_confidence_only_when_requested():
    request = DecisionRequest(
        name="locator_candidate_selection",
        state={"candidates": [{"candidate_id": "candidate_1"}]},
        options=[DecisionOption(key="yes", description="get_by_role('button')")],
    )
    service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(StubDecisionProvider(None)),
        ai_repo=NoopAIRepository(),
    )

    result = await service.choose(request, allow_missing_confidence=True)

    assert result.provider == "jev"
    assert result.choice == "yes"
    assert result.confidence is None
    assert result.fallback_used is False


@pytest.mark.unit
async def test_decision_service_times_out_to_unknown_option():
    request = DecisionRequest(
        name="risk",
        state={},
        options=[DecisionOption(key="ship", description="Allow"), DecisionOption(key="unknown", description="Review")],
    )
    settings = StubSettingsService(enabled=True)
    settings.config = settings.config.__class__(**{**settings.config.__dict__, "timeout": 0.01})

    class SlowProvider:
        async def choose(self, decision_request):
            await asyncio.sleep(1.5)

    service = DecisionService(
        settings_service=settings, provider_registry=StubRegistry(SlowProvider()), ai_repo=NoopAIRepository()
    )
    result = await service.choose(request)
    assert result.choice == "unknown" and result.fallback_used
    assert result.reason == "timeout"


@pytest.mark.integration
async def test_jev_settings_api_persists_encrypted_secret_and_connection_result(client, test_db_session, monkeypatch):
    secret = "jev-test-secret-do-not-return"
    payload = {
        "enabled": True,
        "api_key": secret,
        "model": "jev-1.13.0",
        "base_url": "https://mock.typesafe.test/v1/systemone",
        "timeout": 20,
        "minimum_confidence": 0.6,
    }
    saved = await client.put("/api/decision/settings", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["api_key_configured"] is True
    assert secret not in json.dumps(saved.json())

    async with test_db_session() as session:
        row = (await session.execute(select(DecisionProviderConfigORM))).scalar_one()
        assert row.encrypted_api_key and secret not in row.encrypted_api_key
        assert SecretStore(master_key="change-me-in-production").decrypt_secret(row.encrypted_api_key) == secret

    loaded = await client.get("/api/decision/settings")
    assert loaded.status_code == 200
    assert loaded.json()["model"] == "jev-1.13.0"
    assert secret not in loaded.text

    async def fake_choose(self, request):
        from project_model.models import DecisionResult

        probabilities = {
            option.key: (0.99 if option.key == request.options[0].key else 0.01) for option in request.options
        }
        return DecisionResult(
            choice=request.options[0].key,
            confidence=0.99,
            probabilities=probabilities,
            provider="jev",
            model="jev-1.13.0",
        )

    monkeypatch.setattr(JevDecisionProvider, "choose", fake_choose)
    tested = await client.post("/api/decision/test-connection", json={**payload, "api_key": ""})
    assert tested.status_code == 200, tested.text
    assert tested.json()["connected"] is True
    assert secret not in tested.text

    choice = await client.post(
        "/api/decision/choose",
        json={
            "name": "release_decision",
            "state": {"open_critical_bugs": 0},
            "options": [
                {"key": "ship", "description": "Allow release"},
                {"key": "block", "description": "Block release"},
            ],
        },
    )
    assert choice.status_code == 200, choice.text
    assert choice.json()["decision_name"] == "release_decision"
    assert choice.json()["choice"] == "ship" and choice.json()["fallback_used"] is False
    async with test_db_session() as session:
        invocation = (
            await session.execute(select(AIInvocationORM).where(AIInvocationORM.decision_name == "release_decision"))
        ).scalar_one()
        assert invocation.decision_choice == "ship" and invocation.decision_confidence == 0.99


@pytest.mark.integration
async def test_jev_settings_are_admin_only(client, role_client):
    async with role_client("QA_LEAD") as lead:
        assert (await lead.get("/api/decision/settings")).status_code == 403
        assert (
            await lead.put(
                "/api/decision/settings",
                json={
                    "enabled": False,
                    "model": "m",
                    "base_url": "https://example.test",
                    "timeout": 20,
                    "minimum_confidence": 0.6,
                },
            )
        ).status_code == 403
