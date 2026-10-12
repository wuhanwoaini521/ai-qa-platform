# Full Product Final Acceptance

**Audit date:** 2026-10-11
**Overall verdict: PARTIAL — not a full pass.**
**Repository:** `main` at `cdf954a`; substantial pre-existing user/session worktree changes were preserved.

## Acceptance gates

| Gate | Result | Evidence and boundary |
|---|---|---|
| **1. Workflow simplification** | **PASS — bounded** | Real browser navigation verified six legacy entry categories (requirement, case, Studio, run, failure and recorder) entering the project-scoped Workspace. The five-stage Workspace retains project context and consolidates navigation. This does not mean every branch is complete: human rejection is unavailable and retry-failure coverage is incomplete. See [UX audit](full-product-ux-audit.md). |
| **2. UI before/after evidence** | **PASS — scoped refinement** | A confirmed mobile-navigation readability issue was fixed (390×844 labels 8px→9px; items 42px→52px). Real Dashboard before/after screenshots are retained at 1920×1080, 1440×900, 1366×768 and 390×844. The post-fix browser confirmed localized English/Chinese labels are unclipped, full accessible names remain, all five primary routes open, and no document overflow. This is not a pre-redesign baseline for the broader shell. See [UX audit](full-product-ux-audit.md). |
| **3. Final-code regression** | **PASS — local environment only** | Current worktree source passed `pnpm test` (**667 passed, 7 skipped**), `pnpm lint`, web typecheck/build, i18n parity and diff checks. No product-source changes were made after these runs. PostgreSQL, remote Linux/Windows and the skipped test branches are outside this pass. See [test results](full-product-test-results.md). |

**All three specified gates pass within their stated scope. Overall acceptance remains PARTIAL** because human rejection/retry-failure and tablet direct-refresh coverage are incomplete or unverified, PostgreSQL/cross-platform CI were unavailable, and one pre-existing stale run was auto-recovered at startup. No FULL PASS is claimed.

## What was verified

- API live/readiness and web root returned HTTP 200; SQLite database and artifact storage were healthy; migrations were at `0007_quality_discovery_version`.
- A real AI connection probe succeeded; a real Jev connection/runtime check succeeded; the Jev Playground chose `preserve_read_only` with confidence `1.0` and `fallback_used=false`.
- The browser reviewed primary routes and compatibility redirects. Dashboard and core Workspace screens were captured at 1920×1080, 1440×900, 1366×768 and 390×844 with no document-level horizontal overflow.
- The recorder loaded a local Demo Shop browser frame and was closed without recording an action or saving a case.
- The debugger UI ran `tests/test_shop.py::test_product_detail`; debugpy reported **1 passed in 2.51s**. No code edit or breakpoint change occurred.
- Existing `run_eb4ccaf35252f5440324e6f938cbeb7d` displayed PASSED. The full existing Golden Demo repair journey and its limitations remain in [`playwright-golden-journey-acceptance.md`](playwright-golden-journey-acceptance.md); this audit did not repeat a Worker run.

## Safety, scope and limitations

- Execution-job counts matched the read-only checkpoint: 5,000 queued and 4 completed; all 5,000 remained queued. No Worker was started; the registered Worker remained OFFLINE.
- The pre-existing Golden Demo `run_51c9455dff71` was RUNNING at the checkpoint. API startup later auto-recovered it to CANCELLED after it exceeded the 7,200-second stale threshold (`started_at=02:20:51.117140`, `finished_at=04:22:44.647233`). The startup log records the recovery. This was not a manual cancellation; its history was not reset or restored.
- No requirements, cases, bindings, failures, credentials or queue rows were changed or reset. Real AI/Jev checks added normal provider telemetry. One temporary recorder session was closed.
- The debugger test produced runtime artifacts under `runtime/runtime/artifacts/demo-shop/` and Python collection created a workspace `__pycache__`; these artifacts were left in place and not staged.
- PostgreSQL/Docker were unavailable. No Windows/Linux CI ran. Human rejection, retry-failure and Golden Demo tablet direct-refresh remain unsupported, incomplete or unverified. Quality Discovery was inspected but not newly executed. No complete accessibility or cross-browser claim is made.

## Delivery state

- Five requested audit reports are present: [feature inventory](full-product-feature-inventory.md), [UX audit](full-product-ux-audit.md), [fix log](full-product-fix-log.md), [test results](full-product-test-results.md), and this acceptance report.
- Browser evidence: [`full-product-evidence/before/`](full-product-evidence/before/) and [`full-product-evidence/after/`](full-product-evidence/after/).
- The continuation made a scoped four-file source change (`apps/web/src/index.css`, `apps/web/src/components/Navigation.tsx` and the English/Chinese nav dictionaries) for mobile navigation readability; final regression passed after those edits. Other pre-existing changes were preserved. No files were staged, committed or pushed.
- API and Vite services started for the audit were stopped; ports 8000 and 5173 had no listeners at shutdown.

## To close remaining gates

1. Run the PostgreSQL lane and Linux/Windows CI in an available environment.
2. Implement and test a human rejection contract; complete retry-failure and tablet direct-refresh branches.
3. Test Worker claiming only in an isolated queue/database; do not point it at the existing 5,000 queued benchmark jobs.
