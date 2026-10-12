from __future__ import annotations

import asyncio

import httpx
import pytest
from app.persistence.models import AIInvocationORM
from app.services.decision_service import DecisionService
from app.services.jev_provider import DecisionProviderError, JevDecisionProvider
from project_model.models import DecisionOption, DecisionRequest, DecisionSignalRequest
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
    ("signal_type", "answer", "value_field"),
    [
        ("noul", {"type": "noul", "probability": 0.87, "confidence": 0.93}, "probability"),
        ("score", {"type": "score", "score": 0.74, "confidence": 0.91}, "score"),
    ],
)
async def test_jev_provider_asks_scalar_signal_question(monkeypatch, signal_type, answer, value_field):
    stub = StubClient(
        StubResponse(
            200,
            {"model": "jev-1.13.0", "answers": {"signal": answer}, "usage": {"input_tokens": 9, "output_tokens": 2}},
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: stub)
    request = DecisionSignalRequest(name="signal", state={"candidate": "observed"}, instructions="Score it")
    provider = JevDecisionProvider(
        api_key="jev-secret", model="jev-1.13.0", base_url="https://example.test/v1/systemone", timeout=3
    )

    result = await (provider.ask_probability(request) if signal_type == "noul" else provider.ask_score(request))

    _url, args = stub.request_args
    assert args["json"] == {
        "model": "jev-1.13.0",
        "state": {"candidate": "observed"},
        "questions": {"signal": {"type": signal_type, "instructions": "Score it"}},
    }
    assert getattr(result, value_field) == answer[value_field]
    assert result.confidence == answer["confidence"]
    assert result.usage == {"input_tokens": 9, "output_tokens": 2}


async def test_jev_scalar_signal_without_key_never_opens_an_http_client(monkeypatch):
    def unexpected_client(**_kwargs):
        raise AssertionError("No HTTP client should be created without a configured key")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_client)
    provider = JevDecisionProvider(api_key="", model="m", base_url="https://example.test", timeout=2)
    request = DecisionSignalRequest(name="noul", state={}, instructions="Estimate")

    with pytest.raises(DecisionProviderError, match="missing_api_key"):
        await provider.ask_probability(request)


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
        self.calls = 0

    async def choose(self, request):
        from project_model.models import DecisionResult

        self.calls += 1
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
    assert result.confidence == 0.59
    assert result.attempted_provider == "jev"
    assert result.attempted_model == "m"
    assert result.attempted_choice == "yes"
    assert result.probabilities == {"yes": 0.59}
    assert result.minimum_confidence == 0.6


@pytest.mark.unit
async def test_task_jev_decision_reserves_per_task_budget_before_provider_call(monkeypatch):
    from app.services import task_decision_service as task_decision_module
    from app.services.task_decision_service import TaskDecisionService

    provider = StubDecisionProvider(0.95)
    decision_service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(provider),
        ai_repo=NoopAIRepository(),
    )
    monkeypatch.setattr(task_decision_module, "DecisionService", lambda **_kwargs: decision_service)
    reserved_for = []

    async def reserve_ai_call(task_id: str) -> bool:
        reserved_for.append(task_id)
        return False

    service = TaskDecisionService(repository_scope=None, reserve_ai_call=reserve_ai_call)
    result = await service.choose(
        DecisionRequest(
            name="browser_action_selection",
            state={},
            options=[DecisionOption(key="click", description="Click observed target")],
        ),
        task_id="task-budget",
        run_id="decision-budget",
    )

    assert reserved_for == ["task-budget"]
    assert provider.calls == 0
    assert result.fallback_used is True
    assert result.reason == "task_ai_budget_exhausted"


@pytest.mark.unit
async def test_decision_signal_value_is_recorded_in_ai_invocation_telemetry():
    class ScoreProvider:
        async def ask_score(self, _request):
            from project_model.models import DecisionResult

            return DecisionResult(provider="jev", score=0.81, confidence=0.93, model="m")

    class RecordingAIRepository:
        def __init__(self):
            self.invocations = []

        async def record_invocation(self, **kwargs):
            self.invocations.append(kwargs)

    ai_repo = RecordingAIRepository()
    service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(ScoreProvider()),
        ai_repo=ai_repo,
    )

    result = await service.ask_score(
        DecisionSignalRequest(name="discovery_candidate_score", state={}, instructions="Rank")
    )

    assert result.score == 0.81
    assert ai_repo.invocations[0]["decision_value"] == 0.81
    assert ai_repo.invocations[0]["decision_name"] == "discovery_candidate_score"


@pytest.mark.unit
async def test_decision_signal_reserves_task_budget_and_marks_exhaustion_as_fallback():
    class SignalProvider:
        calls = 0

        async def ask_probability(self, _request):
            self.calls += 1
            raise AssertionError("Provider must not be called after task budget exhaustion")

    provider = SignalProvider()
    service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(provider),
        ai_repo=NoopAIRepository(),
    )
    reserved = []

    async def reserve_task_call():
        reserved.append(True)
        return False

    result = await service.ask_probability(
        DecisionSignalRequest(name="identity", state={}, instructions="Estimate probability"),
        task_id="task-budget",
        reserve_task_call=reserve_task_call,
    )

    assert reserved == [True]
    assert provider.calls == 0
    assert result.provider == "fallback"
    assert result.fallback_used is True
    assert result.reason == "task_ai_budget_exhausted"
    assert result.probability is None


@pytest.mark.unit
async def test_optional_score_reserves_one_daily_request_for_the_required_choice(monkeypatch):
    from app.services.ai_execution_service import AIExecutionService
    from app.services.ai_settings_service import AISettingsService

    class BudgetPolicy:
        budget_enabled = True
        max_request_tokens = 10_000
        max_daily_requests = 8

    reserved_limits = []

    async def load_policy(_self):
        return BudgetPolicy()

    async def reserve_daily_limit(limit, _scope):
        reserved_limits.append(limit)

    monkeypatch.setattr(AISettingsService, "_effective_config", load_policy)
    monkeypatch.setattr(AIExecutionService, "reserve_daily_limit", staticmethod(reserve_daily_limit))

    class ScoreProvider:
        async def ask_score(self, _request):
            from project_model.models import DecisionResult

            return DecisionResult(provider="jev", score=0.8, confidence=0.9)

    service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(ScoreProvider()),
        ai_repo=NoopAIRepository(),
        repository_scope=object(),
    )
    result = await service.ask_score(
        DecisionSignalRequest(name="discovery_score", state={}, instructions="Rank this"),
        daily_request_reserve=1,
    )

    assert result.provider == "jev"
    assert reserved_limits == [7]


@pytest.mark.unit
@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), 1.1, -0.1])
async def test_decision_signal_rejects_non_finite_or_out_of_range_confidence(confidence):
    class InvalidConfidenceProvider:
        async def ask_probability(self, _request):
            from project_model.models import DecisionResult

            return DecisionResult(provider="jev", probability=0.8, confidence=confidence)

    service = DecisionService(
        settings_service=StubSettingsService(enabled=True),
        provider_registry=StubRegistry(InvalidConfidenceProvider()),
        ai_repo=NoopAIRepository(),
    )

    result = await service.ask_probability(DecisionSignalRequest(name="identity", state={}, instructions="Estimate"))

    assert result.provider == "fallback"
    assert result.reason == "confidence_missing"
    assert result.confidence is None
    assert result.probability is None


@pytest.mark.unit
async def test_decision_signal_below_minimum_confidence_falls_back_without_exposing_untrusted_value():
    class LowConfidenceSignalProvider:
        async def ask_probability(self, _request):
            from project_model.models import DecisionResult

            return DecisionResult(provider="jev", probability=0.99, confidence=0.4, model="m")

    service = DecisionService(
        settings_service=StubSettingsService(enabled=True, confidence=0.6),
        provider_registry=StubRegistry(LowConfidenceSignalProvider()),
        ai_repo=NoopAIRepository(),
    )

    result = await service.ask_probability(DecisionSignalRequest(name="identity", state={}, instructions="Estimate"))

    assert result.provider == "fallback"
    assert result.fallback_used is True
    assert result.reason == "below_minimum_confidence"
    assert result.probability is None
    assert result.attempted_provider == "jev"


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
async def test_jev_settings_are_config_managed_and_connection_result_is_sanitized(client, test_db_session, monkeypatch):
    from app.services import decision_settings_service
    from app.services.decision_settings_service import DecisionRuntimeConfig

    secret = "jev-test-secret-do-not-return"
    runtime = DecisionRuntimeConfig(
        provider="jev",
        enabled=True,
        api_key="config-managed-test-key",
        model="jev-1.13.0",
        base_url="https://mock.typesafe.test/v1/systemone",
        timeout=20,
        minimum_confidence=0.6,
    )

    async def configured_runtime(_self):
        return runtime

    monkeypatch.setattr(decision_settings_service.DecisionSettingsService, "get_runtime_config", configured_runtime)
    payload = {
        "enabled": True,
        "api_key": secret,
        "model": "jev-1.13.0",
        "base_url": "https://mock.typesafe.test/v1/systemone",
        "timeout": 20,
        "minimum_confidence": 0.6,
    }
    saved = await client.put("/api/decision/settings", json=payload)
    assert saved.status_code == 409, saved.text
    assert secret not in saved.text

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
async def test_decision_sample_evaluation_api_is_offline_and_ui_consumable(client, monkeypatch):
    async def unexpected_provider_call(*_args, **_kwargs):
        raise AssertionError("Sample evaluation must never call Jev")

    monkeypatch.setattr(JevDecisionProvider, "ask_probability", unexpected_provider_call)
    monkeypatch.setattr(JevDecisionProvider, "ask_score", unexpected_provider_call)
    response = await client.post(
        "/api/decision/evaluate-samples",
        json={
            "threshold": 0.75,
            "samples": [
                {
                    "decision_point": "locator_same_function_probability",
                    "expected": True,
                    "probability": 0.8,
                    "latency_ms": 12,
                    "input_tokens": 100,
                    "output_tokens": 20,
                },
                {
                    "decision_point": "locator_same_function_probability",
                    "expected": False,
                    "probability": 0.4,
                    "abstained": True,
                    "fallback_used": True,
                    "latency_ms": 20,
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sample_count"] == 2
    assert body["threshold"] == 0.75
    assert body["consistency_rate"] == 1
    assert body["abstention_rate"] == 0.5
    assert body["fallback_rate"] == 0.5
    assert body["decision_points"]["locator_same_function_probability"]["sample_count"] == 2
    assert body["threshold_replay"]["above_threshold_count"] == 1


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


@pytest.mark.integration
async def test_runtime_check_reports_disabled_without_probing_connectivity(client, monkeypatch):
    from app.services import decision_settings_service
    from app.services.decision_settings_service import DecisionRuntimeConfig

    async def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("A disabled runtime must not call Jev")

    monkeypatch.setattr(JevDecisionProvider, "choose", unexpected_probe)
    runtime = DecisionRuntimeConfig(
        provider="jev",
        enabled=False,
        api_key="configured-but-disabled",
        model="jev-test",
        base_url="https://mock.typesafe.test/v1/systemone",
        timeout=2,
        minimum_confidence=0.87,
    )

    async def configured_runtime(_self):
        return runtime

    monkeypatch.setattr(decision_settings_service.DecisionSettingsService, "get_runtime_config", configured_runtime)

    response = await client.post("/api/decision/runtime-check")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "connectivity": "NOT_CHECKED",
        "runtime": "DISABLED",
        "enabled": False,
        "api_key_configured": True,
        "provider": "jev",
        "model": "jev-test",
        "base_url_valid": True,
        "minimum_confidence": 0.87,
        "budget_available": True,
        "latency_ms": None,
        "reasons": ["provider_disabled"],
    }


@pytest.mark.integration
async def test_runtime_check_probes_enabled_jev_through_decision_service(client, monkeypatch):
    from app.services import decision_settings_service
    from app.services.decision_settings_service import DecisionRuntimeConfig

    async def connected_probe(self, request):
        from project_model.models import DecisionResult

        return DecisionResult(
            choice=request.options[0].key,
            confidence=0.99,
            provider="jev",
            model="jev-test",
        )

    monkeypatch.setattr(JevDecisionProvider, "choose", connected_probe)
    runtime = DecisionRuntimeConfig(
        provider="jev",
        enabled=True,
        api_key="configured-for-runtime-check",
        model="jev-test",
        base_url="https://mock.typesafe.test/v1/systemone",
        timeout=2,
        minimum_confidence=0.87,
    )

    async def configured_runtime(_self):
        return runtime

    monkeypatch.setattr(decision_settings_service.DecisionSettingsService, "get_runtime_config", configured_runtime)

    response = await client.post("/api/decision/runtime-check")

    assert response.status_code == 200, response.text
    assert response.json()["connectivity"] == "CONNECTED"
    assert response.json()["runtime"] == "READY"
    assert response.json()["model"] == "jev-test"
    assert response.json()["minimum_confidence"] == 0.87
    assert response.json()["budget_available"] is True


@pytest.mark.integration
async def test_runtime_check_blocks_when_jev_response_misses_runtime_confidence(client, monkeypatch):
    from app.services import decision_settings_service
    from app.services.decision_settings_service import DecisionRuntimeConfig

    async def low_confidence(self, request):
        from project_model.models import DecisionResult

        return DecisionResult(
            choice=request.options[0].key,
            confidence=0.2,
            provider="jev",
            model="jev-test",
        )

    monkeypatch.setattr(JevDecisionProvider, "choose", low_confidence)
    runtime = DecisionRuntimeConfig(
        provider="jev",
        enabled=True,
        api_key="configured-for-runtime-check",
        model="jev-test",
        base_url="https://mock.typesafe.test/v1/systemone",
        timeout=2,
        minimum_confidence=0.87,
    )

    async def configured_runtime(_self):
        return runtime

    monkeypatch.setattr(decision_settings_service.DecisionSettingsService, "get_runtime_config", configured_runtime)

    response = await client.post("/api/decision/runtime-check")

    assert response.status_code == 200, response.text
    assert response.json()["connectivity"] == "CONNECTED"
    assert response.json()["runtime"] == "BLOCKED"
    assert response.json()["reasons"] == ["below_minimum_confidence"]


@pytest.fixture(autouse=True)
def isolated_ai_persistence(test_db_session):
    """All provider governance and locator history use the isolated test database."""
