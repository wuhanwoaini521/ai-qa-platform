# Repository Analysis / Baseline

Read `AGENTS.md`, README, architecture, execution, Worker, distributed execution, AI Provider, Failure Intelligence, deployment/security docs, config, manifests, tests, CI, migrations and runtime scripts.

Observed at baseline:
- API/Web/Worker/PostgreSQL were stopped. Started API/Web with documented `pnpm dev`; both health/readiness and Web root answered.
- Existing SQLite DB had no Alembic version row; API startup migrated it through `0007_quality_discovery_version`. Existing data was not reset or deleted.
- Local cluster reports 0 workers and 200 queued jobs from 2026-09-23. Worker was not attached to this store because job intent is unknown and claiming could execute existing work.
- Real AI `/api/ai/status`: `REAL_CONNECTED`, streaming, no fallback. Real Jev `/api/decision/runtime-check`: `CONNECTED` / `READY`. Only safe status fields were recorded.
- Environment endpoint override reproduction failed: setting `QA_AI_BASE_URL` / `JEV_BASE_URL` did not change YAML literal URLs.
- `pnpm test`: 630 passed, 17 failed, 6 skipped. Web test script run separately: 104 passed. `pnpm lint`: 9 Ruff findings. `pnpm build`: passed with oversized Monaco chunk warning.
- Local Docker/PostgreSQL/browser unavailable. Initial full uv sync failed compiling locked basedpyright Node dependency on this host; installed remaining packages with that optional tool excluded.
- Full reproduction classification and evidence: `docs/audits/runtime-hardening-baseline.md`.

No application source changes were made before this baseline artifact.
