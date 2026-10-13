# Architecture Review

## Existing structure retained

- React/TypeScript SPA (`apps/web`) consumes the shared REST client and established API DTOs.
- FastAPI routers delegate to application services and repository/transaction boundaries.
- Failure repair reuses `FailureWorkflowService`, `FailureService`, `DecisionService`/`LocatorDecisionService`, `TestRunService`, and `BrowserRuntime`; no second Runtime, Agent, Provider, or browser lifecycle was added.
- Existing REST, SSE, and WebSocket consumers remain separate where protocol and lifecycle differ.
- The hand-maintained TypeScript DTOs remain a known drift risk; no OpenAPI-to-TypeScript generation workflow was found. No broad client rewrite was justified.

## Safety boundary change

`repair.mode=AUTO` may start one diagnosis and prepare a verified proposal, but now stops at `PATCH_READY`. The analysis path does not write source, start verification, or start another unattended analysis. Existing API actions for applying the selected proposal and separately starting exact-node verification remain in place. `start_verification` still requires the proposal to be applied; the configured rollback safeguard remains available after an explicitly started verification.

This enforces ROADMAP section 0's human-approval invariant without creating a parallel workflow or breaking the compatibility config field `repair.max_attempts`.

## Cleanup decision

The repository audit found no safe dependency or module deletion. Large modules and duplicated-looking transports have active consumers and test coverage. The only confirmed removable behavior was the unattended retry/apply logic that violated the approval boundary; details are in `cleanup-report.md`.

## Residual risks

- The opt-in live AI/Jev repair workflow did not complete in this run; a direct Jev decision smoke call is not equivalent evidence. See `test-results.md`.
- PostgreSQL-specific validation was unavailable because `AI_QA_TEST_DATABASE_URL` is unset and no local PostgreSQL/container runtime was available.
- Full OpenAPI-to-TypeScript DTO generation and broad page redesign were outside the proven-safe scope.
