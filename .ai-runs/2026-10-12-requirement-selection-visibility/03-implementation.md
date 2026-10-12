# Implementation — Requirement Selection Visibility

- Added `buildRequirementSelectionModel` to derive the current requirement identity and ID + title options from existing requirement data.
- In Workspace requirement mode, the toolbar now shows a labeled current-requirement identity when one requirement exists, and an accessible native selector when multiple exist. Selection reuses `handleSelectRequirement`, preserving the existing selected-requirement callback and Workspace URL/context update path.
- Added the `currentRequirement` label in English and Simplified Chinese.
- Added compact token-based styling; the identity occupies the left side of the toolbar and the existing Jira / create / analysis actions remain available on the right. At widths ≤820px, the scope and action rows stack.
- Added model regression tests for single, multiple, fallback-ID, and no-selection cases.
- No backend/API/data-model changes or persisted requirement data changes.

Files:
- `apps/web/src/features/requirements/RequirementsPage.tsx`
- `apps/web/src/features/requirements/requirementSelectionModel.ts`
- `apps/web/src/features/workspace/workspace.css`
- `apps/web/src/i18n/locales/en/requirements.json`
- `apps/web/src/i18n/locales/zh-CN/requirements.json`
- `apps/web/tests/requirement-selection-model.test.mjs`
