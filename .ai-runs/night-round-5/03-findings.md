# Findings — night round 5

## Product findings

No confirmed P0/P1 product failure was found in the executed regression. Full automated suites, API contract checks, and the isolated rejection journey passed.

## Limitations / observations

- **Environment — independent review blocked:** Orca remains at `/usr/local/bin/orca`; the prior attempt failed with `Unable to determine Orca.app path from symlink`. Self-review is not independent.
- **Environment — PostgreSQL and OS matrix not run:** `AI_QA_TEST_DATABASE_URL` was unset; this run was macOS only.
- **Environment / authorization — live AI/Jev not run:** gated acceptance tests were skipped; no provider invocation was authorized in this round.
- **Build warning (P3, existing):** Vite completed but warns about chunks larger than 500 kB (including Monaco editor and worker assets). No build failure; bundle optimization is out of scope.
- The manually seeded disposable dashboard run had zero aggregate counters because the fixture bypassed the normal `TestRunService` terminal aggregation path. This is a fixture limitation, not evidence of a production counter defect; the rejection route itself was verified against the persisted synthetic failure.
