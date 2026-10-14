# Regression Results — Night Final Acceptance

## Summary

| Check | Result |
|---|---|
| Full Python/backend/package/Worker suite | **755 passed, 8 skipped, 55 warnings** |
| Frontend tests | **147 passed** |
| Web typecheck, ESLint, production build | **PASS** |
| Ruff, format, translation parity | **PASS** |
| OpenAPI exporter `--check` | **PASS** |
| Quickstart focused suite | **4 passed** |
| PostgreSQL lane | **BLOCKED / skipped** — no test URL or local PostgreSQL tooling |
| Cross-platform lanes | **NOT RUN** — macOS only |
| Independent review | **BLOCKED** — Orca launcher error |

## Commands and Results

1. `python scripts/task.py test`
   - Python: **755 passed, 8 skipped, 55 warnings** in 331.03s (763 collected).
   - Web unit tests: **147 passed**.
   - Web typecheck, ESLint, and Vite production build passed.
   - PostgreSQL lane skipped because `AI_QA_TEST_DATABASE_URL` is unset. The eight skips include environment-gated live-provider/browser, PostgreSQL, and optional integration tests.
   - Build warning: Monaco/worker chunks exceed Vite's 500 KB advisory threshold; build succeeded.
2. `python scripts/task.py lint`
   - Ruff check passed; 428 files already formatted.
   - Translation parity passed: 25 namespaces, 2 languages, 2,913 keys.
   - Frontend ESLint passed.
3. `uv run --no-sync python scripts/export_openapi.py --check`
   - OpenAPI contract current. TypeScript schema generated into `/tmp` matched the checked-in generated schema exactly; the repository artifact was not overwritten.
4. `uv run --no-sync pytest -q packages/qa-core/tests/test_quickstart_example.py`
   - **4 passed in 1.98s**.

## Functional and Runtime Evidence

- Disposable API readiness: HTTP 200; SQLite DB and artifact storage reported OK.
- Existing API `:8001` live/readiness and Vite `:5174` returned HTTP 200 before and after the run.
- Real AI status and Jev system-health probes succeeded; see `ai-jev-validation.md`.
- UI Golden Journey created a synthetic project, requirement, case, and active binding for `tests/test_cart.py::test_checkout_order`.
- Intentional failure: run `run_1cdb55beb13c`, FAILED because `#checkout-now` was absent. Failure summary, browser action telemetry, source location, and screenshot were captured.
- Debugger: DAP session paused at `test_checkout_order:13`, step-over reached the `finally` cleanup line, then continue completed the failed test.
- Recovery: corrected the selector in the disposable workspace, then run `run_9a80fded75ac` passed; bound-case run `run_b243bb10a461` passed. Case history showed 2 passes / 1 intentional failure.
- Responsive check: document width equalled viewport width at 360×780, 768×1024, and 1440×900.
- Evidence screenshots are under `evidence/`; real AI/Jev UI evidence is under `evidence/ai-jev-browser/`.

## Focused Coverage Within the Full Suite

The passing full suite includes architecture boundaries; database lifecycle/migrations; OpenAPI; Quickstart and timeout behavior; runtime events, event cursors, cancellation, reconnect and terminal-state handling; BrowserRuntime expiry/crash/restrictions; DAP pause/step/locals/continue; failure repair approval/state transitions; and Worker unit tests.

## Skips, Warnings, and Limits

- PostgreSQL integration tests were skipped; SQLite is not a substitute for PostgreSQL locking/concurrency evidence.
- No separate Worker service or configured worker token was available; only API-local execution and Worker package tests were exercised.
- Windows/Linux lanes and independent review were unavailable.
- Pytest emitted 55 collection/deprecation/syntax warnings. No test failed.
- The build emitted a large Monaco/worker chunk warning. No bundle performance measurement was run.
