# UI Review — Per-Case Run Results Visibility

- The result list is prominent immediately below the Run header; consistent green/red rails and status pills make the full execution set scannable. The failed row keeps its own error excerpt, expandable full evidence, and Failure action.
- Runtime Results sits beside Overview as a discoverable tab and reuses the same presentation. The Runtime drawer has a single-column list at 736px; wide Workspace uses a two-column list; mobile stacks identity, status and duration without horizontal page overflow.
- Light and dark themes use existing design tokens. Both English and Simplified Chinese translations were exercised.
- Verified axe-core 4.12.1 for the shared component and Runtime results region: **0 violations / 0 incomplete**. A first pass exposed an invalid `aria-label` on a generic span; it was removed and duration is now visibly labeled. Full error details are expandable on short/narrow layouts when line breaks or longer content can be clamped.
- This was a scoped usability pass, not a complete WCAG audit.
