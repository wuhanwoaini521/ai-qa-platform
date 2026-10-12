# Analysis

- `FailureWorkflowService` previously represented repair state in `FailureAnalysisORM.result` and trace events. GET `list_history()` reconciled verification, emitted events/results, auto-rolled back, and recorded locator history; `get_repair_workflow()` also persisted reconciliation. `FailureRepository.latest_failure_snapshot()` cleared expired ciphertext when read.
- Existing domain enum `FailureRepairState` and API model `FailureRepairWorkflow` are reused, preserving state/action names.
- `failure_analyses` is the legacy source of repair state. `ai_invocations` had run/task/decision metadata but no unique repair-attempt key; shared `run_id` is ambiguous for multiple failures/analyses.
- `apps/api/app/api/quality.py` is the existing quality router and `/api/quality` has project-read authorization. Existing quality endpoints require project scope, so funnel also requires `project_id`.
- `QualityPage` already consumes project-scoped quality data; no UI change was requested. `PlatformHealthService` is not a domain funnel owner.
- Audit item: `docs/AI_JEV_ARCHITECTURE_AUDIT.md` P2 #4 identified read-path state/event writes.
- Compatibility approach: retain and keep reading old analysis result/events; add a constrained state table and backfill only records with repair evidence. Leave ambiguous old AI invocations unlinked rather than misattribute them.
- TDD seams: transition validator/persistence; migration up/down/backfill; failure GET read-only semantics; quality funnel aggregates and project isolation.
- Risk: HIGH (workflow persistence, migration, async reconciliation, telemetry). No external service/browser action is needed.
