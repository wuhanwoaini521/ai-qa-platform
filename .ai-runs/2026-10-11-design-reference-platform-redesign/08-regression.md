# Regression

- Shared shell: verified Dashboard, Projects, Settings, Workspace requirement, and Workspace run-result routes in system Chrome.
- Core Workspace navigation: switched project without stale run query context; clicked stage step and confirmed the heading changes; verified evidence open/close behavior and internal access to the complete repair timeline.
- Responsive: 1440×1000, 768×1024, and 390×844. `documentElement.scrollWidth` equaled viewport width at each; no page-level horizontal overflow.
- Theme: actual browser dark token rendering checked; system remains light/dark token-driven.
- Error/data states: reviewed an actual run-level `ERROR` with missing per-case results and no linked Failure. Existing unavailable-data messaging remained accurate.
- Browser page errors: 0 across the smoke routes.
- Automated: Web tests 105/105; Web typecheck; root lint (Ruff, formatting, i18n parity, ESLint); production Web build; `git diff --check` all passed.
- No Python/API suite was rerun because this change is frontend-only and touches no Python/API code. No PostgreSQL, Worker, provider, or real test-execution workflow was started.

**Regression result:** PASS for the scoped UI redesign.
