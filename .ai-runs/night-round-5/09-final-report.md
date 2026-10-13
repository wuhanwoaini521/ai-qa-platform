# Final project health — night round 5

## Project Health

**PARTIAL** — all executed static, automated, contract, and isolated browser/API checks passed; required independent review and PostgreSQL/cross-platform/live-provider evidence remain unavailable.

## Scope

Completed the fifth-round regression and acceptance for the remediation sequence. No round-five product-source changes were made. The primary risk surface is persisted failure repair state, generated API contracts, UI controls, and the human-approval-only source-write boundary.

## Environment

macOS; Python 3.13.15, Node 24.21.0, Playwright 1.62.0, pnpm 12.5.1. API and Vite ran on 127.0.0.1:8002/5173 against a disposable SQLite database. Existing services on 8001/5174 and persistent runtime data were left untouched. Bundled agent-browser Chrome failed on a VideoToolbox symbol mismatch; isolated system Chrome attached over CDP worked.

## Static Checks

- `pnpm lint`: passed — Ruff check, format (428 files), i18n parity (25 namespaces / 2,916 keys), ESLint.
- OpenAPI exporter `--check`: current. TypeScript schema generated to `/tmp` matched the existing artifact without overwriting workspace files.
- `git diff --check` and commit-range whitespace check: passed.

## Automated Tests

- `pnpm test`: **752 passed, 8 skipped, 0 failed** (760 Python tests); web **146 passed**, typecheck/lint/build passed.
- Documented Quickstart suite: **6 passed**.
- The 8 skips include gated real AI/Jev and PostgreSQL tests; other optional environment-gated tests also remain unverified.
- Pytest emitted 55 collection/deprecation/syntax warnings. Vite passed with its existing >500 kB chunk warning.

## Runtime Health

Disposable FastAPI readiness returned **200** (`/api/health/live`, `{"status":"alive"}`); Vite served the application title; seeded local login and project/workspace reads returned 200. The worker process was not started because the journey required no job and an unattended runner loop was outside the safe test scope.

## API / Service Verification

The UI Reject request returned **200**. After reload the API returned `BLOCKED / HUMAN_REJECTED`, only `START_ANALYSIS`, and a persisted `repair.rejected` event. A follow-up Apply request returned **422**; the test workspace source remained byte-for-byte unchanged. No test execution or AI/Jev request was started.

## Browser Verification

System Chrome exercised login, the failure workspace, dashboard, projects, and runs routes. The rejected proposal and explanation survived reload; Apply and Reject controls were absent and reanalysis remained available. Scoped axe 4.12.1 audit: **0 violations, 0 incomplete**. At 1440×900, 768×1024, and 360×800, document width equalled viewport width. Browser page-error output was empty. This was focused route/flow coverage, not a whole-app UX or WCAG audit.

## Golden Journey

Sign in to the isolated app → open a synthetic persisted failed run → review and reject its locator proposal → reload → confirm the stored decision and reanalysis action → attempt Apply → verify 422 and unchanged workspace source. All observed boundaries passed. This validates the approval-boundary journey, not the complete requirement-to-release workflow.

## Coverage Matrix

| Page / feature | Priority | Result |
|---|---:|---|
| Login | P0 | Pass |
| QA workspace / failure repair | P0 | Pass; persistence, action visibility, API denial and source integrity verified |
| Dashboard | P1 | Route loaded; synthetic fixture counters not assessed |
| Projects | P1 | Route loaded and seeded project visible |
| Runs | P1 | Route loaded; synthetic fixture counters not assessed |
| Studio, Requirements, Quality, Settings, integrations | P1–P2 | Not exercised in this browser pass |

## Issues Found

- **Environment / acceptance blocker:** independent review could not run because Orca resolution failed; not a product failure.
- **Environment:** PostgreSQL and Windows/Linux CI lanes were not run.
- **P3 build advisory:** Vite reports large Monaco/worker chunks; build succeeds and this is carried forward, not repaired in scope.
- The manually seeded dashboard run showed zero aggregate counters because the fixture bypassed the normal `TestRunService` terminal aggregation path. This is a fixture limitation, not evidence of a production counter defect.

## Root Causes

No new product failure was confirmed. The review gate's blocker is the environment's Orca launcher path. PostgreSQL row-lock behavior remains unvalidated rather than disproven.

## Fixes Applied

None in round five. The round-four functional fix is committed as `652736b fix(failures): persist human repair rejection`; its evidence/report is `b88bead docs: record round-four rejection evidence`.

## Regression Result

Executed Python workspace and frontend suites, lint/format/i18n, build/typecheck, Quickstart, OpenAPI contract/type parity, isolated runtime/API, browser Reject/reload/Apply-denied flow, responsive checks, and scoped accessibility audit. All executed checks passed. See `08-regression.md` and `evidence/` for commands and outputs.

## Unverified Areas

PostgreSQL concurrency/locking; Windows and Linux execution; live AI/Jev acceptance in this round; worker runtime; full requirement-to-release journey; and remaining product routes/page states. Prior-round AI/Jev acceptance is carried forward, not re-claimed as round-five evidence.

## Remaining Risks

The key unresolved acceptance risk is the missing independent reviewer. SQLite evidence does not establish PostgreSQL row-lock behavior. Large frontend chunks may affect load performance; no performance measurement was run.

## Git Status

The round-four source and evidence commits are preserved. Inherited modified and untracked work remains in the worktree, including `mise.toml`; it was not overwritten or broadly staged. No round-five application source was changed. Round-five validation artifacts are committed separately. No push was performed.

## Final Verdict

**PARTIAL** — required independent review remains blocked; PostgreSQL, cross-platform, and live AI/Jev gates were not completed.
