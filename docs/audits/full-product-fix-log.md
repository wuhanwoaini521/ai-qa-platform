# Full Product Fix Log

**Audit date:** 2026-10-11
**Code changes made during the initial full-product pass:** none. **Follow-up continuation:** one scoped mobile-navigation readability refinement across the shared navigation component, CSS and locale strings after a browser-confirmed issue.

## Triage outcome

The worktree contained substantial pre-existing API, Worker, demo-shop, navigation, Workspace and run-result changes before the audit began. The initial full-product test baseline and live routes exercised that current code. During continuation, a P2 mobile navigation readability issue was confirmed: at 390×844, primary labels were 8px and each item was 42px wide. A real English-browser check also showed longer labels clipped after the initial sizing-only adjustment, so concise localized labels were added while retaining full accessible names. The final targeted fix is described below. Existing uncommitted changes were preserved; nothing was staged, committed or pushed.

The following attempted checks initially failed only in the audit harness and were corrected without product edits:

1. The first debugger wait predicate looked for “completed” wording while the UI correctly reports the terminal state as `已结束`. A corrected wait observed the terminal status and passed test output.
2. A screenshot script used a strict Playwright locator matching two legitimate `PASSED` labels. The locator was narrowed and stable screenshots were captured successfully.
3. An early mobile Dashboard screenshot was taken before Dashboard data had loaded. It was replaced after waiting for the page-specific loaded state.

These are not product defects and are not counted as product fixes.

## Follow-up source fix

- **Finding:** mobile navigation labels were too small to comfortably distinguish at 390×844 (8px, 42px items).
- **Change:** `apps/web/src/index.css` increases primary item width to 52px and mobile label size to 9px within the existing `max-width: 600px` rule. `Navigation.tsx` renders concise mobile labels alongside full labels; the concise label is hidden from assistive technology and the full translated `aria-label` remains. English and Chinese nav dictionaries provide localized compact labels. Route structure, horizontal scrolling and desktop/tablet styles are unchanged.
- **Verification:** real Chrome at 390×844 measured 52px items and 9px labels. All five primary routes opened correctly; all localized compact labels were unclipped, accessible names remained full, and document width stayed 390px. Dashboard before/after images exist at all four target viewports. Final `pnpm test`, `pnpm lint`, frontend typecheck/build, i18n parity and `git diff --check` passed.

## Existing fixes re-verified

These changes were already present in the dirty worktree and were not introduced during this full-product audit:

- Unified project-scoped Workspace stages and legacy-route redirects, exercised across requirement, cases, Studio, result, failure and recorder entry points.
- Workspace run-result terminal status rendering and repair applicability messaging, covered by `apps/web/tests/workspace-run-model.test.mjs` and browser result screenshots.
- Existing Golden Demo real AI/Jev workflow, project-scoped Worker execution, locator repair and verified retest, documented in [`playwright-golden-journey-acceptance.md`](playwright-golden-journey-acceptance.md).
- Existing Worker project-claim filtering and AI/runtime safeguards; covered by the current test suite, but not activated against the existing runtime queue during this audit.

The Workspace result report at [`.ai-runs/2026-10-11-workspace-result-reference-fix/09-final-report.md`](../../.ai-runs/2026-10-11-workspace-result-reference-fix/09-final-report.md) records its own focused PASS and scope. It is not a substitute for this system-wide acceptance.

## Side effects and preservation

- **Business records:** no requirements, cases, bindings, failures, credentials or Worker jobs were created, updated, deleted or reset. One pre-existing TestRun, `run_51c9455dff71`, transitioned from RUNNING in the checkpoint to CANCELLED during API startup's automatic stale-run recovery after exceeding the configured 7,200-second threshold. The startup log confirms the recovery; no manual cancellation or restoration was performed. Its run history remains in the database.
- **Queue:** no Worker was started. SQLite checkpoint and live job counts matched exactly: 5,000 queued jobs, 4 completed jobs; all 5,000 queued jobs remained queued. The registered Worker remained OFFLINE.
- **AI/Jev telemetry:** the real AI/Jev connection probes and Jev Playground action write normal provider-invocation telemetry. The real Jev decision returned `preserve_read_only` with no fallback. No credentials were changed or emitted.
- **Recorder:** one temporary session loaded the API-hosted Demo Shop page and was closed without recording a user action, saving a case, or writing source.
- **Debugger artifacts:** the read-only debugger test generated `runtime/runtime/artifacts/demo-shop/test_product_detail.{html,png,zip}` and Python collection generated a workspace `__pycache__` entry. These runtime artifacts were left in place and were not staged or committed; runtime data is excluded from product-code delivery.
- **Services:** API and Vite were started because no services were running on entry. They were stopped after evidence capture and final validation; ports 8000/5173 were checked afterward.

## Follow-up fixes not made

- Implementing a human rejection action would require an explicit product/API contract; the UI/API inspected in the failure workflow does not support it. This remains a known workflow limitation, not an assumed pass.
- Retry-failure acceptance remains incomplete.
- PostgreSQL and cross-platform lanes require an available PostgreSQL/Docker service or remote CI; they were not simulated using SQLite.
