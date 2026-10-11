# Architecture Audit — Nightly Platform Improvement

**Date:** 2026-10-11
**Baseline:** `cdf954a` on `agent/nightly-platform-improvement`; working tree contains a broad, uncommitted product change set. This is a scoped architecture review of the current source, not a security certification or a claim that every integration is production-ready.

## Executive assessment

**Overall: PARTIAL / B. No new P1 defect was confirmed in the reviewed scope.** The application has a useful modular-monolith shape: the React client calls FastAPI contracts, API routes generally delegate to application services, browser behavior has a `BrowserRuntime` port, and test execution is separated into API and Worker paths. Existing real AI + Jev acceptance tests and this run's automated regression support those boundaries.

The primary remaining risks are oversized orchestration services, optional rather than default Worker project isolation, incomplete PostgreSQL/cross-platform validation, and workflow state/persistence coupling. The architecture is maintainable enough for current scoped delivery, but the large services make future changes and independent testing expensive.

## Boundary review

| Boundary | Assessment | Evidence / caveat |
|---|---|---|
| Web → API | **Good** | Route components use API clients and typed DTOs; run progress uses the event stream. Accessibility fixes add a single shared `main` landmark rather than changing route ownership. This was not a contract-by-contract API compatibility audit. |
| Page → workflow | **Good / bounded** | Failure actions are displayed from backend state and allowed actions; UI presentation helpers do not authorize repair. Low-confidence Discovery candidates are skipped without execution, and later candidates remain eligible. |
| API → application | **Good** | Routers primarily validate requests, inject services, and map responses; workflow and run behavior resides in services. No broad router-to-ORM rewrite was attempted. |
| Application → infrastructure | **Mixed** | `BrowserRuntime` is a useful port and Playwright is behind an adapter. Some large services still coordinate browser work, ORM sessions, persistence, provider calls, and state transitions directly. |
| AI / Jev / execution safety | **Good, acceptance is opt-in** | AI diagnoses and Jev chooses; Playwright verifies locators and pytest remains the deterministic oracle. The real acceptance path passed without fallback. Confidence thresholds and approval rules were not relaxed. |
| Worker scheduling | **Needs operational hardening** | Claims can be constrained by project IDs, but `WORKER_PROJECT_IDS` is optional; an unset value retains global-claim behavior. Never point an unscoped Worker at a shared/benchmark queue. |

## Prioritized findings

### P2 — Decompose orchestration hotspots

Current source sizes are substantial: `QualityDiscoveryService` is about 4,550 lines, `TaskBrowserExecutor` about 3,102, and `FailureWorkflowService` about 1,652. They combine orchestration with concerns such as browser actions, policy, persistence, provider calls, and workflow state. This raises review and regression cost even though focused tests pass.

**Recommendation:** extract pure candidate/policy logic first, then separate persistence adapters and browser-action orchestration behind narrow interfaces. Keep the public service contract stable and add state-transition tests before moving behavior. Do not do a broad rewrite as part of an unrelated bug fix.

### P2 — Make Worker project isolation fail closed

The Worker supports `WORKER_PROJECT_IDS`, and the API/repository can filter claims, but the environment variable is optional. An unconfigured Worker may claim any eligible queued project job. This is hazardous in a shared runtime database, as demonstrated by the 5,000 unrelated queued jobs present during the audit.

**Recommendation:** decide and document the production policy; prefer a required allowlist for shared environments, with an explicit, audited opt-in for global workers. Add API/Worker tests for unset, empty, and configured allowlists. No Worker was started in this audit.

### P2 — Verify persistence and concurrency on PostgreSQL

Local regression uses the available environment and skips the PostgreSQL lane unless `AI_QA_TEST_DATABASE_URL` is configured. SQLite results do not establish PostgreSQL locking, transaction isolation, or concurrent job-claim behavior.

**Recommendation:** run the PostgreSQL lane and concurrent claim tests in CI with a disposable database. Keep production queue data isolated from acceptance tests.

### P2 — Reduce workflow state/persistence coupling

Failure-repair state is represented across workflow records, analysis results, proposals, and run associations; the existing architecture audit also notes read/reconciliation paths that can write state or events. This is workable, but it increases the need for explicit idempotency and concurrency contracts.

**Recommendation:** document transition invariants and idempotency keys, then add concurrent retry/reconciliation tests before introducing a normalized state machine or schema migration.

### P3 — Separate implemented capabilities from roadmap claims

`docs/ARCHITECTURE.md` presents a broad phase capability matrix alongside future integrations. Readers may interpret roadmap capabilities (for example, external Jira/TestRail/GitHub flows) as fully accepted runtime behavior.

**Recommendation:** mark each capability as implemented, partial, planned, or not validated, and link to its acceptance evidence.

## Verified strengths and this run's changes

- Headless Playwright sessions use a standards-shaped Chrome user agent rather than changing transport settings to mask site compatibility issues; targeted browser runtime tests pass.
- Discovery marks low-confidence candidates skipped and continues without executing them or lowering confidence requirements; focused tests cover the behavior.
- Provider failures in operation traces use vendor-neutral messaging.
- AI/Jev locator repair requires a real decision, confidence-policy compliance, Playwright verification, and exact pytest rerun; the two explicit live acceptance cases passed earlier in this run series.
- Browser-facing pages use one shared main landmark; repair/result headings were corrected to avoid a skipped heading level.

## Regression and acceptance boundary

- Full local suite: **669 passed, 7 skipped, 44 warnings**; PostgreSQL lane skipped because `AI_QA_TEST_DATABASE_URL` is unset.
- Root lint and i18n parity: pass. Web typecheck/build: pass; build keeps its existing large Monaco chunk advisory.
- Python `basedpyright` is not installed in the configured environment; Python editor/language-service analysis was therefore not independently completed. An earlier full `uv sync --all-packages --locked` attempt is blocked by the macOS `nodejs-wheel-binaries` build issue; this audit did not repeat that environment-changing sync.
- Real AI/Jev tests are explicit opt-ins, not included in the ordinary suite. Their prior results are reported separately; they do not prove rejection, retry-failure, PostgreSQL, or cross-OS behavior.

## Conclusion

The reviewed boundaries are adequate for scoped changes and the tested workflows remain fail-closed. The top architecture follow-ups are Worker allowlist policy, PostgreSQL concurrency acceptance, and incremental decomposition of the largest services. No claim of full enterprise readiness or complete architecture/security audit is made.
