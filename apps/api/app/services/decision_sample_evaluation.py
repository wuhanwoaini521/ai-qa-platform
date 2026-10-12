from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations
from typing import Any

from qa_core.failure.redactor import SensitiveRedactor


def evaluate_decision_samples(
    samples: list[dict[str, Any]],
    *,
    threshold: float,
    input_cost_per_million_usd: float | None = None,
    output_cost_per_million_usd: float | None = None,
) -> dict[str, Any]:
    """Calculate offline metrics only; this function never calls a decision provider."""
    if isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be a finite number between 0 and 1")
    for rate in (input_cost_per_million_usd, output_cost_per_million_usd):
        if rate is not None and (isinstance(rate, bool) or not math.isfinite(rate) or rate < 0):
            raise ValueError("token prices must be finite, non-negative numbers")

    samples = [_normalize_sample(sample) for sample in samples]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        name = _first(sample, "decision_point", "decision_name", "name", "task")
        point = SensitiveRedactor.redact_text(str(name))[:128] if name is not None else "unknown"
        grouped[point].append(sample)

    per_point = {
        point: _metrics(
            rows,
            threshold=threshold,
            input_cost_per_million_usd=input_cost_per_million_usd,
            output_cost_per_million_usd=output_cost_per_million_usd,
        )
        for point, rows in sorted(grouped.items())
    }
    total = _metrics(
        samples,
        threshold=threshold,
        input_cost_per_million_usd=input_cost_per_million_usd,
        output_cost_per_million_usd=output_cost_per_million_usd,
    )
    total["threshold_replay"]["by_decision_point"] = {
        point: metrics["threshold_replay"] for point, metrics in per_point.items()
    }
    total["decision_points"] = per_point
    total["threshold"] = threshold
    return total


def _metrics(
    samples: list[dict[str, Any]],
    *,
    threshold: float,
    input_cost_per_million_usd: float | None,
    output_cost_per_million_usd: float | None,
) -> dict[str, Any]:
    count = len(samples)
    labels = [_consistency(sample, threshold) for sample in samples]
    labeled = [value for value in labels if value is not None]
    ranking_checks = _ranking_consistency(samples)
    consistency_checks = labeled + ranking_checks
    abstentions = sum(_abstained(sample) for sample in samples)
    fallbacks = sum(_fallback(sample) for sample in samples)
    latencies = [
        value
        for sample in samples
        if (value := _number(_first(sample, "latency_ms", "duration_ms"))) is not None and value >= 0
    ]
    input_tokens = sum(_token_count(sample, "input_tokens") or 0 for sample in samples)
    output_tokens = sum(_token_count(sample, "output_tokens") or 0 for sample in samples)
    costs = [
        _cost(
            sample,
            input_cost_per_million_usd=input_cost_per_million_usd,
            output_cost_per_million_usd=output_cost_per_million_usd,
        )
        for sample in samples
    ]
    known_costs = [cost for cost, _source in costs if cost is not None]
    sources = {source for _cost_value, source in costs if source is not None}
    replay = _threshold_replay(samples, threshold)
    return {
        "sample_count": count,
        "consistency_rate": round(sum(consistency_checks) / len(consistency_checks), 6) if consistency_checks else None,
        "labeled_sample_count": len(labeled),
        "consistency_observation_count": len(consistency_checks),
        "ranking_pair_count": len(ranking_checks),
        "abstention_rate": round(abstentions / count, 6) if count else 0.0,
        "fallback_rate": round(fallbacks / count, 6) if count else 0.0,
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2) if latencies else None,
        "cost_usd": round(sum(known_costs), 8) if known_costs else None,
        "cost_source": _cost_source(sources, known=len(known_costs), total=count),
        "cost_coverage": round(len(known_costs) / count, 6) if count else 0.0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "threshold_replay": replay,
    }


def _threshold_replay(samples: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    records = []
    for index, sample in enumerate(samples):
        signal_type, value = _signal(sample)
        if signal_type is None or value is None:
            continue
        records.append(
            {
                "sample_id": SensitiveRedactor.redact_text(str(_first(sample, "sample_id", "id") or index))[:128],
                "signal_type": signal_type,
                "value": value,
                "above_threshold": value >= threshold,
            }
        )
    total = len(records)
    above = sum(record["above_threshold"] for record in records)
    return {
        "sample_count": total,
        "above_threshold_count": above,
        "below_threshold_count": total - above,
        "above_threshold_rate": round(above / total, 6) if total else None,
        "signals": records,
    }


def _normalize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(sample)
    for key in ("decision_summary", "same_function_signal", "metadata", "payload"):
        nested = sample.get(key)
        if isinstance(nested, dict):
            normalized = {**nested, **normalized}
    return normalized


def _signal(sample: dict[str, Any]) -> tuple[str | None, float | None]:
    for key in ("probability", "noul_probability"):
        if key in sample:
            return "noul", _unit_interval(sample.get(key))
    if "score" in sample:
        return "score", _unit_interval(sample.get("score"))
    value = _unit_interval(sample.get("decision_value"))
    if value is None:
        return None, None
    kind = " ".join(
        str(sample.get(key) or "").casefold() for key in ("signal_type", "decision_type", "decision_name", "name")
    )
    if any(word in kind for word in ("noul", "probability", "same_function")):
        return "noul", value
    if "score" in kind or "discovery" in kind:
        return "score", value
    return None, None


def _consistency(sample: dict[str, Any], threshold: float) -> bool | None:
    expected = _first(sample, "expected", "ground_truth", "label")
    if expected is None:
        return None
    signal_type, value = _signal(sample)
    if value is not None and isinstance(expected, bool):
        return (value >= threshold) is expected
    actual = _first(sample, "prediction", "actual", "choice", "decision_choice")
    if actual is None:
        return None
    return str(actual).strip().casefold() == str(expected).strip().casefold()


def _ranking_consistency(samples: list[dict[str, Any]]) -> list[bool]:
    groups: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for sample in samples:
        group_id = _first(sample, "selection_group", "group_id", "decision_id", "state_id")
        rank = _number(_first(sample, "expected_rank", "ground_truth_rank", "label_rank"))
        signal_type, score = _signal(sample)
        if group_id is None or rank is None or score is None or signal_type != "score":
            continue
        point = str(_first(sample, "decision_point", "decision_name", "name", "task") or "unknown")[:128]
        groups[(point, str(group_id))].append((score, rank))

    checks = []
    for candidates in groups.values():
        for (left_score, left_rank), (right_score, right_rank) in combinations(candidates, 2):
            if left_score == right_score or left_rank == right_rank:
                continue
            checks.append((left_score > right_score) == (left_rank < right_rank))
    return checks


def _abstained(sample: dict[str, Any]) -> bool:
    if any(sample.get(key) is True for key in ("abstained", "abstain", "jev_abstain")):
        return True
    status = str(sample.get("status") or "").casefold()
    choice = str(_first(sample, "choice", "prediction", "actual") or "").casefold()
    return status in {"abstain", "abstained"} or choice in {"unknown", "abstain", "abstained", "undecided"}


def _fallback(sample: dict[str, Any]) -> bool:
    provider = str(sample.get("provider") or "").casefold()
    return provider == "fallback" or any(sample.get(key) is True for key in ("fallback", "fallback_used"))


def _token_count(sample: dict[str, Any], token_name: str) -> int | None:
    usage = sample.get("usage")
    value = sample.get(token_name)
    if value is None and isinstance(usage, dict):
        value = usage.get(token_name)
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _cost(
    sample: dict[str, Any],
    *,
    input_cost_per_million_usd: float | None,
    output_cost_per_million_usd: float | None,
) -> tuple[float | None, str | None]:
    measured = _number(sample.get("cost_usd"))
    if measured is not None and measured >= 0:
        return measured, "measured"
    has_rate = input_cost_per_million_usd is not None or output_cost_per_million_usd is not None
    if not has_rate:
        return None, None
    input_tokens = _token_count(sample, "input_tokens")
    output_tokens = _token_count(sample, "output_tokens")
    components = []
    complete = True
    for tokens, rate in (
        (input_tokens, input_cost_per_million_usd),
        (output_tokens, output_cost_per_million_usd),
    ):
        if rate is None:
            if tokens != 0:
                complete = False
            continue
        if tokens is None:
            complete = False
            continue
        components.append(tokens * rate / 1_000_000)
    if not components:
        return None, None
    return sum(components), "estimated" if complete else "partial_estimate"


def _cost_source(sources: set[str], *, known: int, total: int) -> str:
    if not sources:
        return "unavailable"
    if "partial_estimate" in sources or known < total:
        return "partial"
    if sources == {"measured"}:
        return "measured"
    if sources == {"estimated"}:
        return "estimated"
    return "mixed"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _first(sample: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if sample.get(key) is not None:
            return sample[key]
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _unit_interval(value: Any) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and 0 <= parsed <= 1 else None
