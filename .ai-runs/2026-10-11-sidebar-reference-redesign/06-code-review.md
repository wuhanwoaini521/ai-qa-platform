# Code Review

## Review scope

Self-review of the changed navigation, header/layout integration, tooltip behavior, responsive CSS, locale strings, and existing project-route helper/tests. No independent reviewer or additional agent was available.

## Review notes

- Project selector remains a single control. Route navigation uses `withProjectId`; project-scoped routes do not expose the All-projects option.
- Collapse state is limited to the browser preference key and storage access is guarded. It does not change project data or server state.
- Collapse button exposes an accessible label, expanded state, and controlled navigation target. Links keep accessible names in compact mode; custom tooltip behavior is opt-in for collapsed desktop and preserves the existing media-query behavior.
- Search and navigation destinations are retained; Settings is rendered in the pinned footer during normal navigation and included in search results.
- Header still receives the selected project ID for its status query, with the duplicate selector and handler removed.
- Responsive overrides preserve mobile labels even if the desktop collapsed preference is set.

No blocking issue found. `pnpm --filter @ai-qa/web build` includes TypeScript compilation and passes. Vite's large Monaco chunk warning is non-blocking and unrelated to this change.
