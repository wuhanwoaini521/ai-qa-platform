# Request

The user authorized an unattended system-wide stabilization and acceptance effort: discover actual product routes/features, exercise real UI/API/runtime flows, repair confirmed problems, run final regressions, and produce the five specified `docs/audits/full-product-*.md` reports. Full PASS requires explicit evidence for workflow simplification, UI Before/After, final-code regression, and all Golden Journeys; do not infer passes from mocks or source inspection.

## Scope and constraints

- Repository: `/Users/hans/Code/github/ai-qa-platform`; branch `main`; initial HEAD `cdf954a`.
- Start-of-task worktree already contained 43 modified tracked paths and 3 untracked top-level entries, including extensive prior API/Worker/UI/demo changes and runtime/audit artifacts. Preserve them; do not reset, clean, or stage unrelated changes.
- Existing SQLite database and `.env` are present. Preserve data and credentials; do not print or store secret values. No production deployment.
- Earlier user constraints remain: do not delete existing data, alter credentials, or process unrelated queued jobs. Any demo Worker must remain scoped to `proj_golden_shop_v1`.
- User now asks for reversible commits at stable stages. Do not commit mixed/pre-existing user work; reassess whether isolated staging is safe after identifying the changes made in this task.

## Initial evidence

- No API, web, Worker, PostgreSQL, or Docker service was running; Docker CLI is unavailable.
- Local SQLite database is 41 MiB, migration revision matches head `0007_quality_discovery_version`.
- Database contains 26 projects, 5,000 queued execution jobs (all observed in benchmark projects), an offline Worker, and one RUNNING Golden Demo Run. Before API startup, a read-only SQLite checkpoint was saved under `/var/folders/jn/l50pwhbx1zd3vrnk9dkp73000000gn/T/aiqa-full-audit-prestart-up3sumbu.db`.
- Effective config is authenticated development mode, SQLite, real `openai-compatible` AI and Jev enabled, with both keys configured. Values are not recorded.
- Runtime workspace/project `proj_golden_shop_v1` exists with one requirement and eleven cases. Worker must be scoped to it.
