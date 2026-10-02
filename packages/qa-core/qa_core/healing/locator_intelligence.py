from __future__ import annotations

import re
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
        raw_evidence = candidate.get("evidence")
        evidence = (
            dict(raw_evidence)
            if isinstance(raw_evidence, Mapping)
            else {"description": raw_evidence}
            if raw_evidence
            else {}
        )
        count = evidence.get("match_count")
        if isinstance(count, int):
            evidence["uniqueness"] = count == 1
        # Absence of nth is not proof of uniqueness; only observed counts establish it.
        evidence.setdefault("uniqueness", False if nth is not None else None)
        dynamic = bool(re.search(r"(?:\d{5,}|[0-9a-f]{8,})", value, re.I))
        evidence.setdefault("dynamic_attribute_risk", dynamic)
        if evidence["uniqueness"] is False:
            score -= 0.15
        if evidence["dynamic_attribute_risk"]:
            score -= 0.2
        history = evidence.get("history") or {}
        successes, failures = history.get("success_count", 0), history.get("failure_count", 0)
        if successes + failures:
            score += 0.1 * ((successes + 1) / (successes + failures + 2) - 0.5)
        evidence.setdefault("stability", _STRATEGY_SCORE.get(kind, 0.4))
        evidence.setdefault("semantic_quality", _STRATEGY_SCORE.get(kind, 0.4))
        item = {
            **candidate,
            "kind": kind,
            "value": value,
            "evidence": evidence,
            "confidence": round(max(0.05, min(score, 0.99)), 2),
        }
        ranked.append((item["confidence"], -index, item))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked]
