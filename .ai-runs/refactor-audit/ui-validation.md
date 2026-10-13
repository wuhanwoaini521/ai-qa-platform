# UI Validation

## Changes and evidence

The Settings repair-mode copy now explicitly states that AUTO can prepare a proposal but does not write source or start unattended retries; a person must Apply and separately start verification. English and Chinese strings remain in parity. This is a safety-clarity update, not a broad visual redesign.

Screenshots saved under this report directory:

- Settings before/after at 1440px: `ui-before-settings-1440.png`, `ui-after-settings-1440.png`.
- Settings after at 768px/360px: `ui-after-settings-768.png`, `ui-after-settings-360.png`.
- Workspace before and loaded: `ui-before-workspace-1440.png`, `ui-after-workspace-loaded-1440.png`.
- Project and run flow: `ui-after-projects-1440.png`, `ui-after-run-1440.png`.
- Bound case/run observation at desktop and narrow sizes: `ui-after-bound-workflow-1440.png`, `ui-after-bound-workflow-768.png`, `ui-after-bound-workflow-360.png`.

## Responsive checks

At 768px and 360px, both Settings and the workspace run-details overlay were checked with `document.documentElement.scrollWidth` and `document.body.scrollWidth`; each matched the viewport width (no horizontal overflow). At 360px, long run titles truncate, while status and event rows remain readable. No unrelated UI redesign was attempted.
