# Implementation log

## Milestone 1 — behavior-preserving split

- Extracted Discovery Pydantic contracts/enums/errors to `quality_discovery_models.py`.
- Extracted exploration/runtime/planning/browser-policy methods to `quality_discovery_execution.py`.
- Extracted state graph/evidence/decision-signal recording to `quality_discovery_graph.py`.
- Extracted quality-map/journey/coverage projections to `quality_discovery_projection.py`.
- Kept `quality_discovery_service.py` as compatibility composition root with existing service methods and contract re-exports.
- Preserved prior working-tree Jev score/probability logic and config monkeypatch seam; no browser policy or API changes in this milestone.
- Refactor used source slices from the current dirty worktree, not HEAD. Existing modifications were preserved.

## Verification

- Pre-split focused baseline: **129 passed** (`test_quality_discovery.py`, `test_agent_tasks.py`, `test_recorder_service.py`).
- Post-split same focused suite: **129 passed**.
- Full `python scripts/task.py test`: backend **733 passed, 8 skipped**; frontend **138 passed**, TypeScript, ESLint, and production build passed.
- Targeted Ruff and `git diff --check`: passed.
- PostgreSQL and opt-in live-browser suites were skipped by repository configuration.

## Milestone 2 — Discovery → pytest draft

- Added `QualityDiscoveryDraftMixin` to transform only selected completed-run journeys backed by persisted state evidence and successful state-changing graph edges.
- Reconstructs start navigation and observed-control actions deterministically. Rejects ambiguous/missing edges, failed or unverified actions, unsupported action types, unsafe start URLs, sensitive values, and journeys without a grounded final heading/title assertion.
- The draft creates an existing `CREATE_TEST` task with recorded steps, no top-level browser URL/session, and zero AI-call budget. Existing task DAG conditions skip inspect/decision/act; the recorder generates code, static checks validate it, and existing approval-diff flow waits for a human.
- Added an opt-in `assertion_bypass_check` input to run the existing assertion/skip/xfail/pass-only-handler policy at both generation and validation stages.
- Reused the recorder's pytest generator. Added explicit select-by-value support for observed Discovery options while preserving legacy label-based recordings.
- Added `POST /api/discovery/runs/{run_id}/journeys/{journey_id}/pytest-draft`, guarded by `AUTOMATION_EDIT`, and a Quality Discovery journey UI action that opens the existing runtime task approval panel.
- Integration test confirms browser steps are skipped, generated pytest contains the grounded assertion, the task waits at approval, and workspace files remain absent before and after rejection; a second task is explicitly approved, writes through the existing Task Runtime path, and passes against a local fixture page.
- Review hardening: non-text search controls and malformed observed-control evidence now fail closed rather than degrading into a click or surfacing an unhandled attribute error.
