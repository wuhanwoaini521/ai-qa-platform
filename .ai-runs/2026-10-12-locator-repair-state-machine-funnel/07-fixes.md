# Review Fixes

- Concurrency test exposed duplicate LocatorRepair inserts when concurrent requests claimed the same active analysis. Repository creation now uses a nested transaction and resolves the unique-analysis race by re-reading the winner.
- Read-only review exposed snapshot TTL cleanup in a repository getter. GET now only projects EXPIRED/no-ciphertext; explicit purge is separate and runs on a write path. Tests assert the GET leaves stored ciphertext unchanged and purge removes it.
- Verification reconciliation and auto-rollback were removed from GET history reads and moved to the verification monitor; manual verification starts schedule the monitor, with duplicate monitor suppression by run ID.
- Failure/blocker events now persist state and reason through the state machine, while legacy analysis result shape remains compatible.
- Migration backfill was hardened for malformed JSON/date values, missing verification-run references, legacy applied proposals, and event-only state evidence.
