# Regression

- run-date: 2026-10-11

## Coverage and results
- Frontend regression: 113 tests passed, including Workspace layout/context models and run models; ESLint and production TypeScript/Vite build passed.
- Browser regression: Automation editor and file selection at 360, 390, 768, 1024, and 1524px; More Tools context/Problems interaction at 360px; Cases context stacking at 360px; Results main area at 390 and 1524px. No page errors or horizontal document overflow.
- Desktop Explorer remains alongside the editor (1024px: 612px Monaco; 1524px: 870px Monaco). Narrow Explorer is a temporary overlay, not a persistent width deduction.
- `git diff --check` passed. No commits, dependency edits, or cleanup/reset operations.
