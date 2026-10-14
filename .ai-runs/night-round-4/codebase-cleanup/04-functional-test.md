# Functional testing and validation

## Browser behavior

- Tool/browser: agent-browser **0.39.0** with system Google Chrome **150.0.7871.125** (the bundled Chrome was unusable on this host due a VideoToolbox symbol error).
- Aborted the recurrence GET once. The page showed its translated retryable error rather than the valid-empty message. After removing the interception, Retry made a real request and displayed the empty result (HTTP 200).
- Replayed an out-of-order response: two delayed requests for `fail_cbf1a3980f8e` returned a synthetic stale row after 1.5 seconds; two immediate requests for selected `fail_82b0e6ae03a4` returned `[]`. Once both completed, the selected card still showed `Similar Past Failures (0)`, with zero rows and no stale content. This exercises the request-id guard across a selection change.
- Screenshots and machine-readable results: `evidence/after/recurrence-load-error.png`, `evidence/after/recurrence-retry-success.png`, and `evidence/recurrence-error-retry-and-race.json`.
- These were read-only browser actions with intercepted GET responses. No AI/Jev action, Apply, external write, or source write occurred.

## Automated checks

| Check | Result |
|---|---|
| `uv run pytest -q` | **755 passed, 8 skipped**, 0 failed (332.50s) |
| `pnpm --filter @ai-qa/web test` | **147 passed**, 0 failed |
| `pnpm --filter @ai-qa/web typecheck` | Passed (`tsc --noEmit`) |
| `pnpm --filter @ai-qa/web lint` | Passed (`eslint .`) |
| `pnpm --filter @ai-qa/web build` | Passed; existing Monaco chunk-size warning remains |
| `uv run ruff check .` | Passed; no issues |
| `uv run ruff format --check .` | Passed; 428 files formatted |
| `uv run python scripts/i18n_check.py` | Passed; 25 namespaces, 2 languages, 2913 keys |
| Playwright version check | Resolved version is **1.62.0** |
| `git diff --cached --check` | Passed for the scoped staged source diff |

The full Python suite includes the BrowserRuntime lifecycle tests. An earlier focused Round 4 run also passed 80 browser-runtime, startup, failure-workflow, and repair-state-machine tests.

## Unavailable checks

- `docker --version` returned `command not found`; no worker image build is claimed.
- `uv run --project apps/api basedpyright ...` did not reach the checker: uv attempted to build `nodejs-wheel-binaries==24.19.0`, and that native build failed. Ruff and frontend TypeScript checks passed; this is an unavailable type-check, not a passing result.
- PostgreSQL concurrency, Linux/Windows CI, axe, and cross-browser runs were not available in this local session. The eight pytest skips were not treated as passes for those gates.
