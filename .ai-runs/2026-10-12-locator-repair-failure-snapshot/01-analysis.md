# Analysis

## Existing evidence path

`live_browser_plugin` instruments the Playwright page used by pytest and emits `session.finished.page_evidence` (URL, controls, recent steps, console/network). `TestRunService._record_browser_event` redacts and persists that JSON in `browser_sessions.page_evidence_json`; `persist_suite_result` later links the session to `test_executions`. Failure diagnosis reads it through `FailureRepository.latest_browser_session` / `FailureEvidenceService`. No storage state, a11y tree, DOM snapshot, or successful-element fingerprint is persisted today. Locator verification in `FailureService.generate_repair_proposal` creates a new context and navigates to the URL, so auth-protected pages lose their authenticated state. The distributed `WorkerDaemon` currently does not install the live-browser plugin.

## Design

- Extend the existing pytest live-browser plugin; capture only at call failure, redact page evidence using the shared `SensitiveRedactor`, encrypt storage state before the event log is written, and mark missing baselines explicitly.
- Transfer the encrypted snapshot through the existing `SuiteExecutionResult` path. Host processes decrypt the per-run envelope in memory and encrypt storage state at rest using the platform key; persist sanitized bundle metadata and encrypted state with a configured TTL on the existing browser-session record.
- Extend the worker's existing `PytestRunner` invocation to use the same plugin and return encrypted snapshot transfers; do not create a second browser execution path.
- `FailureService` restores the encrypted storage state into the existing `BrowserRuntime` before navigating to the captured URL. Restore failures remain explicit and never fall back to a claim of replay. No actions are replayed; DTO records the captured URL/storage safe point and side-effecting steps not replayed.
- Return a typed, redacted `FailureSnapshotBundle` in the repair workflow DTO, including `INSUFFICIENT_EVIDENCE` when no live page evidence exists.

## Safety/limits

Storage state is never written in plaintext. It is capped and encrypted with an ephemeral per-run key before plugin telemetry reaches disk; the trusted host re-encrypts it using the platform secret before database persistence. Expired ciphertext is deleted on read/cleanup. DOM/a11y and event payload sizes are bounded, sensitive form values are removed before shared redaction, and snapshot fields exclude secrets from API DTOs.
