# Fixes

## Screenshot findings

1. **Scrolled repair-panel context / clipped warning strip** — Added a sticky panel heading at the wide internal-scroll breakpoint. Adjusted its top offset to account for the panel's 13px padding after browser review showed the initial offset left a strip of the warning visible. Verified the final scrolled state in `/tmp/aiqa-result-sticky-scrolled-final.png`.
2. **Long event title overlapping/crowding status** — Constrained the title grid item and enabled anywhere wrapping. Verified the real pytest node ID and PASSED badge at desktop and tablet widths.

No other source or data changes.
