# Fixes — night round 4

## ISSUE-001 — Persist proposal rejection

- Added server `REJECT` action and route; the existing state machine records the decision as `BLOCKED / HUMAN_REJECTED` and appends `repair.rejected` to the existing analysis history.
- Prevented the trusted-proposal reconciliation branch from reopening a human-rejected candidate. The persisted block reason is surfaced in the workflow response and drives the UI status.
- Added row locking with identity refresh before state-machine transition validation to serialize competing Apply/Reject transitions.
- Replaced local React-state clearing with a real API request. The UI retains the rejected proposal for audit, removes Apply/Reject, explains that source was not changed, and offers reanalysis.
- Extended backend state/API regressions to prove event/state persistence, Apply denial, and unchanged source; generated the additive OpenAPI and web type contract using existing tooling.

No code path was added that writes source during rejection. Human approval remains required for Apply, and repair verification still depends on the original test's actual result.

## Verification-driven adjustments

- The first new tests failed as expected (missing action and 404 route); both passed after implementation.
- During second-pass review, the row-lock read was changed to `populate_existing=True` so a concurrently updated ORM row is refreshed before transition validation.
- Ruff's format check identified four formatting-only issues in the new code/test; they were corrected and the final formatter check passed.
