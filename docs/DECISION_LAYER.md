# Decision Layer & Advisory Signal Evaluation

The Decision Layer provides a decoupled, structured choice interface isolating business modules from underlying model providers. Callers submit a state object, natural-language instructions, and dynamic candidate options; the service returns selected candidate key, confidence, probabilities, model metadata, and fallback status. The primary implementation is Jev / System One.

---

## 1. Jev Decision Provider Configuration

In Settings, the **Jev Decision Provider** can be enabled, configured with API Key, Model, Base URL, Request Timeout, and Minimum Confidence threshold:
- **Defaults**: Disabled by default; model `jev-1.13.0`, Base URL `https://api.typesafe.ai/v1/systemone`, timeout 20s, minimum confidence 0.60.
- **Connection Test**: Runs a real structured choice request.
- **Playground**: Allows testing state, dynamic options, and fallback behavior interactively.

### Key Encryption & Secrets
API keys are sent only to the server, authenticated and encrypted using Fernet before storage in the database. Responses return only configured status and masked tokens, never plain credentials. The encryption key is derived from `APP_SECRET_KEY`, so changing it invalidates previously saved Jev keys. Initial defaults can be supplied via environment variables (`JEV_API_KEY`, `JEV_ENABLED`, `JEV_MODEL`, `JEV_BASE_URL`, `JEV_TIMEOUT`, `JEV_MINIMUM_CONFIDENCE`).

Settings and decision endpoints are restricted to callers with `SECURITY_ADMIN` or authorized system tokens. When enabled, requests fallback gracefully when Jev is unavailable, times out, or returns confidence below the threshold. If candidates include `unknown`, it is chosen; otherwise an empty selection is returned and treated as undecided. Telemetry metadata is written to AI invocation records without persisting the full decision state body.

---

## 2. Separation of Regular AI vs Jev

Regular AI providers (OpenAI-compatible / Fake) for QA Assistant, requirement analysis, case generation, and failure diagnosis are configured completely independently from the Jev decision provider. They use separate database records, separate API keys, and different environment variables (`QA_AI_*` vs `JEV_*`).

---

## 3. Core API Endpoints

- `GET /api/decision/settings`: Read non-sensitive settings and status.
- `PUT /api/decision/settings`: Update settings with replacement API key or `clear_api_key: true`.
- `POST /api/decision/test-connection`: Test connectivity using current or passed credentials without persisting.
- `POST /api/decision/choose`: General structured choice endpoint.

### `choose` Request Example:

```json
{
  "name": "release_risk",
  "state": { "open_critical_bugs": 0, "coverage": 0.94 },
  "instructions": "根据发布风险选择一个结果。",
  "options": [
    { "key": "ship", "description": "允许发布" },
    { "key": "block", "description": "阻止发布" },
    { "key": "unknown", "description": "信息不足，交由人工判断" }
  ]
}
```

Upstream consumers (Recorder, Failure Diagnosis, Failure Classification, Locator Repair, Task Runtime) depend on `DecisionProvider` / `DecisionService`, keeping them decoupled from Jev-specific protocol details.

---

## 4. Decision Signal Samples & Offline Evaluation

Decision probabilities and score values are **advisory signals**. They never set test `PASS`/`FAIL` verdicts or authorize unapproved browser actions:
- **Locator Repair**: Uses a trusted same-function probability only as an Apply recommendation. A value below the configured threshold withholds Apply and reports the reason. An unavailable/fallback probability is explicitly labeled and never treated as an estimate.
- **Quality Discovery**: Uses scores only to reorder already-filtered candidates; Jev choices and deterministic browser-safety checks remain enforced.

### Offline Evaluator Tool

Run the offline evaluator against a JSON array, JSONL file, or an object containing `decision_samples`:

```bash
uv run --package api python scripts/evaluate_decision_samples.py samples.json \
  --threshold 0.75 \
  --input-cost-per-million-usd 2.00 \
  --output-cost-per-million-usd 8.00
```

### Sample Record Format

Sample fields support both flat invocation records and discovery event objects with metadata:

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

For Discovery ranking comparisons, include `selection_group`, `candidate_id`, `score`, and `expected_rank` on each candidate sample. Consistency is computed over labeled outcomes and pairwise score/rank comparisons; unlabeled samples are excluded. Abstention and fallback are reported as separate rates.

Changing `--threshold` replays only the scalar advisory boundary and reports values above/below it. It does not execute a provider, browser, test run, Apply operation, or test verdict.

### Evaluation API Endpoint

Authenticated UI clients can submit sample arrays to `POST /api/decision/evaluate-samples` with `threshold` and optional token prices. The response contains aggregate and per-decision-point consistency, abstention, fallback, latency, cost, token, and threshold-replay metrics. Evaluation is computed locally and never contacts external Jev endpoints.
