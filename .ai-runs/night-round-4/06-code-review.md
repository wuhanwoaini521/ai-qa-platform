# Code review — night round 4

## Structured second pass

- **Correctness:** `REJECT` is offered only for `PATCH_READY`; the service rechecks that server-owned action before persisting `BLOCKED` with the stable `HUMAN_REJECTED` code and `repair.rejected` event. `get_repair_workflow` does not reconcile a rejected proposal back to `PATCH_READY`.
- **Source-write boundary:** rejection never calls `FailureService.apply_repair`; the existing Apply action remains the only locator-patch write path. Apply is denied after rejection. API regression and the isolated live API check verified a 422 and unchanged source bytes. Existing explicit-Apply/verification tests remain green.
- **Concurrency/edge cases:** state-machine movement loads the repair row under `SELECT ... FOR UPDATE` and refreshes an already-loaded ORM identity before validating the transition. Thus concurrent Apply/Reject must validate against the current state; PostgreSQL runtime confirmation remains outstanding. Repeated rejection is naturally denied because `BLOCKED` no longer advertises `REJECT`.
- **Persistence/API compatibility:** reuses `BLOCKED` and the existing block-reason field, so no database enum migration or new persistence column is needed. The response addition is additive; OpenAPI and generated TypeScript were regenerated using the existing user-provided tooling.
- **Complexity/duplication:** reuses the existing state machine, workflow history and centralized API client. No new runtime, provider, queue, dependency, or auto-apply path was added.
- **Validation:** 99 backend/API/architecture tests and 146 web tests pass; explicit Apply behavior and API contract parity are included. Browser persistence and denial are independently exercised against an isolated service.

## Review disposition

No P0/P1 issue was found in the implementer's structured second pass. This is **not** an independent review: Orca could not start. Exact blocker and disposition are in `08-independent-review.md`; the required independent gate remains open, so round 4 is not PASS.

Known validation limitation: SQLite does not exercise PostgreSQL row-lock behavior. The relevant concurrency guard is present, but PostgreSQL integration remains for final acceptance if available.
