# Implementation

Changed only `apps/web/src/features/workspace/workspace.css`:

- On the wide layout where result panels are fixed-height internal scroll containers, keep each panel heading sticky. Offset it by the panel's 13px padding (`top: -13px` plus matching margin/padding) so scrolled content cannot peek through above the heading.
- Add `min-width: 0` and `overflow-wrap: anywhere` to event title grid items so long pytest node IDs wrap within their column instead of colliding with the status badge.

No markup, component state, routes, API calls, database, runtime files, or user data were changed. No new abstraction was introduced.
