# Plan

- [x] Extend shared Decision models/provider protocol and Jev `/v1/systemone` scalar request parsing.
- [x] Implement DecisionService signal budget, timeout, confidence, fallback, logging, and value telemetry.
- [x] Connect Locator same-function probability recommendation and Apply threshold explanation.
- [x] Connect Discovery score as bounded ranking advice while preserving one daily request for action choice.
- [x] Add invocation schema migration and DTO support.
- [x] Add pure sample evaluator, CLI, API, UI TypeScript types, and usage documentation.
- [x] Add unit/integration coverage including low-identity Apply block, budget denial before provider call, no-key no-network, and Discovery score-only reordering.
- [x] Final full regression, lint/typecheck, diff review, and acceptance report.

Acceptance criteria: existing `choose` behavior remains; scalar failures return `provider="fallback"`; Jev signals never determine test PASS/FAIL or deterministic browser safety; low trusted locator identity probability withholds Apply with a reason; Discovery scores only reorder prefiltered candidates; offline evaluation reports consistency, abstention, fallback, latency, cost and threshold replay without contacting Jev; budget exhaustion produces no browser action.
