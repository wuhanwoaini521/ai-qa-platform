# Full Product Test Results

**Audit date:** 2026-10-11
**Code baseline:** current worktree at `main` / `cdf954a`, including pre-existing changes and the final mobile-navigation refinement in `apps/web/src/index.css`, `apps/web/src/components/Navigation.tsx` and both nav locale dictionaries. Final regression ran after all source edits.

## Automated regression

| Check | Result | Notes |
|---|---|---|
| `pnpm test` | **PASS — 667 passed, 7 skipped, 44 warnings** | Fresh final run of the backend/core/Worker and frontend test task on current source. Warnings were non-failing and not all independently triaged; skipped tests remain skipped. |
| `pnpm lint` | **PASS** | Ruff; 398 Python files already formatted; translation parity; frontend ESLint. |
| `pnpm --filter @ai-qa/web typecheck` | **PASS** | TypeScript check. |
| `pnpm --filter @ai-qa/web build` | **PASS** | Production build succeeded; the existing Monaco large-chunk advisory remains. |
| `uv run python scripts/i18n_check.py` | **PASS** | 25 namespaces, 2 languages and 2,865 keys. |
| `git diff --check` | **PASS** | No whitespace errors in the tracked diff. |

No product-source edits occurred after these checks. Documentation/evidence files and runtime test artifacts do not affect the compiled or tested application source.

## Live API and provider verification

- `GET /api/health/live` — HTTP 200, `alive`.
- `GET /api/health/ready` — HTTP 200, `ready`, database `ok`, storage `ok`.
- Web `/` — HTTP 200.
- AI Settings connection test — HTTP 200, connected to `openai-compatible / deepseek-flash`; structured JSON probe succeeded.
- Jev Settings connection test — HTTP 200, connected, model `jev-1.13.0`.
- Jev runtime check — `CONNECTED / READY`, enabled, budget available, no reasons.
- Jev Playground — `choice=preserve_read_only`, confidence `1.0`, provider `jev`, `fallback_used=false`.

## Real browser/runtime verification

Browser: installed system Chrome; authenticated against the local app. The route sweep covered Dashboard, Projects/Project Overview, Requirement, Cases, Automation Studio, Run Results, Recorder, Debugger, Failure/Repair, Workflow, Library, Runs, Quality, Quality Discovery, Workers, Settings, Security, Flaky, and compatibility routes.

- Dashboard and Workspace Requirement/Cases/Results/Failure views were checked at **1920×1080, 1440×900, 1366×768 and 390×844**. All stable after-state captures report no document-level horizontal overflow.
- Final mobile-navigation review at 390×844 measured localized 9px primary labels in 52px items (before: 8px / 42px), 148px visible nav width and 264px scroll width. Compact English/Chinese labels were unclipped, full accessible names were preserved and all five primary routes opened correctly. The same Dashboard before/after screenshots are available at all four viewport sizes. Workspace Failure/Results was also re-captured at 1440×900 and 390×844; both returned HTTP 200 with no document overflow.
- Targeted runtime flows had **zero page/console errors and zero HTTP 4xx/5xx/API response failures**.
- Navigation away from active run views cancelled two run-event SSE requests during the targeted route check and eight during the final 16-screenshot Workspace sweep; these expected client-side aborts were not HTTP failures.
- Recorder rendered a live frame from the local Demo Shop and was closed without a user action, case save or source write.
- Debugger ran `tests/test_shop.py::test_product_detail`; terminal state `已结束`, debug console **1 passed in 2.51s**. Breakpoints were accepted but not hit for this selected test.
- Existing result run `run_eb4ccaf35252f5440324e6f938cbeb7d` displayed PASSED. No rerun was initiated.

Screenshots are in [`full-product-evidence/after/`](full-product-evidence/after/); initial entry snapshots are in [`full-product-evidence/before/`](full-product-evidence/before/). Dashboard captures in both folders provide the controlled four-size before/after evidence for the mobile-navigation refinement.

## Persistence and Worker safety check

Read-only SQLite counts matched the saved pre-start checkpoint:

| Scope | Checkpoint | After audit |
|---|---:|---:|
| `execution_jobs` total | 5,004 | 5,004 |
| QUEUED jobs | 5,000 | 5,000 |
| COMPLETED jobs | 4 | 4 |
| Golden Demo jobs | 4 COMPLETED; none queued/running | 4 COMPLETED; none queued/running |
| Pre-existing Golden Demo run status | `RUNNING` (`run_51c9455dff71`) | `CANCELLED` by API stale-run recovery |
| Registered Workers | 1 OFFLINE | 1 OFFLINE |

The cluster API reports 200 queued jobs because its summary is capped; the underlying read-only SQLite count is 5,000. No Worker process was launched and no queued job was claimed. The only test-run status delta was automatic startup recovery of `run_51c9455dff71`: it started at `02:20:51.117140`, crossed the configured 7,200-second stale threshold, and was marked `CANCELLED` at `04:22:44.647233`. `/tmp/aiqa-mobile-nav-workspace.log` records `Recovered 1 stale run(s) at startup`; no manual status change or reset was performed. The cancellation is preserved as recorded.

## Not run / not passed

- **PostgreSQL:** unavailable locally; Docker and a PostgreSQL service/test URL were not available. SQLite results are not substituted for PostgreSQL acceptance.
- **Windows/Linux CI:** not run on this macOS host.
- **Fresh Worker execution against the existing runtime DB:** intentionally not run because the database contains 5,000 queued jobs with unrelated benchmark-project work. Prior scoped Golden Demo Worker evidence is linked in the Golden Journey report.
- **Fresh Quality Discovery run:** form loaded, but no new run was created. The Jev decision was independently exercised in Settings.
- **Human rejection, retry-failure and Golden Demo tablet direct-refresh branches:** remain unsupported, incomplete or unverified as recorded in the acceptance report.
