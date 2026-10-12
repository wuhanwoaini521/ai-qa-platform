# Plan

1. Define the transition graph and one `LocatorRepairStateMachine` using the existing typed repair-state enum; test legal and illegal transitions.
2. Add LocatorRepair persistence/repository and migration from 0009 with constraints, AI invocation correlation, legacy backfill, downgrade, and migration regression.
3. Route repair lifecycle mutations through the machine. Keep legacy event/result history; make failure GET projections read-only and move verification/rollback/snapshot cleanup to write/background paths.
4. Add authenticated `/api/quality/repair-funnel` DTO/service with project-scoped state counts, stable blocker codes, and correlated invocation totals/breakdowns.
5. Verify state, migration, read-only, funnel, and legacy behavior; run full regression/lint and second-pass review.

## Acceptance

- Legal transitions persist; illegal transitions raise without changing stored state.
- Failure GET paths do not write analysis events/results, LocatorRepair state, or snapshot data.
- Upgrade/backfill/downgrade/re-upgrade retain old result/event data.
- Funnel stage/blocker counts match fixture rows; AI invocation totals/breakdowns reconcile by explicit repair ID and project scope.
- Existing failure workflow/API state and action vocabulary remains compatible.

## Result

All acceptance items passed on SQLite. Full test/lint results and the second-pass review are in `04-functional-test.md`, `06-code-review.md`, and `08-regression.md`. PostgreSQL/live-provider lanes were unavailable or opt-in and are recorded as limitations.
