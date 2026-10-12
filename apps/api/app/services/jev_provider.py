from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx
from project_model.models import DecisionRequest, DecisionResult, DecisionSignalRequest


class DecisionProviderError(Exception):
    """A safe, classified provider failure without upstream body or credential data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class JevDecisionProvider:
    name = "jev"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float, retries: int = 1) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = self._endpoint(base_url)
        self._timeout = timeout
        self._retries = retries

    @staticmethod
    def _endpoint(value: str) -> str:
        endpoint = value.strip().rstrip("/")
        if endpoint.endswith("/systemone"):
            return endpoint
        if endpoint.endswith("/v1"):
            return f"{endpoint}/systemone"
        return f"{endpoint}/v1/systemone"

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise DecisionProviderError("missing_api_key")

        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            for attempt in range(self._retries + 1):
                try:
                    response = await client.post(
                        self._base_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                except httpx.TimeoutException as error:
                    provider_error = DecisionProviderError("timeout")
                    if attempt == self._retries:
                        raise provider_error from error
                    continue
                except httpx.RequestError as error:
                    provider_error = DecisionProviderError("network_error")
                    if attempt == self._retries:
                        raise provider_error from error
                    continue
                if response.status_code != 429 and response.status_code < 500:
                    break
                if attempt == self._retries:
                    break
                await asyncio.sleep(0.1 * (attempt + 1))

        if response.status_code in (401, 403):
            raise DecisionProviderError("invalid_api_key")
        if response.status_code == 404:
            raise DecisionProviderError("unsupported_model")
        if response.status_code == 429:
            raise DecisionProviderError("rate_limited")
        if response.status_code >= 500:
            raise DecisionProviderError("upstream_error")
        if response.status_code >= 400:
            raise DecisionProviderError("invalid_request")
        try:
            body = response.json()
        except (ValueError, TypeError):
            raise DecisionProviderError("invalid_response") from None
        if not isinstance(body, dict):
            raise DecisionProviderError("invalid_response")
        return body

    async def choose(self, request: DecisionRequest) -> DecisionResult:
        keys = [option.key for option in request.options]
        if len(set(keys)) != len(keys):
            raise DecisionProviderError("invalid_request")

        body = await self._post(
            {
                "model": self._model,
                "state": request.state,
                "questions": {
                    request.name: {
                        "type": "choice",
                        "instructions": request.instructions
                        or f"Choose exactly one option for decision '{request.name}'.",
                        "criteria": {option.key: option.description for option in request.options},
                    }
                },
            }
        )
        try:
            answer = self._answer(body, request.name, "choice")
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in keys:
                raise ValueError("invalid choice")

            probabilities: dict[str, float] = {}
            raw_probabilities = answer.get("probabilities")
            if isinstance(raw_probabilities, dict):
                for key, value in raw_probabilities.items():
                    probability = self._unit_interval(value)
                    if key in keys and probability is not None:
                        probabilities[key] = probability

            return DecisionResult(
                choice=choice,
                confidence=self._unit_interval(answer.get("confidence")),
                probabilities=probabilities,
                provider=self.name,
                model=self._model_name(body),
                usage=self._usage(body),
            )
        except (ValueError, TypeError, KeyError):
            raise DecisionProviderError("invalid_response") from None

    async def ask_probability(self, request: DecisionSignalRequest) -> DecisionResult:
        return await self._ask_scalar(request, signal_type="noul")

    async def ask_score(self, request: DecisionSignalRequest) -> DecisionResult:
        return await self._ask_scalar(request, signal_type="score")

    async def _ask_scalar(self, request: DecisionSignalRequest, *, signal_type: str) -> DecisionResult:
        body = await self._post(
            {
                "model": self._model,
                "state": request.state,
                "questions": {
                    request.name: {
                        "type": signal_type,
                        "instructions": request.instructions,
                    }
                },
            }
        )
        try:
            answer = self._answer(body, request.name, signal_type)
            value_keys = ("probability", "noul", "value") if signal_type == "noul" else ("score", "value")
            value = next((self._unit_interval(answer.get(key)) for key in value_keys if key in answer), None)
            if value is None:
                raise ValueError("missing signal value")
            return DecisionResult(
                probability=value if signal_type == "noul" else None,
                score=value if signal_type == "score" else None,
                confidence=self._unit_interval(answer.get("confidence")),
                provider=self.name,
                model=self._model_name(body),
                usage=self._usage(body),
            )
        except (ValueError, TypeError, KeyError):
            raise DecisionProviderError("invalid_response") from None

    @staticmethod
    def _answer(body: dict[str, Any], name: str, expected_type: str) -> dict[str, Any]:
        answers = body.get("answers")
        answer = answers.get(name) if isinstance(answers, dict) else None
        if not isinstance(answer, dict) or answer.get("type") != expected_type:
            raise ValueError("missing answer")
        return answer

    @staticmethod
    def _unit_interval(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) and 0 <= parsed <= 1 else None

    def _model_name(self, body: dict[str, Any]) -> str:
        model = body.get("model")
        return model if isinstance(model, str) else self._model

    @staticmethod
    def _usage(body: dict[str, Any]) -> dict[str, int | float | None] | None:
        raw_usage = body.get("usage")
        if not isinstance(raw_usage, dict):
            return None
        return {
            key: value
            for key, value in raw_usage.items()
            if key in ("input_tokens", "output_tokens")
            and (value is None or (not isinstance(value, bool) and isinstance(value, (int, float))))
        }
