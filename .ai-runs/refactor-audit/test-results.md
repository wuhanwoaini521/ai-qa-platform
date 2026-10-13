# Test and Tool Results

## Automated suites

- `UV_NO_SYNC=1 ./scripts/test`: **PASS** — SQLite backend `738 passed, 8 skipped, 55 warnings` in 326.47s; frontend `145 passed, 0 failed`; TypeScript `tsc --noEmit`, ESLint, and production build passed.
- `UV_NO_SYNC=1 ./scripts/lint`: **PASS** — Ruff checks, Ruff format check (426 files), translation parity (25 namespaces / 2 languages / 2,909 keys), and frontend ESLint.
- `git diff --check`: **PASS**.
- The production Vite build emitted its existing large-chunk warning (Monaco editor bundle); it still completed successfully.

## Not passed / unavailable

- Opt-in `AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1` test `test_live_ai_jev_repair_requires_approval_and_exact_rerun`: **FAIL / unresolved**. It asserted that `analysis.result.automatic_triggered` was true while the analysis remained `RUNNING`; no completed workflow result was available. A standalone Jev decision call passed but does not clear this failure.
- PostgreSQL lane: **SKIPPED** by `scripts/test`; `AI_QA_TEST_DATABASE_URL` is unset and PostgreSQL/container services are unavailable.
- `uv sync --all-packages --locked` could not build the environment because the `nodejs-wheel-binaries` package build failed on this host. Tests/lint were run with `UV_NO_SYNC=1` against the existing environment; active Playwright was aligned to required `1.62.0`.

The isolated UI workspace test separately completed its bound browser test **PASSED · 1/1**. It validates the local product flow, not real AI/Jev repair; see `feature-validation.md`.
