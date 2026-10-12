# overall product UI redesign

- run-date: 2026-10-11
- task-type: ui-redesign
- scale: standard

## Review fixes
- Replaced hard-coded skeleton gradient stops with `--surface-inset` / `--surface-hover` so dark mode no longer shows a light placeholder flash.
- Tightened the initial KPI layout after the desktop measurement showed excessive card height; retained the metric band, navigation footer and mobile one-column behavior.
- Following user feedback that the first pass was too subtle, replaced the floating app frame with a full-height navigation rail/open canvas; flattened nested Workspace panels and criterion cards; restyled workflow stages and lifecycle tabs as compact step/tab navigation.
- Rechecked the resulting desktop, tablet and mobile layouts and dark code workspace; no follow-up CSS or behavior fix was required.
