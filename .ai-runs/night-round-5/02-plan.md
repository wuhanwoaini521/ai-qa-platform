# Plan — night round 5

1. Run repository lint/static checks and the official `pnpm test` suite (SQLite lane, frontend tests/typecheck/lint/build); preserve full outputs under `evidence/` or `/tmp` before summarizing.
2. Run the documented browser-free quickstart test suite and generated OpenAPI/type checks without overwriting existing untracked contract artifacts.
3. Verify runtime/API and the rejected-proposal Golden Journey only on a newly isolated disposable database and local ports; never attach to the existing 8001/5174 services or regular runtime data.
4. Record unavailable lanes (PostgreSQL, Windows/Linux matrix, gated live AI/Jev) and exact independent-review status. Do not claim PASS for a blocked required gate.
5. Review commits and `git status`, write the regression and final acceptance reports, then commit only round-five evidence as a separate classified commit. Do not stage or modify inherited user work.

## Matrix

| Layer | Planned check |
|---|---|
| Static / repository | `pnpm lint`; OpenAPI/type generation check (read-only comparison); `git diff --check` |
| Automated backend | Full `pnpm test` SQLite suite, plus quickstart examples |
| Automated web | Included in `pnpm test`: web tests, typecheck, lint, production build |
| Runtime / API | Disposable local FastAPI startup, readiness, auth, representative success/error responses |
| Browser / Golden Journey | Isolated local UI, persisted Reject → reload → Apply denied/source unchanged |
| PostgreSQL | Run only if a safe test database is available; never use unknown user data |
| Cross-platform | Current macOS only; report CI Windows/Linux lanes as unverified |
| Live AI/Jev | Do not invoke without explicit credentials/authorization; report gated tests |
| Independent review | Orca only; if unavailable, retain `PARTIAL` |
