# Regression Results

- Final `python scripts/task.py test`: **711 passed, 8 skipped**; includes API, qa-core, integrations, and worker suites.
- Frontend tests: **138 passed**; typecheck, ESLint, production build passed.
- Final `python scripts/task.py lint`: Ruff check/format, i18n parity, and frontend lint passed.
- `uv lock --check` and `git diff --check` passed.
- Focused signal/discovery/locator/budget tests: **44 passed**.

Known environment skips: PostgreSQL lane requires `AI_QA_TEST_DATABASE_URL`; live browser and real Jev service checks require explicitly configured external credentials/targets. No real Jev key was available, and no external service was called. The Vite build emitted a large Monaco chunk advisory but succeeded.
