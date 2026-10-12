# Plan — Workspace Test Case Selection and Layout

## Design direction
- **Palette/type:** reuse the Workspace's existing surface, border, ink, accent, and form-control tokens; keep the compact toolbar's current 11–12px label hierarchy.
- **Layout:** place a clearly labeled current-case identity/selector on the left of the embedded case toolbar and keep “New Test Case” on the right. The selector uses the full project case collection; its options combine canonical case ID (or external/fallback ID) with title. On narrow viewports, scope and create action wrap rather than forcing a two-column detail view.
- **Principle:** reveal the missing primary navigation in the work surface without duplicating the entire case list already available in the collapsible context rail. Preserve full-width case detail and avoid adding a new panel/page.

## Self-review
A two-column list/detail restoration would make 11 cases visible at once but would duplicate the context rail, shrink the detailed case editor, and require a separate mobile layout. A native selector keeps the embedded Workspace compact, exposes all cases (including those beyond the rail's ten-item limit), and fills the otherwise action-only toolbar. It follows the existing case/design selector pattern in Automation Studio.

## Implementation and Verification
1. Add a tested case-selection view model for empty, single, multiple, and fallback-ID states.
2. Render a labeled native selector or static current-case identity in Workspace mode; leave standalone `TestCaseList` unchanged.
3. Pass the selected `TestCase` to Workspace's existing `selectCase` context helper so requirement/design/binding and stale run context stay consistent.
4. Refine toolbar styles with existing tokens and responsive wrapping.
5. Run web tests, lint, typecheck, build, and diff checks. Verify live switching between real project cases, URL/detail/context, empty/single case behavior where available, and desktop/tablet/mobile/light/dark layout; perform an independent code/UI review and regression.
