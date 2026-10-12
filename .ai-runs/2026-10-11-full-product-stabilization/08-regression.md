# Regression

## Final checks after all source edits

- `pnpm test`: **667 passed, 7 skipped, 44 warnings**. Backend suite: 272.39s. The task also ran 107 frontend tests, TypeScript typecheck, ESLint and production build; all passed. The PostgreSQL lane was skipped because `AI_QA_TEST_DATABASE_URL` was not configured. Build retains the existing Monaco large-chunk advisory.
- `pnpm lint`: passed. Ruff check passed; 398 Python files already formatted; i18n parity passed (25 namespaces, 2 languages, 2,865 keys); frontend ESLint passed.
- `git diff --check`: passed.

## Real-browser regression

- Authenticated Chrome at 1920×1080, 1440×900, 1366×768 and 390×844 captured Dashboard plus Workspace Requirement/Cases/Run Result/Failure views.
- After the navigation patch, all 16 Workspace Requirement/Cases/Run Result/Failure viewport captures returned HTTP 200 and had no document-level overflow.
- At 390×844, nav items measured 52px, compact labels 9px; nav scroll width 264px, client width 148px, max scroll 116px. English/Chinese labels did not clip, full aria names remained, and all five primary routes opened.
- Page/console errors: 0. HTTP 4xx/5xx/API response failures: 0. Eight active-run SSE requests were cancelled while navigating between core views; expected client aborts.

## Runtime/data check

- Read-only job counts match checkpoint: 5,004 total; 5,000 QUEUED, 4 COMPLETED. Golden Demo job rows unchanged; Worker remained OFFLINE; no Worker process was started.
- One pre-existing `test_runs` status delta: `run_51c9455dff71` transitioned RUNNING→CANCELLED during API startup stale recovery after the 7,200-second threshold. Startup log confirms it. No manual cancellation or restoration occurred.
- API/Vite stopped; ports 8000 and 5173 closed.

## Unavailable lanes / incomplete branches

PostgreSQL/Docker and Linux/Windows CI were unavailable. No Worker was run against the existing queue. Human rejection, retry-failure and Golden Demo tablet direct-refresh remain incomplete or unverified.
