# Live findings

## ISSUE-001 — Verification timeline is not keyboard-scrollable

- Severity: P1 (keyboard accessibility for a core repair-status view).
- Reproduction: sign in to the local running platform, open the failure/results workspace, set viewport to 360px or 768px, then run axe 4.12.1.
- Observed: axe reports `scrollable-region-focusable` for `.failure-verification > ol`. The list's six columns overflow horizontally but the `<ol>` is not keyboard-focusable (`tabIndex=-1`).
- Evidence: `evidence/before-failures-mobile-360.png`, `evidence/before-failures-tablet-768.png`, `evidence/a11y-before-mobile-360.json`, `evidence/timeline-before-mobile-360.json`.
- Root cause: the existing horizontal overflow is attached directly to a non-focusable ordered list.
- Fix: added `tabIndex={0}` to that existing list; preserved semantic ordered-list structure and existing scrolling/layout.
- Repro after fix: at 360px, focus the list and press ArrowRight; horizontal `scrollLeft` reaches 40px. Axe reports 0 violations at desktop/tablet/mobile after the fix.
