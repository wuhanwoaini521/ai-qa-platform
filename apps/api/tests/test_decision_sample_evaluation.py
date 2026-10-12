from __future__ import annotations

from app.services.decision_sample_evaluation import evaluate_decision_samples


def test_evaluator_reports_consistency_abstention_fallback_latency_cost_and_threshold_replay():
    samples = [
        {
            "decision_point": "locator_same_function_probability",
            "expected": True,
            "probability": 0.82,
            "latency_ms": 12,
            "fallback_used": False,
            "input_tokens": 100,
            "output_tokens": 25,
            "cost_usd": 0.001,
        },
        {
            "decision_point": "locator_same_function_probability",
            "expected": False,
            "probability": 0.45,
            "latency_ms": 28,
            "fallback_used": True,
            "abstained": True,
        },
        {
            "decision_point": "discovery_candidate_score",
            "score": 0.91,
            "latency_ms": 10,
            "usage": {"input_tokens": 50, "output_tokens": 15},
        },
    ]

    report = evaluate_decision_samples(samples, threshold=0.7)

    assert report["sample_count"] == 3
    assert report["consistency_rate"] == 1.0
    assert report["labeled_sample_count"] == 2
    assert report["abstention_rate"] == 0.333333
    assert report["fallback_rate"] == 0.333333
    assert report["mean_latency_ms"] == 16.67
    assert report["p95_latency_ms"] == 28
    assert report["cost_usd"] == 0.001
    assert report["cost_source"] == "partial"
    assert report["input_tokens"] == 150
    assert report["output_tokens"] == 40
    replay = report["threshold_replay"]
    assert replay["sample_count"] == 3
    assert replay["above_threshold_count"] == 2
    assert replay["below_threshold_count"] == 1
    assert replay["by_decision_point"]["discovery_candidate_score"]["signals"][0]["signal_type"] == "score"


def test_cost_reports_partial_estimates_when_one_token_price_is_unknown():
    report = evaluate_decision_samples(
        [{"decision_point": "score", "input_tokens": 100, "output_tokens": 20}],
        threshold=0.7,
        input_cost_per_million_usd=2.0,
    )

    assert report["cost_usd"] == 0.0002
    assert report["cost_source"] == "partial"


def test_provider_fallback_and_unknown_choice_are_counted_as_fallback_and_abstention():
    report = evaluate_decision_samples(
        [
            {"decision_point": "decision", "provider": "fallback", "choice": "unknown"},
        ],
        threshold=0.7,
    )

    assert report["fallback_rate"] == 1
    assert report["abstention_rate"] == 1


def test_threshold_replay_is_offline_and_changes_only_the_advisory_boundary():
    samples = [
        {"decision_name": "locator_same_function_probability", "decision_value": 0.66},
        {"decision_name": "locator_same_function_probability", "decision_value": 0.84},
    ]

    strict = evaluate_decision_samples(samples, threshold=0.8)
    lenient = evaluate_decision_samples(samples, threshold=0.6)

    assert strict["threshold_replay"]["above_threshold_count"] == 1
    assert lenient["threshold_replay"]["above_threshold_count"] == 2
    assert strict["fallback_rate"] == lenient["fallback_rate"] == 0
    assert strict["consistency_rate"] is None


def test_evaluator_accepts_discovery_event_metadata_as_a_decision_sample():
    report = evaluate_decision_samples(
        [
            {
                "id": "event-1",
                "type": "decision.score_recommendation",
                "metadata": {
                    "decision_point": "discovery_candidate_score",
                    "candidate_id": "candidate-1",
                    "score": 0.83,
                    "confidence": 0.92,
                    "provider": "jev",
                    "fallback_used": False,
                    "latency_ms": 11,
                    "input_tokens": 40,
                    "output_tokens": 8,
                },
            }
        ],
        threshold=0.7,
    )

    assert report["decision_points"]["discovery_candidate_score"]["sample_count"] == 1
    assert report["decision_points"]["discovery_candidate_score"]["mean_latency_ms"] == 11
    assert report["threshold_replay"]["above_threshold_count"] == 1


def test_score_consistency_compares_pairwise_order_against_offline_expected_ranks():
    samples = [
        {
            "decision_point": "discovery_candidate_score",
            "selection_group": "state-1",
            "candidate_id": "candidate-a",
            "score": 0.8,
            "expected_rank": 1,
        },
        {
            "decision_point": "discovery_candidate_score",
            "selection_group": "state-1",
            "candidate_id": "candidate-b",
            "score": 0.4,
            "expected_rank": 2,
        },
        {
            "decision_point": "discovery_candidate_score",
            "selection_group": "state-2",
            "candidate_id": "candidate-c",
            "score": 0.2,
            "expected_rank": 1,
        },
        {
            "decision_point": "discovery_candidate_score",
            "selection_group": "state-2",
            "candidate_id": "candidate-d",
            "score": 0.9,
            "expected_rank": 2,
        },
    ]

    report = evaluate_decision_samples(samples, threshold=0.7)

    assert report["decision_points"]["discovery_candidate_score"]["ranking_pair_count"] == 2
    assert report["decision_points"]["discovery_candidate_score"]["consistency_rate"] == 0.5
    assert report["threshold_replay"]["above_threshold_count"] == 2


def test_evaluator_estimates_cost_only_when_token_rates_are_supplied():
    samples = [{"decision_point": "test", "input_tokens": 1000, "output_tokens": 500}]

    unavailable = evaluate_decision_samples(samples, threshold=0.7)
    estimated = evaluate_decision_samples(
        samples,
        threshold=0.7,
        input_cost_per_million_usd=2.0,
        output_cost_per_million_usd=4.0,
    )

    assert unavailable["cost_usd"] is None
    assert unavailable["cost_source"] == "unavailable"
    assert estimated["cost_usd"] == 0.004
    assert estimated["cost_source"] == "estimated"
    assert estimated["cost_coverage"] == 1
