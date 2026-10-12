# Plan

1. Extend the existing Workspace run presentation model with terminal-status and repair-notice helpers; render localized terminal outcomes and distinguish “repair not needed” from a genuinely blocked failed run. Test terminal/active and repair applicability states.
2. Refine only the result-view layout: two-column summary/repair overview, full-width run context/event stream, neutral token-based surfaces and table-like event rows. Remove fixed-height nested panel scrolling while preserving responsive breakpoints.
3. Run the targeted frontend test, then typecheck/lint/build and translation parity. Inspect the actual UI at desktop/tablet/mobile if the browser can be safely run; stop any temporary dev services afterward.
4. Independently review the changed diff, fix findings, rerun affected checks, and record acceptance without touching other uncommitted work.
