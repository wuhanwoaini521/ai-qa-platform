# Request

用户请求："侧边栏应该这样。"（附参考图）

## Parsed scope
- Task type: `ui-redesign`; scale: standard; risk: MEDIUM (shared app navigation and project context across routes).
- Goal: align the application sidebar with the reference: a distinct rounded panel, project context near the top, searchable navigation, clear active state, and a desktop icon-rail collapse mode.
- Keep existing destinations, project-switch routing, navigation search, platform disclosure, language switch, and responsive behavior. Do not fabricate reference-only items (credits, favorites, help center, unread counts, or user identity).
- Repository: `/Users/hans/Code/github/ai-qa-platform`; branch `main`; starting HEAD `cdf954a`.
- Reference image: `/var/folders/jn/l50pwhbx1zd3vrnk9dkp73000000gn/T/pi-clipboard-05c4676d-ddd9-488d-87b6-53ef14ba998d.png`.

## Initial git status
Existing uncommitted UI redesign changes were present in `AppLayout.tsx`, `navigation.ts`, `Header.tsx`, Workspace components/styles, workspace translations, `index.css`, and `workspace-context.test.mjs`; `projectPaths.ts` and `.ai-runs/` were untracked. These are pre-existing user/session changes and must be preserved. This task will make incremental edits to relevant files only; no staging, commit, or push is requested.
