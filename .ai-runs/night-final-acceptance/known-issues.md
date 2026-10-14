# Known Issues and Open Gates — Night Final Acceptance

## Product/configuration follow-up

1. **P2 — Disabled AI/Jev configuration returned HTTP 500.** In the first disposable setup, the harness explicitly set AI/Jev disabled; `/api/ai/status`, `/api/runs`, and `/api/failures` returned 500 during AI-dependent service construction. The subsequent run used the configured real providers and passed. No product fix was made. If provider-disabled mode is supported, those routes should report an unavailable/disabled state rather than crash. This was not observed under the current configured real-provider mode.

## Environment / acceptance blockers

2. **PostgreSQL is unverified.** `AI_QA_TEST_DATABASE_URL` is unset and `docker`, `psql`, and `pg_isready` are unavailable. PostgreSQL-marked tests were skipped; SQLite evidence does not validate PostgreSQL locking/concurrency.
3. **Independent review is blocked.** Orca could not resolve `/usr/local/bin/orca`; no independent reviewer result exists. See `independent-review.md`.
4. **Windows/Linux lanes were not run.** This host is macOS.
5. **No separate remote Worker service/token was available.** Worker package unit tests passed and API-local execution was available; a deployed/remote Worker lane was not exercised.
6. **Human-approved Apply/post-approval verification remains intentionally blocked.** The real AI + Jev workflow stopped at `PATCH_READY`; no Apply was invoked and no approval was simulated.

## Non-blocking operational advisories

7. **Python LSP unavailable.** Platform health marked this component `warning` and overall health `degraded`; local execution and DAP debugging worked.
8. **Large frontend chunks.** Vite warned that Monaco/worker chunks exceed 500 KB. The production build passed; no bundle-performance measurement was run.
9. **Existing test warnings.** The full suite emitted 55 pytest collection/deprecation/syntax warnings, with no failures.
10. **Host browser mismatch.** Bundled Chrome failed due a VideoToolbox symbol incompatibility on this macOS host. System Chrome 150 worked with Playwright 1.62.0; this is a host-specific setup risk, not a newer Playwright dependency.
11. **Synthetic demo favicon 404.** The disposable demo page does not provide a favicon; its 404 appeared in browser telemetry but did not affect the flow.

## Summary

No P0/P1 product failure was confirmed on the configured real-provider path. Final acceptance is **PARTIAL** until the independent-review, PostgreSQL, cross-platform, remote Worker, and approval-dependent gates are addressed.
