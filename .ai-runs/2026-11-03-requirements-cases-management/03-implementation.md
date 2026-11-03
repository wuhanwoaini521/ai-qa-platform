# 03 — Implementation

Scope: extend the existing `需求与用例` page only. No new API, no schema migration, no new navigation, no commit.

## Files changed

| File | Change |
|---|---|
| `apps/web/src/features/management/ProjectManagementPage.tsx` | +286/−? — contextual header primary button, `moveTab` keyboard helper (ArrowLeft no longer behaves like ArrowRight), per-tab status labels, real filter summary + removable chips, requirement detail drawer, create-requirement / create-case wiring, `openDetail` focus handling |
| `apps/web/src/features/management/managementModel.ts` | +7 — `clearedFilterPatch(tab)` so each tab clears only its own filters |
| `apps/web/src/features/management/ProjectManagementPage.css` | drawer, chips, row-action and table width rules; removed `td:first-child{min-width:260px}` |
| `apps/web/src/features/management/ProjectManagementMatrix.css` | `white-space:nowrap` moved from `.management-matrix-table` first column to `.management-trace-table` only (the nowrap rule was inflating the identity column to 799px at 1280) |
| `apps/web/src/features/requirements/components/RequirementFormModal.tsx` | optional `error` prop rendered as `role="alert"` inside the modal body |
| `apps/web/src/features/test-cases/components/TestCaseFormModal.tsx` | same optional `error` prop |
| `apps/web/src/index.css` | `.form-error` rule |
| `apps/web/src/i18n/locales/{zh-CN,en}/projectManagement.json` | 25 new keys, `dataScope` now uses `{{count}} / {{total}}`, title unified to 需求与用例 / Requirements & Cases |
| `apps/web/tests/management-model.test.mjs` | 4 `clearedFilterPatch` assertions |

Reused instead of re-created: `RequirementFormModal`/`TestCaseFormModal` + their `use*FormModal` hooks, `api.updateRequirement`, `api.createRequirement`, `api.createTestCase`, `criteriaTextFor` / `requirementDocumentWithCriteria` (`features/lifecycle/requirementCriteria.ts`, added earlier in this task), `getRequirementDisplayId` / `getCaseDisplayId` / `countCasesForRequirement` / `canChangeCaseRequirement`.

## Behaviour delivered

1. **Detail drawer** (`?detail=<requirementId>`, deep-linkable, refresh/back safe): facts (status, real linked-case count, updated, source only when present), description, acceptance criteria view/edit (ID-preserving save via `requirementDocumentWithCriteria`), linked case list, and “link an existing unlinked case of this project”. Escape and backdrop close it; focus moves in on open and returns to the triggering 详情 button on close.
2. **Filter truthfulness**: `显示 {{count}} / {{total}} 条记录` plus one removable chip per active filter; a single 清除筛选 path (the chips-row clear hides while the empty state shows its own).
3. **Contextual primary action**: 新建需求 / 新建用例 following the active tab, with create errors surfaced in the modal instead of a silent no-op.
4. **Keyboard**: ArrowRight/ArrowLeft move and wrap between the three tabs (previous code mapped ArrowLeft to forward movement).
5. **Column/label correctness**: cases table body now emits 7 cells matching its 7 headers (was 6 — priority/automation/date were displayed under the wrong headings).

## Deliberate non-goals

- No execution-result column: there is no reliable requirement↔execution mapping, so any value would be fabricated. The traceability hint states results are not implied.
- No bulk retitle / title-similarity merge, no coverage percentage, no Discovery “source” fabrication.
- Case row density at 1280 (id + title + tags + relation label + relation select) is an accepted trade-off for inline association.
