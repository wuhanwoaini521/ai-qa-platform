# overall product UI redesign

- run-date: 2026-10-11
- task-type: ui-redesign
- scale: standard

## Changes delivered
- `apps/web/src/index.css`
  - Reduced shared control/card radius and section rhythm; narrowed the desktop sidebar from 286px to 256px and shifted it to the existing frame surface token.
  - Changed the selected navigation state from neutral gray to a restrained surface-active tint with a blue icon; hover surfaces are now token-based.
  - Tightened shared card headers/body, data-table cell spacing and the overview strip to increase information density without removing content.
  - Increased modal dimming from 28% to 36% to strengthen the focus overlay; the existing centered dialog and secondary/primary action order remain intact.
  - Replaced hard-coded light skeleton colors with surface tokens so loading states follow light and dark themes.
  - Compact Dashboard KPI content and added restrained blue/green/red/violet icon tints using existing semantic theme tokens.
- `apps/web/src/pages/DashboardPage.tsx`
  - Applied semantic tone classes to the four existing KPIs; no labels, values, actions, data contracts or routes changed.
- No workflow, API, dependency, lockfile, or runtime data changes.

## Baseline and after screenshots
- Baseline: `/tmp/ai-qa-overall-ui-current-dashboard-light-1440.png`, `...-light-390.png`, `...-dark-loaded-1440.png`.
- After: `/tmp/ai-qa-overall-ui-after-dashboard-desktop.png`, `...-tablet.png`, `...-mobile.png`, `...-dashboard-dark-loaded.png`, `...-workspace-cases.png`, `...-projects.png`, `...-quality.png`, `...-settings.png`, `...-project-modal.png`, `...-dark-code-settled.png`.
- All screenshots are local temporary evidence, not committed project assets.

## Corrective redesign pass after user feedback
The initial delivery was too subtle for the requested overall redesign. Replaced the inset-card app shell with a full-height white navigation rail and open canvas; restructured the Workspace stage navigation as a slim step/tab row; removed nested card frames from the Workspace context and main panels; converted requirement tabs to underline navigation and acceptance criteria to rule-separated rows. Added a `view` modifier class to scope those styles. This pass changes the page silhouette and information hierarchy, not just tokens.

- Additional source files: `apps/web/src/features/workspace/WorkspacePage.tsx` and `apps/web/src/features/workspace/workspace.css`; `apps/web/src/index.css` now uses an edge-to-edge shell and 20px content inset.
- After screenshots: `/tmp/ai-qa-overall-ui-redesign-final-workspace-requirement.png`, `/tmp/ai-qa-overall-ui-redesign-final-dashboard-loaded.png`, `/tmp/ai-qa-overall-ui-redesign-final-projects.png`, `/tmp/ai-qa-overall-ui-redesign-final-quality.png`, `/tmp/ai-qa-overall-ui-redesign-final-dashboard-dark.png`, `/tmp/ai-qa-overall-ui-redesign-final-dark-code.png`.
