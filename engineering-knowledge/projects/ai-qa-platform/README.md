# AI QA Platform — Project-Specific Knowledge Links

Project-specific implementation and test evidence is kept separate from generic shared patterns. This file intentionally contains no credentials, customer records, sensitive logs, or copied private source.

- Architecture source audit and boundaries: [`docs/architecture-review/current-state.md`](../../../docs/architecture-review/current-state.md).
- Candidate target, decisions and deferred gate: [`docs/architecture-review/architecture-decisions.md`](../../../docs/architecture-review/architecture-decisions.md), [`docs/architecture-review/target-architecture.md`](../../../docs/architecture-review/target-architecture.md).
- Official P0 framework verification: [`docs/architecture-review/framework-p0-verification-2026-10-28.md`](../../../docs/architecture-review/framework-p0-verification-2026-10-28.md).
- Existing-runtime fixture PoC and limits: [`docs/architecture-review/poc-results.md`](../../../docs/architecture-review/poc-results.md); raw safe test evidence is under `experiments/architecture-review/poc/`.
- Current architecture gate status: **DEFERRED / NOT PASSED**. No framework is approved for production.
- Execution change scope: stale Quality Discovery startup recovery must not regress a newer state or publish a pause event that was not durably recorded. The local SQLite evidence and PostgreSQL gap are in [`patterns/conditional-recovery.md`](../../patterns/conditional-recovery.md).
