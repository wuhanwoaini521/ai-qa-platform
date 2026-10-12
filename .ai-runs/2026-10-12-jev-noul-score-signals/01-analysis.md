# Analysis

## Existing architecture

- `JevDecisionProvider.choose` already sends TypeSafe `/v1/systemone` choice questions.
- `DecisionService.choose` owns config, redaction, token/daily/task budget, timeout, minimum-confidence fallback, and AI invocation telemetry.
- Locator Repair uses `LocatorDecisionService` for Jev candidate choice and Playwright verification; `FailureService.generate_repair_proposal` persists trusted proposal/Apply metadata.
- Quality Discovery filters action candidates deterministically, then sends a shared `DecisionService.choose` request before any browser action.
- The architecture invariant says AI must not decide test PASS/FAIL or bypass deterministic safety checks.
- Existing browser-agent test `test_browser_agent_blocks_when_task_jev_budget_is_exhausted` already asserts provider call count zero and no `browser.action_started` event after task-budget exhaustion.

## Implementation plan

1. Add a scalar signal request/result contract and Jev `noul`/`score` question methods; retain `choose` and share transport/retry/error classification.
2. Reuse DecisionService budgets, redaction, timeout, confidence, fallback, and telemetry. Persist scalar values as invocation telemetry.
3. Ask for same-function probability only after Locator Repair has a trusted selected candidate. A trusted low probability withholds Apply and explains why; unavailable/fallback signals are explicitly reported and never treated as evidence.
4. Use Jev scores only to reorder already-filtered Discovery candidates. Preserve one daily request for mandatory action choice; keep deterministic safety checks and choice step authoritative.
5. Add pure offline sample evaluation, threshold replay, JSON/JSONL CLI, and authenticated evaluation API with UI DTO types.
6. Add provider/service/integration tests, run targeted then broader regressions, and perform a structured second-pass code review.

## Risks and controls

- Provider response shape: validate answer type and finite [0,1] values; invalid/missing confidence/value falls back.
- Secrets: no key means provider rejects before creating HTTP client; state is redacted before Jev; evaluation returns metrics only and redacts labels/IDs.
- Budget: score requests reserve below the daily limit to leave the last request for deterministic action selection; existing task-local budget test covers zero browser actions.
- Compatibility: add nullable signal fields and an additive Alembic migration; preserve existing choice request/payload behavior.
- Threshold semantics: threshold replay is advisory only; no provider/browser/PASS/FAIL execution occurs during evaluation.
