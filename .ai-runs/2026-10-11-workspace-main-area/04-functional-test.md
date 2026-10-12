# Functional Testing

- run-date: 2026-10-11

## Automated
- `pnpm --filter @ai-qa/web test` — PASS, 113 tests.
- `pnpm --filter @ai-qa/web lint` — PASS.
- `pnpm --filter @ai-qa/web build` — PASS (`tsc -b` and Vite production build); Vite reports the existing Monaco chunks exceed 500 kB.
- `git diff --check` on changed implementation files — PASS.

## Browser
Chrome, authenticated Workspace, Automation > Code, file opened from Explorer:
- 360x640: Monaco 280x169; Explorer 230px overlay; closes after file selection.
- 390x844: Monaco 310x373; Explorer closes after selection.
- 768x900: Monaco 588x334; Explorer is collapsed by default and usable as an overlay.
- 1024x900: Monaco 612x352 with the desktop Explorer alongside.
- 1524x900: Monaco 870x352 with the desktop Explorer alongside.
- At all five sizes: no document horizontal overflow or page errors.
- At 360x640, More Tools toggled the embedded context and Problems panels successfully; context can be reopened and closed.
- Cases view at 360x640: collapsed main panel 324x349; opening context stacked it above a 324x221 main panel; no document overflow or page errors.
- Results view: 390x844 main panel 354x189; 1524x900 main panel 911x637; no document overflow or page errors.
