# Implementation

## Changes

- Reframed the shared authenticated shell in `apps/web/src/app/AppLayout.tsx` and `apps/web/src/components/Header.tsx`: project selector now leads a full-width toolbar; navigation and page content sit below it; workspace routes use their own content heading instead of repeating the global route title.
- Updated shared tokens and shell styles in `apps/web/src/index.css`: cool blue-gray canvas, clearer blue/green/red semantics, lighter separators, a full-bleed app frame, and a stronger blue active-navigation state. Existing dark-theme token overrides remain in place.
- Updated the Workspace stage timeline and result layout in `apps/web/src/features/workspace/workspace.css`. Wide result screens align the three work panels at a viewport-aware height so the evidence row is visible; each panel retains its complete contents via internal scrolling.
- Added stage-specific Workspace H1s and localized labels (including the reference's “用例分析”) in `WorkspacePage.tsx` and both `workspace.json` locales.
- Failed/error result evidence now opens by default and remains user-collapsible in `WorkspaceRunResult.tsx`; success/active runs keep it closed.
- Extracted project-scope URL rewriting into `apps/web/src/app/projectPaths.ts`. Changing project in Workspace starts a clean route without carrying old run/entity query parameters. The “All projects” option is kept on global routes and omitted while a specific Workspace/project route is active.
- Added project-scope route tests in `apps/web/tests/workspace-context.test.mjs`.

## Scope Boundaries

No backend/API, database, provider, worker, workspace, project, or run data was changed. Browser inspection used read-only GETs; no run or AI task was created. Build artifacts remain ignored. `.ai-runs/` is untracked and was not staged.

## Files

`apps/web/src/app/AppLayout.tsx`, `apps/web/src/app/navigation.ts`, `apps/web/src/app/projectPaths.ts` (new), `apps/web/src/components/Header.tsx`, `apps/web/src/features/workspace/WorkspacePage.tsx`, `apps/web/src/features/workspace/WorkspaceRunResult.tsx`, `apps/web/src/features/workspace/workspace.css`, `apps/web/src/index.css`, `apps/web/src/i18n/locales/{en,zh-CN}/workspace.json`, and `apps/web/tests/workspace-context.test.mjs`.
