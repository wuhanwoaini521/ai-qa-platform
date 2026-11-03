# 06 — Code review

Self-review by the implementing agent. No independent code reviewer was delegated; this is not a substitute for one.

## Checked

- **Contract reuse.** No new service, store, endpoint or runtime path. Drawer writes go through the existing `api.updateRequirement` / `api.updateTestCase` and `criteriaTextFor` + `requirementDocumentWithCriteria`, so acceptance-criterion IDs and `negative_required` survive an edit (covered by `apps/web/tests/requirement-criteria.test.mjs`, 4 cases).
- **URL as state.** Drawer, tab and every filter live in `searchParams`; refresh/back/deep-link restore the same view. `openDetail` uses `replace:false` so Back closes the drawer; filters use `replace:true`.
- **Effect correctness.** One real defect was found and fixed during verification: the reset effect originally depended on `[detailRequirementId, detailCriteria]`, so the `验收标准已保存` success message was wiped as soon as the saved criteria changed. It now depends on `[detailRequirementId]` and reads the current text through a ref.
- **Async safety.** `saveCriteria` / `linkCase` guard with their own saving flags, catch into a typed feedback object (`{failed, message}`) and never throw into React.
- **Type safety.** All new state typed (`ReactKeyboardEvent<HTMLButtonElement>`, `Feedback`, `Record<string,string>` patches); `tsc --noEmit` clean, no `any`.
- **Accessibility.** Tab list retains `role="tab"`/`aria-selected`/`aria-controls`; the drawer is `role="dialog"` + `aria-labelledby` with a labelled close button; chips carry `aria-label="移除筛选：<label>"`; feedback uses `role="alert"`/`role="status"`; selects have visually-hidden labels.
- **i18n.** Every new string added to both locales; `uv run python scripts/i18n_check.py` → `30 namespace(s), 2 language(s), 4127 keys` PASS.

## Known weaknesses (accepted)

1. No focus trap or scroll lock — the drawer is deliberately non-modal (`aria-modal="false"`) so the list stays readable; Tab can reach the dimmed page.
2. `reason`-less disabled 关联 button.
3. Drawer facts/all sections re-render from the latest `testCases`/`requirements` snapshot — fine for a 108-case project, O(n) per render otherwise.
4. `criteriaList` keys use `` `${index}-${item}` ``; duplicate lines are legal content, so index-prefixed keys are intentional.
