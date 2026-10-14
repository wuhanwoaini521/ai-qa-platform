# Regression results

- Full platform Python suite: `uv run pytest -q` — **755 passed, 8 skipped, 0 failed** (332.50s).
- Web suite: **147 passed**; TypeScript typecheck, ESLint, and production build passed.
- Python Ruff check/format and translation parity passed.
- Real-browser recurrence error/retry and stale-response scenarios passed in system Chrome. See `04-functional-test.md` and `evidence/recurrence-error-retry-and-race.json`.
- Playwright remains resolved to **1.62.0**; the worker image was not built because Docker is unavailable.

## Unrun regression lanes

PostgreSQL concurrency, Windows/Linux CI, axe, cross-browser, and live AI/Jev acceptance were not run. They are not reported as passing. No known functional regression remains in the executed local suites.