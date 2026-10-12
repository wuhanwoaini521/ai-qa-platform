# Functional Testing

## Automated checks

- `pnpm --filter @ai-qa/web test` — PASS, 105/105 tests.
- `pnpm --filter @ai-qa/web lint` — PASS.
- `pnpm --filter @ai-qa/web build` — PASS (`tsc -b` and Vite production build). Vite reports the existing large Monaco editor chunk (~4 MB); build completes successfully.
- `git diff --check` — PASS.

## System Chrome checks

- Expanded desktop sidebar: project selector, search, current Workspace active state, Platform group, Settings, and language control rendered. Evidence: `/tmp/aiqa-sidebar-desktop-verified.png`.
- Collapsed/expanded toggle: icon rail and labels both rendered; preference survived reload. Existing captures: `/tmp/aiqa-sidebar-desktop-collapsed.png`, `/tmp/aiqa-sidebar-collapsed-reload.png`, `/tmp/aiqa-sidebar-collapsed-tooltip.png`.
- Keyboard navigation search (`Cmd+K`): searched `failure`, saw the matching Workspace failure destination in the palette, closed it, cleared the query, and confirmed the current route remained unchanged. Evidence: `/tmp/aiqa-sidebar-search-results.png`.
- Project selection: switched from the actual `Reference QA` project to the actual `Broken Conftest Probe` project on a project-scoped Workspace route, then restored the original project and URL. Scoped selector omitted “All projects” as intended. Existing captures: `/tmp/aiqa-sidebar-project-options.png` and `/tmp/aiqa-sidebar-after-restore.png`. This was navigation only; no run was started and no project data was edited.
- Responsive layout: reviewed desktop, compact/tablet, and narrow mobile presentations. Evidence: `/tmp/aiqa-sidebar-tablet-final.png` and `/tmp/aiqa-sidebar-mobile-final.png`; no page-level horizontal overflow was visually observed (the Workspace stage retains its own horizontal scroller).
- Dark theme: changed the existing UI preference from `system` to `dark`, reviewed the sidebar, then restored `system`. Evidence: `/tmp/aiqa-sidebar-dark-theme.png`.

The local API/Web session and existing real run data were only viewed. No database reset, Worker startup, queue processing, or write operation was performed. Chrome was restored to its original active tab, window bounds, Workspace URL, project, search state, and theme preference.
