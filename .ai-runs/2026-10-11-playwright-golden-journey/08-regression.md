# Regression

## Passed
- `uv run pytest`: full Python suite **666 passed, 7 skipped**. Pytest emitted non-failing warnings; the warnings were not all independently triaged for this acceptance run.
- `pnpm --filter @ai-qa/web test`, `typecheck`, `lint`, and `build`: passed. Vite reported its existing large-chunk advisory during build; build exit status was successful.
- `uv run ruff check <all changed Python files>`: passed.
- `uv run ruff format --check <all changed Python files>`: passed; 21 files already formatted.
- `uv run python scripts/i18n_check.py`: passed (25 namespaces, 2 languages, 2,859 keys).
- `git diff --check`: passed.
- Real Chrome shop behavior: `examples/demo-shop/tests/test_shop.py` **8 passed**. System Chrome was used because Playwright's bundled Chromium executable was unavailable. The deliberately stale locator test remains a pre-repair failure fixture in the checked-in example.
- Golden Demo's reviewed/approved repaired workspace suite: **10/10 passed**, recorded as `run_92a613c81881`; generated case `run_1b850d74579d` and exact repaired case `run_eb4ccaf35252f5440324e6f938cbeb7d` also passed.
- Golden Demo Worker was stopped and is `OFFLINE`; the unrelated queued-job count remained 200.

## Not run / incomplete
- PostgreSQL lane: unavailable because Docker/PostgreSQL were unavailable; SQLite was healthy.
- Human rejection branch: unsupported by inspected workflow UI/API, not exercised.
- Retry-failure branch: incomplete.
- Tablet direct-refresh behavior: not independently verified.
- Build-size advisory and non-failing pytest warnings were not investigated as separate product issues.
