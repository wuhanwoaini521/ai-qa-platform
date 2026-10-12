# Implementation

- Completed the terminal-result presentation using the existing Workspace run model: `PASSED`, `FAILED`, `ERROR`, and `CANCELLED` are recognized as terminal; the UI displays localized status labels instead of `—` for passing/cancelled outcomes.
- Added `repairNoticeForRun` to distinguish a passed run with no Failure record (neutral “repair not needed”) from a failed/error run with no Failure record (repair blocked). Active and cancelled runs do not receive a premature blocker; existing Failure/AI invocation evidence suppresses the missing-record notice.
- Added the neutral notice styling and English/Chinese translations. The related two-column overview, full-width activity section, token-based neutral styling, and non-nested result-panel flow were already present in this worktree from the preceding layout pass and were browser-verified again here.
- Added model tests for the repair-state boundary cases, alongside terminal-status coverage.

## Files

- `apps/web/src/features/workspace/workspaceRunModel.ts`
- `apps/web/src/features/workspace/WorkspaceRunResult.tsx`
- `apps/web/src/features/workspace/workspace.css`
- `apps/web/src/i18n/locales/en/workspace.json`
- `apps/web/src/i18n/locales/zh-CN/workspace.json`
- `apps/web/tests/workspace-run-model.test.mjs`

No API/data changes, database changes, staging, commits, or pushes were made. The pre-existing unrelated worktree changes were preserved.