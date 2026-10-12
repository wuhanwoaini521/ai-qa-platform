# Delivery Plan / Milestones

1. Baseline — record actual runtime, real Provider probes, test/lint/build results, service inventory, and separately label reproduced defects vs static hypotheses. Commit baseline artifact.
2. Configuration / Provider health — test precedence and explicit operational states; preserve live credentials; confirm real AI and Jev calls without outputting secrets.
3. Worker — implement bounded concurrency, capability matching, lifecycle/recovery semantics where supported by repository architecture; add tests before each fix. Use isolated DB/workspace only because the existing DB has 200 queued jobs.
4. Worker coverage — unit/integration/real Worker tests with concurrency overlap evidence and failure/cancellation isolation.
5. Service boundaries — resolve confirmed TaskRuntime boundary regression, then extract only cohesive responsibilities with tests and stable public APIs.
6. Real failure repair — run actual AI + Jev browser-backed repair/verification path; never claim verified absent real pytest execution.
7. Security/config — assess existing credential seam and redaction; keep single-tenant scope; unify version metadata.
8. Frontend/full regression — exercise real browser UI and API-backed journey where environment allows; include omitted Web unit tests in project validation entrypoints if confirmed.
9. Independent review, run relevant suites, record all blocked checks, write report, and commit discrete milestones.

## Milestone Status

1. Baseline — **COMPLETE**, recorded and committed separately.
2. Configuration / Provider health — **COMPLETE**, real AI and Jev probes remained configured; runtime health is distinct and safe.
3. Worker — **COMPLETE** for local code/tests; bounded lifecycle and ownership protections implemented.
4. Worker coverage — **COMPLETE** for unit/concurrency tests; full acceptance intentionally blocked by the existing queued-work safety constraint.
5. Service boundaries — **COMPLETE** for verified static-boundary regression and documented repairs.
6. Real failure repair — **COMPLETE** for opt-in AI + Jev locator acceptance and browser UI path.
7. Security/config — **COMPLETE** for provider secrets/config precedence and output safety; credentials were not changed.
8. Frontend/full regression — **COMPLETE** for frontend/backend local suites and system-Chrome browser acceptance.
9. Review/acceptance — **COMPLETE** with documented environmental/data-safety blockers; see `09-final-report.md`.

Acceptance: no secrets in outputs; no existing queued job executed; no test deleted/xfail or assertions weakened; unsupported infrastructure is marked BLOCKED; only verified successful test execution may mark a repair VERIFIED.
