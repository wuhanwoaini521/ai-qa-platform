# Decision signal samples

`noul` probabilities and `score` values are advisory signals. They do not set test PASS/FAIL or authorize browser actions. Locator Repair uses a trusted same-function probability only as an Apply recommendation: a value below the configured threshold withholds Apply and reports the reason. An unavailable/fallback probability is labeled as such and is never treated as an estimate. Discovery uses scores only to reorder already-filtered candidates; its normal Jev choice and deterministic browser-safety checks remain in force.

## Offline evaluator

Run the evaluator against a JSON array, JSONL file, or an object containing `decision_samples`:

```bash
uv run --package api python scripts/evaluate_decision_samples.py samples.json \
  --threshold 0.75 \
  --input-cost-per-million-usd 2.00 \
  --output-cost-per-million-usd 8.00
```

Sample fields are intentionally flexible. Flat invocation records and discovery event objects with `metadata` are accepted. Recommended fields:

```json
{
  "decision_point": "locator_same_function_probability",
  "sample_id": "sample-001",
  "expected": true,
  "probability": 0.82,
  "confidence": 0.91,
  "abstained": false,
  "fallback_used": false,
  "latency_ms": 230,
  "input_tokens": 320,
  "output_tokens": 18,
  "cost_usd": 0.00042
}
```

For Discovery ranking comparisons, include `selection_group`, `candidate_id`, `score`, and `expected_rank` on each candidate sample. Consistency is computed over labeled outcomes and pairwise score/rank comparisons; unlabeled samples are excluded. Abstention and fallback are separate rates. Cost is reported as measured when `cost_usd` is present, estimated only when token prices are supplied, and otherwise `null` with an explicit coverage/source field.

Changing `--threshold` replays only the scalar advisory boundary and reports values above/below it. It does not run a provider, browser, test, Apply operation, or PASS/FAIL decision.

## UI API

Authenticated UI clients can submit the same sample array to `POST /api/decision/evaluate-samples` with `threshold` and optional token prices. The response contains aggregate and per-decision-point consistency, abstention, fallback, latency, cost, token, and threshold-replay metrics. Evaluation is local and never contacts Jev.
