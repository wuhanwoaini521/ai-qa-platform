from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_STRATEGY_SCORE = {
    "role": 1.0,
    "label": 0.98,
    "test_id": 0.97,
    "placeholder": 0.92,
    "id": 0.88,
    "name": 0.82,
    "text": 0.76,
    "css": 0.58,
    "xpath": 0.35,
}


def rank_locator_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank observed locator candidates by stability and uniqueness.

    `nth` is the zero-based duplicate match index supplied by the browser recorder.
    This function never invents candidates; it only orders observed evidence.
    """
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        kind = str(candidate.get("kind", "css"))
        value = str(candidate.get("value", "")).strip()
        if not value:
            continue
        nth = candidate.get("nth")
        score = _STRATEGY_SCORE.get(kind, 0.4)
        if nth is not None:
            score -= 0.18
        if candidate.get("exact") is False and kind in {"role", "label", "placeholder", "text"}:
            score -= 0.08
        item = {**candidate, "kind": kind, "value": value, "confidence": round(max(0.05, min(score, 0.99)), 2)}
        ranked.append((item["confidence"], -index, item))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked]
