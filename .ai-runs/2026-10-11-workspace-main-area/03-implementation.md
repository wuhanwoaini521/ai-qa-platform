# Implementation

- run-date: 2026-10-11
- task-type: ui-redesign
- risk: MEDIUM

## Changes
- `apps/web/src/features/workspace/WorkspacePage.tsx`, `workspace.css`, `workspaceLayoutModel.ts`, and `apps/web/tests/workspace-layout-model.test.mjs`: adapt context and Inspector modes to measured Workspace width; retain the context toggle and use a modal Inspector when side-by-side layout would crowd the main panel.
- `apps/web/src/features/automation-studio/AutomationStudioPage.tsx`: in embedded Workspace, keep the redundant Studio context hidden by default but accessible from More Tools; collapse the file tree at widths <=820px, display it as a 230px overlay, and close it after a file is selected.
- `apps/web/src/features/automation-studio/components/ProblemsPanel.tsx`, `apps/web/src/index.css`, and `workspace.css`: give the phone editor more vertical room, keep its toolbar to one icon row, hide secondary status chrome and move the Problems toggle into More Tools while leaving expanded diagnostics visible.
- No API, model, dependency, or lockfile changes. Existing unrelated worktree changes were preserved.
