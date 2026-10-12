# AI QA Platform V2 overhaul — regression

## Coverage and results

- **Frontend callers:** full web unit suite (137 passed), lint, typecheck, and production build passed. Shared project labels exercise Navigation, Studio selector, Projects, Runs, Tasks, Settings, requirement/case forms, and Workspace consumers; no route or API contract changes.
- **Task/run state:** unit states cover task-only completion/failure/blocked/cancelled, active task, idle, and real TestRun precedence. Real browser shows task complete separately from a passed TestRun and retains case context.
- **Responsive UI:** system Chrome at 1440/768/390 for Projects; Run Dock at 1440/768/390 in dark theme. Project table width remains internal; keyboard navigation verified. English/Chinese labels checked.
- **Backend/workspace suite:** `uv run --no-sync pytest -q` — 669 passed, 7 skipped. Ruff check and format check passed. SQLite suite only; PostgreSQL URL absent.
- **Live sandbox journey:** real AI + Jev analysis, binding, real single-case run, persisted 1/1 PASS. Existing Golden Demo run `run_1a8bf6d5a021` remains 7 passed / 1 failed; its TC-002 expectation mismatch was not changed.

## Not covered / blockers

- PostgreSQL lane: not run; `AI_QA_TEST_DATABASE_URL` unset.
- Linux/Windows CI, Firefox/WebKit, full screen-reader acceptance, physical devices, video recording: not run.
- Python language service: modules absent in active environment; safe sync unavailable, so no LSP success regression can be claimed.
- Dashboard: measured stats response and visual timing, but no profiling/fix.
- Build emits the existing large Monaco worker chunk warning; build itself succeeds.

No unrelated backend regression was observed. Existing warnings from pytest are recorded in the command output; no suite failure occurred.
