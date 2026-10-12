# Regression

- Frontend tests: 105 passed, 0 failed.
- Lint: passed.
- Production build and TypeScript compilation: passed; only the existing large Monaco chunk warning.
- `git diff --check`: passed.
- Real Chrome checked initial desktop view, scrolled desktop panel, actual long event title, tablet after resizing loaded result, and mobile stacked result.
- No run was started; project/run data was read-only. No backend, API, database, worker, or queue changes.

No regression attributable to the CSS fix was found. See UI review for the isolated tablet reload empty-state observation.
