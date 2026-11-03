# 09 — Final report

**Verdict: PASS** — the 需求与用例 page rework is implemented, all automated gates pass, the primary flows plus
failure paths are verified in a real browser at 1280/1440/1920 against an isolated API (`46/46` checks), and the
change is committed and pushed per the user's explicit instruction.

## Changes

New: `apps/web/src/features/lifecycle/requirementCriteria.ts`, `apps/web/tests/requirement-criteria.test.mjs`.

Modified: `apps/web/src/features/management/{ProjectManagementPage.tsx,ProjectManagementPage.css,ProjectManagementMatrix.css,managementModel.ts}`, `apps/web/src/features/lifecycle/RequirementLifecyclePanel.tsx`, `apps/web/src/features/requirements/components/RequirementFormModal.tsx`, `apps/web/src/features/test-cases/components/TestCaseFormModal.tsx`, `apps/web/src/i18n/locales/{en,zh-CN}/projectManagement.json`, `apps/web/src/index.css`, `apps/web/tests/management-model.test.mjs`.

Delivered behaviour:

- Requirement rows: real linked-case count, 详情 action opening a detail drawer, filterable case entry point.
- Detail drawer (URL-backed `?detail=`): facts (status / relation / updated / source when present), description,
  acceptance criteria view + inline edit with ID-preserving save, linked cases, link-an-existing-case, create-case
  in requirement context.
- Truthful filter chips with per-family labels, accurate `显示 X / Y 条记录。`, single clear action, no-match state.
- Contextual header action (新建需求 / 新建用例), keyboard tab navigation with correct wrap direction.
- Cases table: correct column/cell alignment, no 1280px overflow, single-line requirement label + inline relation select.
- Failure paths show an error instead of staying silent; inputs are preserved for retry; duplicate submits are guarded.

Untouched (pre-existing user work): `apps/web/src/app/workspaceContext.ts`, `apps/web/src/components/Navigation.tsx`, `apps/web/src/features/lifecycle/ProjectOverviewPage.tsx`, `apps/web/src/i18n/locales/{en,zh-CN}/nav.json`, `apps/web/src/pages/ProjectsPage.tsx`, `docs/agent-handoff.md` (new section appended only).

## Verification (commands actually run from `/home/hans/self-github/ai-qa-platform`)

| Command | Result |
|---|---|
| `pnpm --filter @ai-qa/web typecheck` | PASS — `tsc --noEmit`, no errors |
| `pnpm --filter @ai-qa/web lint` | PASS — eslint clean |
| `pnpm --filter @ai-qa/web test` | PASS — 318 tests, 0 failures (10 in `management-model.test.mjs`, 4 in `requirement-criteria.test.mjs`) |
| `pnpm --filter @ai-qa/web build` | PASS — Vite build 2m27s; only the pre-existing >500kB chunk warning |
| `uv run python scripts/i18n_check.py` | PASS — 30 namespaces, 2 languages, 4127 keys |
| `uv run python evidence/final-check.py` (shared stack) | PASS — tabs, keyboard, chips, search, no-match, drawer, deep link, 0 page/console errors |
| `uv run python evidence/shots3.py` | PASS — 9 viewport/tab combos, page and table overflow 0 |
| `uv run python evidence/closure-check.py` (isolated `:8010`) | PASS — 46/46 incl. CRUD, criteria ID retention across reload, link success/failure rollback, load failure + retry, long titles, 3 viewports |
| `uv run python evidence/shots-tabs.py` (isolated) | PASS — 9 viewport/tab combos, overflow 0, requirements/trace row height 68px |

Evidence: `.ai-runs/2026-11-03-requirements-cases-management/evidence/` (28 PNGs + 5 scripts + `closure-result.json`).

## Risks

- Execution-result linkage is intentionally absent — no trustworthy project/binding/nodeid/run mapping exists, and
  fabricating it is forbidden by the request.
- Drawer is intentionally non-modal: no focus trap, no scroll lock; focus returns to the trigger.
- Cases rows are taller than requirement rows at 1280 (long requirement labels wrap); accepted, documented.
- Pre-existing, not introduced here: duplicated counts (cards + tab badges), drawer overlapping the top toolbar.
- Verification required an isolated API instance; the harness relies on Playwright request interception, so it does
  not exercise the Vite dev proxy for `/api`. The shared stack was used separately for the earlier read-only checks.

## Git

`.ai-runs/…` records and `docs/agent-handoff.md` §3.70/§3.71 are included in the commit; pre-existing uncommitted
user changes in the protected files remain untouched by this task's edits.
