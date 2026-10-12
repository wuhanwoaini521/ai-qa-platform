# Plan

1. Add typed snapshot/replay DTOs and a shared authenticated-encryption helper; add failing tests for plugin failure capture, explicit missing baseline, encrypted persistence/TTL, Verification Browser restoration, and insufficient evidence.
2. Implement plugin capture/redaction/fingerprinting and bounded encrypted storage state. Wire snapshot collection through API local and worker pytest paths.
3. Persist snapshots safely on browser-session records; add additive migration and repository TTL handling.
4. Update Locator Repair Verification to restore storage state first, report restore failures and non-replayed side effects, and expose bundle/replay status in DTOs.
5. Run scoped tests, then backend regression/type checks; inspect diff and preserve pre-existing workspace changes.
