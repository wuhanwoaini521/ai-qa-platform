# UI review — Discovery journey pytest draft

## Browser setup and scope

- Ran the repository dev stack with `python scripts/task.py dev`; reviewed the authenticated local Quality Discovery workspace in real Chrome through `agent-browser`, constrained to `127.0.0.1`.
- The bundled agent-browser Chrome could not start on this macOS image (`VideoToolbox` symbol mismatch); using the installed system Chrome executable succeeded.
- Used a temporary completed Discovery run with one evidence-backed journey to render the completed-run state. Removed the synthetic run afterward. No draft task was created from the browser and no workspace file was written during this review.
- Opened the Features report section and User Journeys disclosure. The new “Create pytest draft” action was visible, enabled, and keyboard-focusable (`tabIndex=0`); its explanatory note states that approval is required before workspace changes. The button was not activated because activation creates a persisted runtime task. The API integration test covers task creation, approval wait, rejection/no-write, and explicit approval/write/run.

## Viewports and observations

- **Desktop — 1440×1000:** journey states/evidence and the draft action fit within the report card. Screenshot: `evidence/discovery-journey-draft-action-1440.png`.
- **Tablet — 768×1024:** report card stacks into the narrower workspace; journey action and note remain visible without clipping. Screenshot: `evidence/discovery-journey-draft-tablet-768.png`.
- **Mobile — 390×844:** journey labels/evidence wrap and the draft action remains within its card. `documentElement.scrollWidth`, `body.scrollWidth`, and viewport width were all 390px. Screenshot: `evidence/discovery-journey-draft-mobile-action-390.png`.
- At 768px, document/body widths were both 768px. The compact workspace stage/report tab strips are horizontally clipped/scrollable at phone width, but the page itself has no horizontal overflow; this is adjacent shell behavior, not introduced by the draft action.

## Findings

- **P0:** none.
- **P1:** none.
- **P2:** the existing narrow-width stage/report tab strips have constrained visible labels. Not changed in this feature; no document-level overflow and the draft action remains accessible. Disposition: leave out of scope.

## Review result

The new CTA and approval-boundary copy render consistently at desktop/tablet/mobile widths, with a visible keyboard focus target. No blocking UI issue found. Actual click-through is covered at the API/runtime integration boundary rather than by creating an extra persistent task in the development database.
