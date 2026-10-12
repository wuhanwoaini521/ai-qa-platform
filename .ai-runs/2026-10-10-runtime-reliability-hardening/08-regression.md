# Regression Coverage

- Backend: full SQLite test suite, including API, domain/core, integrations and Worker unit coverage — 658 passed, 7 skipped.
- Provider/config: environment-over-YAML precedence, no-probe disabled/unconfigured status, safe output redaction, runtime-managed settings, and Jev fallback/threshold decisions.
- Worker/distributed execution: maximum in-flight concurrency, supported-browser selection, atomic claim behavior, unauthorized failure ownership, registration rejection, cancellation and shutdown ordering.
- Repair: real AI + Jev locator candidate, source change, exact-node verification, safe low-confidence block, UI state, and persisted rollback/verification reporting.
- Frontend: 104 unit tests, typecheck, lint, translation parity, responsive real-browser viewport checks, and production build.
- Architecture: task service-boundary static tests and Python lint/format gates.
- Data safety: no worker attached to existing runtime queue; existing 200 jobs remained unclaimed; no database reset or credential rotation.

Blocked coverage: PostgreSQL/Docker lane; full Worker acceptance against the existing unknown queue; Chromium bundled-browser installation (system Chrome substituted only for browser execution, not for real-provider behavior); optional basedpyright language-server test.
