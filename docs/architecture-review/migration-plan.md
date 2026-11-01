# Migration and Rollback Plan — Candidate B (Not Started)

**Status:** Planning only. Phase 5 gate is deferred; do not implement this plan until the architecture decision is closed and the exact phase design/acceptance is approved. No production code/schema was changed for this review.

## Principles

- Keep PostgreSQL/SQLite compatibility and existing user data. No destructive migration until all readers/writers are migrated and recovery is rehearsed.
- Add versioned fields and adapters before changing persisted semantics or API payloads.
- Preserve deterministic Pytest results and current approval behavior.
- Retain existing task/run/event/artifact IDs and external references.
- Roll out one bounded phase per isolated branch/worktree; retain a reversible commit/checkpoint, migration downgrade strategy, and data backup evidence.
- Restart recovery must prefer an explicit `BLOCKED`/operator decision over replaying a possibly effectful step.
- No project-wide migration to an OSS framework is in scope.

## Current state boundary to preserve

- Task tables: `agent_tasks`, `agent_task_steps`, `agent_task_events`, `agent_task_evidence`, `agent_task_artifacts`, `agent_task_decisions`.
- Test execution tables: `test_runs`, `test_executions`, `execution_jobs`, worker/session/artifact records.
- Discovery: `quality_discovery_runs` with bounded JSON `result`/events and optimistic version.
- API read models: `RuntimeProjection` joins task/run history; task EventSource uses a DB cursor. Discovery reads stored result events and live in-memory fan-out.
- Alembic chain currently contains migrations `0001`…`0015`; PostgreSQL CI uses a disposable Postgres 16 database, and SQLite is the local default.

Before each phase, independently export schema/current Alembic head and take a verified backup of an isolated test database. Never point rehearsal/rollback scripts at a developer or production database.

## Recommended staged plan

| Stage | Scope / compatibility approach | Acceptance and tests | Rollback point |
|---|---|---|---|
| 0. Baseline and contracts | Record current API/OpenAPI, status vocabularies, event cursors, evidence IDs, migration head and golden workflows. Do not change schemas. | Contract inventory; SQLite and PostgreSQL baseline; persisted fixture export with secrets removed; approved restore rehearsal. | No production change; baseline commit/evidence only. |
| 1. Add event/evidence envelope version | Add optional schema-version, correlation, source/provenance and parent references additively. Keep all current fields/events readable. Write a compatibility mapper, not a parallel event store. | Migration upgrade/downgrade; old/new API schema tests; task cursor replay; Discovery result/event adapter tests; redaction/ownership tests on both DBs. | Feature flag off; old readers continue. Downgrade only if new fields are unused or safely nullable. |
| 2. Dual-read / controlled dual-write | New execution paths emit the normalized envelope alongside existing persisted state where required. The legacy model remains authoritative until equivalence is proven; do not dual-emit side effects. | Compare IDs, event counts, cursor ordering, artifact hashes and statuses for the same isolated workflow; no duplicate events on retry/reconnect. | Disable new projection/write path; keep legacy columns/JSON and return legacy response shape. |
| 3. Scheduler ownership and recovery | Make task/child run ownership, lease/heartbeat, claim version and idempotency explicit using current repository/UoW and DB conditional updates. Keep WorkerDaemon and PytestRunner. | Concurrent claims; duplicate HTTP request; kill API/worker before and after each side-effect boundary; cancellation propagation; resume/replan behavior; SQLite + PostgreSQL; no auto-replay of ambiguous side effects. | Feature flag to old conservative scheduler; database additions are nullable/additive. Revert code only after no live lease relies on new fields. |
| 4. Discovery lifecycle convergence | Keep Discovery domain/result schema while routing execution through one Task Runtime owner. Remove standalone scheduling fallback only after all callers and tests use the runtime path. Persist parent task/child run links and reconcile status mapping. | Run create/pause/resume/cancel/restart; one executor per run; no duplicate browser actions; event/evidence IDs stable; old `/api/discovery` and UI behavior preserved. | Keep old `_start` route behind a compatibility flag while the new path is validated. Do not delete old fields/events in this phase. |
| 5. Browser adapter contract | Formalize stable action/observation/evidence boundaries on current `BrowserRuntime`; test an adapter in the isolated PoC first. A candidate library cannot own a second live session in production. | Same local-site cases; browser 1.62.0 compatibility; allowed-domain/SSRF tests; deterministic evidence; failure cleanup and resource bounds. | Default to the existing Playwright adapter; remove candidate adapter config and retain old behavior. |
| 6. Workflow/Results projections | Update React to consume normalized event/evidence projections while retaining existing routes, Graphite UI, deep-link context and API fallback. No IA redesign in this architecture migration. | Web tests/typecheck/lint/build, generated OpenAPI, desktop browser flows at 1280×800, 1440×900 and 1920×1080; verify action semantics and status text. | Feature flag back to legacy projection; no data write changes. |
| 7. Security/operations hardening | Isolate untrusted Pytest workers; bound egress/resources; improve correlation/metrics and recovery runbooks only after a threat model. | Security negative tests, process/container escape policy review, secret isolation, artifact ACL checks, backup/restore and worker/API failover rehearsals. | Deployment rollback to previous worker image/profile; preserve DB data; explicitly stop new jobs before reverting worker contract. |
| 8. Legacy retirement (optional) | Only after adoption telemetry and external consumer review, deprecate dead/shadow APIs or fields. Candidate `BrowserExplorer` removal is separately gated. | No internal/external callers, supported deprecation window, compatibility tests, data retention sign-off. | Do not delete historical rows; retain compatibility readers or migration export. |

## Data migration procedure (only when stage design is approved)

1. **Preflight:** assert target DB name/environment is isolated; verify backup checksum/restore; identify DB dialect and Alembic head; run read-only row counts and foreign-key checks.
2. **Expand:** add nullable columns/tables/indexes and version fields. Use dialect-safe Alembic operations. Do not rename/drop legacy columns or overwrite JSON blobs.
3. **Backfill:** deterministic, idempotent batches keyed by existing primary IDs. Record a completion marker and per-batch counts/checksums. Redact secrets in diagnostic output.
4. **Dual-read validation:** compare normalized projection against existing fields for counts, timestamps, status mapping, event sequence, ownership, evidence artifact hashes and parent IDs. Stop on mismatch.
5. **Switch reads:** feature flag per route/read model; keep old API fields and clients compatible. Record fallback rate and mismatch count.
6. **Switch writes:** make the new representation authoritative only after all readers can tolerate it. Maintain legacy-compatible fields during a documented compatibility window.
7. **Contract:** stop dual-write after parity evidence and version support policy are approved. Removing old columns/data requires a separate gate and backup/retention sign-off.

## API and interface compatibility

- Keep `/api/tasks`, `/api/runs`, `/api/discovery`, SSE route names and current task/run identifiers stable.
- Add event/evidence fields as optional/additive; do not repurpose an old event name or status meaning.
- Keep old client projections working through a mapper until all supported clients pass contract tests.
- Provide explicit status mapping from TaskStatus, TestRun status, and DiscoveryStatus to display categories; retain original domain status in payloads.
- Preserve `Last-Event-ID` replay semantics. If a new unified cursor is introduced, support old cursor queries until the old event history is migrated/retired safely.
- Keep OpenAPI generated schema current and require CI contract drift checks.

## Test migration and reproducibility

- Retain current tests while adding contract tests. Do not rewrite all existing tests around the new framework.
- Every state migration test must run on SQLite and the configured PostgreSQL lane; verify migration upgrade/downgrade and schema comparison.
- Test old fixtures and missing/null legacy fields. Seed only disposable fixtures, never runtime/user DBs.
- Separate provider fixtures from real provider tests. No real provider is required for core deterministic test lifecycle; if a paid/remote call is proposed, require explicit cost cap, provider identity, sample, consent and stop condition.
- Browser tests remain pinned to Playwright 1.62.0. Use only controlled loopback sites unless separately authorized.
- Test restart at each side-effect boundary: before action, after dispatch/before confirmation, after file write/before status persist, after Pytest exit/before Run persist, and during SSE replay.

## Rollback and recovery

- Keep each production rollout behind a feature flag with a tested old-path fallback.
- Schema changes are expand-only initially. A code rollback may leave additive nullable columns/tables in place; do not immediately downgrade data-bearing schema.
- If event parity fails, route reads/writes back to legacy model and freeze destructive cleanup; preserve both copies until reconciliation.
- If task/worker claims become ambiguous, stop new claims, mark active work `BLOCKED`, inspect actual process/workspace state, and replan only after operator review.
- If a browser adapter fails, close only sessions created by that adapter, return to the existing Playwright adapter, and retain failure evidence.
- Restore production data only through a separately approved, previewed runbook. No automatic restore, reset, or cleanup.

## Release gate per stage

Before an implementation stage begins, write a stage design and acceptance criteria, create an isolated branch/worktree, assign one writer per file, run scoped deterministic tests, obtain fresh independent Reviewer and QA reports, and document rollback. After each verified milestone, update `docs/agent-handoff.md` with commit, actual test commands/results, unresolved issues and next command. Do not mark a stage done on compilation or synthetic fixtures alone.
