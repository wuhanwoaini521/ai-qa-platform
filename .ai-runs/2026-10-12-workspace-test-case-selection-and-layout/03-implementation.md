# Implementation — Workspace Test Case Selection and Layout

## Changes
- Added `apps/web/src/features/test-cases/testCaseSelectionModel.ts` to present every project case with a stable display ID and title. It uses the model display ID, external ID, or a visible ID suffix as fallback; it distinguishes selected-single, selectable, and empty states.
- Updated `TestCasesPage` to show a labeled current-case selector in Workspace mode when multiple cases are available, a static ID/title identity for a selected single case, and a placeholder when cases exist but none is selected. The standalone list/detail rendering was not changed.
- Changed `onSelectTestCase` to pass the selected `TestCase`, and connected it to `WorkspacePage.selectCase` so selection updates the full existing context (case, requirement, design, binding, and stale run/debug IDs) rather than only `testCaseId`.
- Added responsive toolbar styles using existing Workspace tokens; retained the create action and full-width detail. Added English and Simplified Chinese strings.
- Added `apps/web/tests/test-case-selection-model.test.mjs`, including selected-single, all-cases, unselected-single, fallback-ID, and empty-list cases.

## Changed files for this task
- `apps/web/src/features/test-cases/TestCasesPage.tsx`
- `apps/web/src/features/test-cases/testCaseSelectionModel.ts` (new)
- `apps/web/src/features/workspace/WorkspacePage.tsx`
- `apps/web/src/features/workspace/workspace.css` (case-toolbar additions; pre-existing requirement-toolbar edits preserved)
- `apps/web/src/i18n/locales/en/testCases.json`
- `apps/web/src/i18n/locales/zh-CN/testCases.json`
- `apps/web/tests/test-case-selection-model.test.mjs` (new)

## Commands
- `pnpm --filter @ai-qa/web test`
- `pnpm --filter @ai-qa/web lint`
- `pnpm --filter @ai-qa/web typecheck`
- `pnpm --filter @ai-qa/web build`
- `git diff --check`
- Browser exercised real project cases through the visible selector and direct-case route; no case data was created or modified.
