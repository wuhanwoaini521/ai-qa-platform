# Analysis

- `apps/web/src/components/Navigation.tsx` owns the shared sidebar, project scope access, route links, platform disclosure, keyboard search, and language control. It is the smallest coherent implementation surface for the requested sidebar change.
- `Header.tsx` currently renders the real project selector in the top toolbar; moving that existing control into the sidebar's top context row matches the reference without creating a second/fake selector. Preserve the existing `withProjectId` route semantics when switching projects. `Header` still needs the selected project ID for its real runner-status query.
- `AppLayout.tsx` supplies both shared shell components and currently owns project selection; that handler can move into `Navigation` using the existing project-scope provider and `withProjectId` helper.
- `index.css` currently uses a full-height 220px sidebar and an automatic icon rail below 1150px, with a horizontal mobile navigation. Restyle the sidebar as an inset rounded panel, increase expanded width to match the reference proportions, add an explicit persisted desktop collapse control, and preserve tablet/mobile compact modes.
- Existing nav items are Dashboard, Workspace, Projects, Runs, Insights, Settings, and a collapsible Platform group. Keep them and existing search destinations. Pin Settings and language controls at the bottom; do not add fabricated account, billing, favorites, help, or unread-count content.
- `Tooltip` only appears below 1151px today. Extend it narrowly so manually collapsed desktop navigation also exposes accessible hover/focus labels; retain responsive tooltips.
- Risk is MEDIUM because the shell is shared by every route and project selection changes route context. No backend, API, persistence schema, or runtime data changes are needed.
- Browser review found and corrected a narrow-screen width conflict in the pinned footer; the final responsive review passed. Dark mode was also manually checked and the original system preference restored.

## Acceptance criteria
1. At desktop width, the sidebar is a separated rounded panel with project context, search, navigation, a clear neutral active state, and bottom-pinned Settings/language controls.
2. The collapse control switches between labeled and icon-rail layouts, has accessible expanded state/labels, persists the user's choice, and shows nav labels on hover/focus when collapsed.
3. Project switching remains available in expanded and compact layouts, respects project-scoped routes, and uses the existing route helper.
4. Platform links, keyboard search, language switching, and route destinations remain usable.
5. Desktop, tablet, and narrow mobile layouts have no visually observed page-level horizontal overflow; responsive navigation and dark theme remain legible.
6. Relevant frontend tests, typecheck, lint, and production build pass; system-Chrome review covers expanded/collapsed, project switching, keyboard search, active state, responsive layouts, and dark theme.
