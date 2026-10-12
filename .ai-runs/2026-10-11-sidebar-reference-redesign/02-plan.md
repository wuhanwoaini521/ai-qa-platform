# Plan

1. Implement the sidebar reference in `Navigation.tsx` and `index.css`: project scope in the sidebar header, rounded inset panel, expandable platform group, pinned Settings/language footer, persisted desktop collapse state, compact project selection, and active/hover styling.
2. Remove the duplicated project selector/selection handler from the top toolbar and `AppLayout.tsx`, retaining the selected project ID for Header's status query and using `withProjectId` for sidebar switches.
3. Extend the shared `Tooltip` with an explicit enable option for manually collapsed desktop navigation, keeping current automatic compact-screen behavior.
4. Add localized collapse/expand control labels in both nav locale files. Keep project and route labels from existing translations.
5. Run focused frontend tests, typecheck, lint, production build, and diff checks. Review the full changed diff for route, keyboard, responsive, and accessibility regressions.
6. If the existing local system-Chrome/browser setup is available, review expanded/collapsed states at desktop and responsive widths; otherwise state the limitation explicitly.

## Expected implementation files
- `apps/web/src/components/Navigation.tsx`
- `apps/web/src/components/Tooltip.tsx`
- `apps/web/src/components/Header.tsx`
- `apps/web/src/app/AppLayout.tsx`
- `apps/web/src/index.css`
- `apps/web/src/i18n/locales/en/nav.json`
- `apps/web/src/i18n/locales/zh-CN/nav.json`

## Review and acceptance
- Preserve prior uncommitted changes and avoid unrelated files.
- Confirm no duplicate project selector and that project-scoped/all-project behavior is unchanged.
- Validate real UI behavior and three viewport classes; capture evidence in `/tmp` if browser tooling is available.
- No commit/push or changes to backend/runtime data.
