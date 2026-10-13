# Functional testing — night round 5

## Repository checks

- `pnpm lint`: passed — Ruff check, Python format check (**428 files formatted**), i18n parity (**25 namespaces / 2,916 keys**), and ESLint.
- `pnpm test`: passed — **752 passed, 8 skipped, 0 failed** across the Python workspace; web tests **146 passed**, then TypeScript typecheck, ESLint, and Vite production build all passed.
- `mise exec -- uv run pytest -c examples/quickstart/pytest.ini examples/quickstart/tests -q`: **6 passed**.
- `mise exec -- uv run --no-sync python scripts/export_openapi.py --check`: current.
- Generated TypeScript into `/tmp` and compared it with the existing workspace artifact; exact match, without overwriting the untracked artifact.
- `git diff --check` and `git diff --check HEAD~2..HEAD`: passed.
- Runtime versions: Python **3.13.15**, Node **24.21.0**, Playwright **1.62.0**.

The full test output includes 55 warnings (pytest collection/deprecation and syntax warnings) and Vite's existing >500 kB chunk advisory. Neither caused a failure. The 8 skips include gated live AI/Jev and PostgreSQL tests; no live provider or PostgreSQL database was used.

## Isolated runtime/API journey

Started a disposable FastAPI + Vite instance on localhost ports 8002/5173 with SQLite at `/tmp/night-round-5/qa.db`; existing user services on 8001/5174 were left untouched.

- `/api/health/live`: **200**, `{"status":"alive"}`.
- Browser login and project/workspace reads: **200**.
- Reject action from the UI: `POST /api/failures/{failure_id}/analyses/{analysis_id}/reject` **200**.
- After reload: persisted `BLOCKED / HUMAN_REJECTED`, `allowed_actions=["START_ANALYSIS"]`, and `repair.rejected` event.
- Follow-up Apply request: **422**; source content remained byte-for-byte unchanged.
- The page still offered reanalysis and retained the rejected proposal/message; Apply and Reject controls were absent.
- No test execution or AI/Jev request was started.

Detailed API/browser evidence and logs are in `evidence/`.
