# Regression Results

Final repository check via `python scripts/task.py test`:

- Python: **733 passed, 8 skipped**; 741 collected, 56 warnings.
- Frontend: **138 passed**.
- TypeScript typecheck: passed.
- Frontend ESLint: passed.
- Production build: passed (Vite emitted its existing large Monaco chunk warning).

Final `python scripts/task.py lint`:

- Ruff check: passed.
- Ruff format check: passed (421 files formatted).
- i18n parity: passed (25 namespaces, 2 languages, 2906 keys).
- Frontend lint: passed.

`uv lock --check` and `git diff --check` passed. PostgreSQL lane skipped because `AI_QA_TEST_DATABASE_URL` was not set; optional live-browser/provider tests were not enabled. Pytest warnings were non-fatal collection/SQLite adapter/SQLAlchemy teardown warnings.
