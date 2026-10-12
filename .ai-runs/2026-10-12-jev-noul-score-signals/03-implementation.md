# Implementation

- Added `DecisionSignalRequest` and probability/score values to shared decision models; expanded Jev provider protocol with `ask_probability` and `ask_score` while retaining choice requests.
- Refactored Jev HTTP transport/retry classification once and implemented TypeSafe `noul` and `score` questions with strict finite scalar parsing.
- Added DecisionService signal flow with state redaction, request-size/daily/task budgets, timeouts, minimum-confidence fallback, telemetry and explicit `provider="fallback"` results. Optional Discovery scores reserve one daily call for mandatory action choice.
- Added nullable `decision_value` invocation persistence and migration `0009_decision_signal_values`.
- Locator Repair now requests same-function probability for a trusted selected candidate. Low trusted values produce `LOCATOR_IDENTITY_BELOW_THRESHOLD`, an explicit trace/summary, and no proposal/Apply. Fallback/unavailable values are marked unavailable and are not interpreted as probabilities.
- Discovery scores only already-filtered candidate IDs and uses trusted Jev scores to reorder priority; the existing Jev choice and safety checks remain authoritative.
- Added offline evaluator service, `scripts/evaluate_decision_samples.py`, authenticated `POST /api/decision/evaluate-samples`, UI DTO types, and `docs/DECISION_SAMPLE_EVALUATION.md`. The evaluator accepts flat invocation samples or Discovery event metadata and replays thresholds without network or browser actions.
- Discovery score events and Locator summaries carry decision point, candidate/probability, confidence, provider/fallback, latency, and available token usage for offline analysis. Fallback/invalid recommendations are recorded as unavailable and never alter ranking or safety decisions.
- Added provider, budget, telemetry, evaluator, Discovery ranking, and Locator Apply threshold tests. Existing browser-agent budget test covers no browser action after exhausted required Jev budget.
- No source changes were staged; no commit or push.
