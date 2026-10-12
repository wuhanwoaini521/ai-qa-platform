# Functional Test Results

## Focused tests

- Decision signal/provider/budget/telemetry and sample-evaluation coverage, Discovery ranking/fallback, Locator threshold and evidence workflow, and required-budget browser guard: **44 passed**.
- No real Jev key was configured; provider HTTP behavior was validated with mocked transport. The offline evaluator and API do not invoke Jev, a browser, or Apply.
- API and worker package environments both import `cryptography` (50.0.1). A non-secret API/worker `app.secret_key` encrypt/decrypt round-trip passed; no key material was printed.

## Full repository regression

`python scripts/task.py test` — **711 passed, 8 skipped**, 719 collected (330.34s).

- Frontend unit tests: **138 passed**.
- Frontend typecheck, lint, and production build: passed.
- PostgreSQL-specific lane skipped because `AI_QA_TEST_DATABASE_URL` is not configured. Optional live browser/locator tests also skipped; no external target was contacted.
- Vite reported the large Monaco/editor bundle warning (>500 kB); build completed successfully. Pytest emitted collection/fixture warnings and one non-fatal SQLAlchemy connection-teardown warning in the failure-workflow suite; the targeted low-probability Locator test passed alone with SQLAlchemy warnings treated as errors.

## Static and workspace checks

`python scripts/task.py lint` — Ruff check/format, translation parity (25 namespaces, 2 languages, 2906 keys), and frontend ESLint all passed.

`uv lock --check` and `git diff --check` passed.
