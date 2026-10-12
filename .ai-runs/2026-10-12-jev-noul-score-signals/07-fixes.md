# Review Fixes

- Preserved one daily decision request for required Discovery action choice when optional score recommendations are enabled.
- Tightened signal trust to finite [0, 1] probability/score and confidence meeting the effective runtime minimum; fallback and unavailable results never masquerade as numeric evidence.
- Made Discovery score telemetry non-blocking and emitted explicit unavailable/fallback samples while keeping the existing candidate order.
- Added candidate-correlated latency/token metadata and support for nested Discovery event metadata in offline evaluation.
- Added observed-control context to the same-function question and retained only bounded, redacted evidence. The signal remains advisory; low trusted probability blocks Apply, while unavailable probability is not interpreted as low.
- Added focused tests for event normalization, evidence context, request reserve, fallback behavior, and budget-denied browser action.

All fixes are included in the final regression run; see `04-functional-test.md`.
