# Repository analysis

## User outcome and acceptance

Make the existing platform reliable and convenient across its principal QA lifecycle without expanding the feature set or breaking user data/API contracts. Acceptance requires real evidence for the requested pages and journeys, not only source inspection or mocked tests:

1. Create and retain a unique requirement, case, automation binding/script, successful run, and visible result.
2. Reproduce a Playwright failure, inspect its evidence, correct the script, rerun successfully, and retain history.
3. Where live AI/Jev credentials and a valid repair scenario are available, obtain and apply a confidence-qualified repair and verify the rerun; otherwise record the exact environment/product blocker.
4. Exercise Studio editing, execution, browser, logs, debugger, and failure handoff; revisit history after navigation/reload.
5. Cover Dashboard, Projects/Workspace, Requirements, Test Cases/Explorer, Automation Studio, Runs/results, Live Browser/Recorder, Debugger, Failure Analysis/AI Repair, AI/Jev settings, and configuration/health screens in a real browser; report page-level coverage.
6. Run appropriate web/backend/API/persistence tests, final code review, responsive checks, and a final regression on the completed tree. Commit only task-owned changes in categories and push only the task branch.

## Architecture / execution context

- React 19 + TypeScript + Vite web client (`apps/web`); FastAPI API (`apps/api`); worker (`apps/worker`); shared project and QA contracts in `packages/`.
- `scripts/task.py` defines cross-platform setup/dev/test/lint/build. `pnpm test` runs pytest plus frontend test/typecheck/lint/build; PostgreSQL rerun is conditional on `AI_QA_TEST_DATABASE_URL`.
- Existing web/API services are reachable at `127.0.0.1:5173` and `127.0.0.1:8000`; health endpoints report API/database/storage ready. `docker` is not installed in this shell. `.env` exists but values are intentionally not read or logged.
- Shell environment does not export AI/Jev keys or a PostgreSQL test URL. Existing API process may load local configuration; actual provider availability must be checked through safe status/real operations, not inferred from this shell.
- Playwright/Chromium browser tooling is installed; `agent-browser doctor --offline --quick` passes with a warning that `ffmpeg` is absent (video recording only).

## Constraints / impact / risk

- HIGH risk: broad cross-module workflow spans persisted requirements/cases, workspace files, worker execution, failure evidence, AI/Jev repair, authentication, and frontend navigation.
- Preserve all 16 tracked worktree changes and untracked existing artifacts. Do not run setup/sync, migrations, Docker commands, cleanup, or database resets against the live environment without a demonstrated need and safe isolation.
- No weakening of assertions, confidence thresholds, auth, or execution verdicts; no mocks/fallbacks counted as real integration passes.
- Keep API and persisted-data contracts stable. New acceptance data must use a separately named project/artifacts; no deletion of existing records.
- Browser screenshots and network evidence must avoid exposing credentials. Store screenshots/report under this run or a task-specific report folder.

## Unknowns to resolve through evidence

- Whether the already-running app is authenticated and which data/storage backend it uses.
- Which top-level modules and the five requested real-world scenarios are currently usable.
- Whether configured AI + Jev providers are reachable in the running service and whether a safe reproducible locator repair target exists.
- Whether local PostgreSQL is available despite Docker being unavailable.
- Any concrete failures, their reproduction, and root causes; no defect is presumed before browser/API evidence.
