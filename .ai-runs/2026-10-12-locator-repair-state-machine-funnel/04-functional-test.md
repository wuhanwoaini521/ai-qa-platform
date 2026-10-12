# Functional Test Results

## State machine

- Legal transition matrix cases pass, including idempotent reconciliation.
- Invalid transitions raise `IllegalLocatorRepairTransition`; a new DB session verifies persisted state remains unchanged.
- Safe blocker-code behavior is covered; failed repair rolled back retains its diagnostic reason.

## Persistence and compatibility

- Fresh upgrade creates the new table and AI-link column.
- Legacy result and event backfills, applied repair mapping, non-repair analysis exclusion, invocation-row preservation, downgrade to 0009, and re-upgrade are covered.
- Legacy analysis result/event data remains readable through downgrade.

## API and read-only behavior

- `GET /api/quality/repair-funnel?project_id=...` returns all stage/state counts, stable blocker distribution, and invocation summaries that match actual linked `ai_invocations` rows; project filters isolate data.
- Failure analysis/history and repair-workflow GETs return projected verification state without changing stored analysis JSON/events, LocatorRepair state, or expired encrypted snapshot data.
- Expired snapshot response reports EXPIRED and never contains encrypted state; explicit purge clears it on a write/maintenance path.
- Invocation-context test verifies `AIRepository` persists the active LocatorRepair ID.

## Execution

- Full backend suite: **733 passed, 8 skipped**, 741 collected.
- Frontend unit tests: **138 passed**; typecheck, lint, and production build passed.
- PostgreSQL and opt-in live-browser/provider lanes were skipped due missing test DB URL/explicit live opt-in.
- No external provider or browser target was accessed.
