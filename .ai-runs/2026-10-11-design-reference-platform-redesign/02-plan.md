# Plan

## Milestones

1. [x] **Shared shell** — moved the project header above navigation/content; aligned project selection and status controls; removed the inset frame while preserving navigation and full-bleed behavior.
2. [x] **Visual language** — updated shared tokens and navigation/control states to cool white/blue-gray surfaces, crisp borders, blue active states, and clear status colors; verified dark mode.
3. [x] **Representative workflow** — updated Workspace headings/timeline/result composition and made actual error evidence discoverable without changing business rules.
4. [x] **Responsive and regression** — inspected 1440/768/390px in system Chrome; checked Dashboard, Workspace, run result, Settings/Projects; Web tests, lint, typecheck, and production build passed.

## Likely Areas

- `apps/web/src/app/AppLayout.tsx`
- `apps/web/src/components/Header.tsx`, `Navigation.tsx`
- `apps/web/src/index.css`
- `apps/web/src/features/workspace/WorkspacePage.tsx`, `WorkspaceRunResult.tsx`, `workspace.css`
- Focused frontend tests for any changed project-selection/navigation or evidence disclosure behavior.
- `.ai-runs/2026-10-11-design-reference-platform-redesign/` records.

## Review and Acceptance

- UI review: actual local app in system Chrome at 1440px, 768px, 390px; inspect screenshots, overflow, active states, and click behavior.
- Code review: second-pass diff review for route compatibility, project selection, responsive breakpoints, dark mode, loading/empty/error/success states, and unintended CSS leakage.
- Regression: `pnpm --filter @ai-qa/web test`, `pnpm --filter @ai-qa/web typecheck`, `pnpm lint`, and `pnpm --filter @ai-qa/web build`; check relevant app routes in the browser.
- Do not use real provider calls or create/execute runs for a visual task. Existing local runtime data remains read-only.
