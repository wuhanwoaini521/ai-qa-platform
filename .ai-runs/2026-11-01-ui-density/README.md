# UI density pass — flaky & workers (2026-11-01)

Symptom reported: these pages read denser than the rest of the product and used a different card
language (boxed KPI tiles, inline spacing, column rules in tables).

## What changed

- One page-level layer in `index.css` (`.page-container` scope):
  - KPI cards become one row: icon tile (40px, token colors) + label + 30px value + optional subtitle
  - toolbar becomes `.page-toolbar` (`12px 16px`, 16px gaps, consistent field widths)
  - table rhythm: `12px 16px` header, `14px 16px` rows, single horizontal rule, no column rules
  - empty states use `.page-empty-state` instead of inline padding
- `FlakyPage.tsx`: removed inline grid template / margins / font sizes; toolbar markup now uses the
  shared classes.
- `WorkersPage.tsx`: inline `rgba(...)` icon backgrounds replaced with token classes
  (`stat-icon.is-blue/is-green/is-amber/is-violet`).

## Evidence

`evidence/flaky-1440x900.png`, `evidence/workers-1440x900.png`, plus 1280x800 for both. No horizontal
overflow at either size; authenticated pages, real data.

## Verified

`tsc --noEmit`, ESLint (both pages), frontend test baseline 234 passed, i18n unchanged.
