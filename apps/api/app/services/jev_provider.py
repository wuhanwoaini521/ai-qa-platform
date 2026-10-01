from __future__ import annotations

import math
from typing import Any

import httpx
from project_model.models import DecisionRequest, DecisionResult


class DecisionProviderError(Exception):
    """A safe, classified provider failure without upstream body or credential data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class JevDecisionProvider:
    name = "jev"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = self._endpoint(base_url)
        self._timeout = timeout

    @staticmethod
    def _endpoint(value: str) -> str:
        endpoint = value.strip().rstrip("/")
        if endpoint.endswith("/systemone"):
            return endpoint
        if endpoint.endswith("/v1"):
            return f"{endpoint}/systemone"
        return f"{endpoint}/v1/systemone"

    async def choose(self, request: DecisionRequest) -> DecisionResult:
        if not self._api_key:
            raise DecisionProviderError("missing_api_key")

        keys = [option.key for option in request.options]
        if len(set(keys)) != len(keys):
            raise DecisionProviderError("invalid_request")

        payload: dict[str, Any] = {
            "model": self._model,
            "state": request.state,
            "questions": {
                request.name: {
                    "type": "choice",
                    "instructions": request.instructions or f"Choose exactly one option for decision '{request.name}'.",
                    "criteria": {option.key: option.description for option in request.options},
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                response = await client.post(
                    self._base_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as error:
            raise DecisionProviderError("timeout") from error
        except httpx.RequestError as error:
            raise DecisionProviderError("network_error") from error

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
            answers = body.get("answers")
            answer = answers.get(request.name) if isinstance(answers, dict) else None
            if not isinstance(answer, dict) or answer.get("type") != "choice":
                raise ValueError("missing answer")
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in keys:
                raise ValueError("invalid choice")

            confidence = answer.get("confidence")
            if confidence is not None:
                confidence = float(confidence)
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    confidence = None

            raw_probabilities = answer.get("probabilities")
            probabilities: dict[str, float] = {}
            if isinstance(raw_probabilities, dict):
                for key, value in raw_probabilities.items():
                    if key in keys:
                        try:
                            probability = float(value)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(probability) and 0 <= probability <= 1:
                            probabilities[key] = probability

            raw_usage = body.get("usage")
            usage = None
            if isinstance(raw_usage, dict):
                usage = {
                    key: value
                    for key, value in raw_usage.items()
                    if key in ("input_tokens", "output_tokens") and (value is None or isinstance(value, (int, float)))
                }
            model = body.get("model")
            return DecisionResult(
                choice=choice,
                confidence=confidence,
                probabilities=probabilities,
                provider=self.name,
                model=model if isinstance(model, str) else self._model,
                usage=usage,
            )
        except (ValueError, TypeError, KeyError):
            raise DecisionProviderError("invalid_response") from None
