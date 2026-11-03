# 08 — Regression

Gate results are recorded per round in `09-final-report.md`; this file records what was checked for unintended breakage.

| Area | Check | Result |
|---|---|---|
| Requirements lifecycle panel | Still renders acceptance criteria after switching to `criteriaTextFor` / `requirementDocumentWithCriteria` imports | PASS — `RequirementLifecyclePanel.tsx` diff is −43/+? (imports only), criteria UI re-verified in the browser on `req_9c72a1dabe30` |
| Requirement creation (other pages) | `RequirementFormModal` gained an optional `error` prop; existing callers pass none | PASS — prop optional, `typecheck` clean, no caller changed |
| Test-case creation (other pages) | `TestCaseFormModal` same optional prop | PASS — same |
| managementModel consumers | New export only; no existing export renamed or removed | PASS — `management-model.test.mjs` 9 existing cases still pass |
| i18n | 25 new keys, `dataScope` now takes `{{count}}`/`{{total}}` | PASS — `i18n_check.py` 30 namespaces / 2 languages / 4127 keys; both locales present |
| Shared CSS | `index.css` only gained `.form-error`; no existing selector modified | PASS |
| Table CSS | `white-space:nowrap` narrowed from `.management-matrix-table` to `.management-trace-table` | PASS — traceability view re-shot; requirements/cases now wrap correctly, overflow 0 |
| Protected worktree changes | `workspaceContext.ts`, `Navigation.tsx`, `ProjectOverviewPage.tsx`, `nav.json` ×2, `ProjectsPage.tsx` show the same diffstat as before this task | PASS — `git diff --stat` unchanged for them |
| Build | Vite build after all edits | PASS — 318 tests / build green |

| Cases table scoping | Added `management-cases-table` class + `:not()` so the 400px name cap applies only to 需求/追踪 tables | PASS — row heights 68px (需求/追踪)、126/106/87px (用例, unchanged); overflow 0 at 1280/1440/1920 |
| Duplicate submit guard | `createRequirement` / `createTestCase` early-return while `createSubmitting` | PASS — `create_duplicate_submit_guard`: double click sends exactly 1 POST |
| Modal error prop | `error?: string` rendered as `role="alert"` inside `.modal-body`; `.form-error` in `index.css` | PASS — `create_failure_shows_error`, `link_failure_*` |

Not covered: no automated browser regression suite exists in this repo, so UI regression relies on the Playwright scripts in `evidence/` being re-run manually.
