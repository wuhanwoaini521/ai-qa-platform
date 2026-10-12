# Regression — Per-Case Run Results Visibility

- Final web tests: **127 passed, 0 failed**.
- Final ESLint, TypeScript typecheck, production build, and `git diff --check`: all passed.
- Final browser checks: real result page has 8 rows / 1 actual failed row; mocked second failure was isolated and removed; Runtime Results tab and Runs-page default verified; Flow remains available; app has no console errors.
- Responsive checks at 1524×900, 768×1024, 390×844, and 360×800: no document-level horizontal overflow. Dark and English rendering checked; original Chinese/light preference restored.
- Build retains the existing large Monaco editor chunk warning (>500 kB); this task does not change bundling.
- PostgreSQL/backend tests were not run because no backend changes were made and this task did not require a database write.
