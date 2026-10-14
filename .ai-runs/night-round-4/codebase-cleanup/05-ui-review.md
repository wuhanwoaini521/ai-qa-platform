# UI review

## Result

The recurrence panel now distinguishes three states: loading, a successful empty history, and a failed request. The failed state is visibly retryable; retry returns to the real empty result without implying history was absent during the error.

A delayed stale response was tested against a newer selected failure. Even with duplicate requests for each selection, the current card retained the selected failure's empty result after stale responses completed. The captured error and recovery screenshots are in `evidence/after/`; the request sequence and assertions are in `evidence/recurrence-error-retry-and-race.json`.

## Scope and safety

The embedded failure detail and `/failures` compatibility redirect remain. Only the unreachable standalone queue/header branch and its styling/text were removed. No AI/Jev or Apply action was used.

## Not checked

No axe audit, mobile browser session, or second browser engine was available. System Chrome was used because the agent-browser bundled Chrome failed to launch on this host.
