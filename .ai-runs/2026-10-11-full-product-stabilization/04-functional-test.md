# Functional Testing

## Real browser

- Command: `uv run python /tmp/aiqa_nav_after.py`
- Result: PASS. Authenticated real Chrome loaded the Dashboard at 1920×1080, 1440×900, 1366×768 and 390×844; all four screenshots were captured at their requested dimensions.
- Post-change mobile metrics: 9px label text, 52px item width, 148px visible nav width, 264px nav scroll width, 116px maximum horizontal scroll. All five primary navigation routes were opened successfully at 390×844. Compact English and Chinese labels were unclipped; full accessible names were retained. At all four viewports document width equaled viewport width.
- The first 50px sizing-only iteration clipped English `Dashboard` and `QA Workspace`; compact localized mobile labels were then added, with full names preserved for accessibility. A test-helper call initially used a positional Playwright argument and was corrected; no product fault was involved.
- Browser page/console errors: 0; HTTP 4xx/5xx/API response failures: 0. Two active-run SSE requests were client-aborted when navigating away, as expected.
- All 16 core Workspace Requirement/Cases/Run Result/Failure screenshots were recaptured at four viewports after the final navigation change; all routes returned HTTP 200 and no viewport had document overflow. The final four-view screenshot sweep cancelled eight active-run SSE requests while navigating between pages; these were expected client aborts.
- The first harness attempt tried to scroll to platform links intentionally hidden by the existing mobile CSS and timed out. The check was narrowed to the five primary mobile links (the change's scope); all five passed. No product change was made for this unrelated mobile platform-menu behavior.

## Automated checks after all navigation and locale edits

- `pnpm --filter @ai-qa/web test`: 107 passed, 0 failed.
- `pnpm test`: **667 passed, 7 skipped, 44 warnings**; backend suite completed in 272.39s. Frontend tests, typecheck, ESLint and production build also passed. PostgreSQL lane was skipped because `AI_QA_TEST_DATABASE_URL` was not configured. Build retained the existing Monaco large-chunk advisory.
- `pnpm lint`: passed; Ruff checks passed, 398 Python files already formatted, translation parity passed for 25 namespaces / 2 languages / 2,865 keys, frontend ESLint passed.
- `git diff --check`: passed.

## Preservation check

Read-only SQLite check after stopping browser services: 5,004 jobs total, 5,000 QUEUED and 4 COMPLETED; no jobs changed. `run_51c9455dff71` was RUNNING at checkpoint and became CANCELLED at API startup once older than the 7,200-second recovery threshold (`finished_at=04:22:44.647233`). `/tmp/aiqa-mobile-nav-workspace.log` confirms the automatic recovery; no manual cancellation/restoration occurred. No Worker was started. Ports 8000 and 5173 were closed after verification.
