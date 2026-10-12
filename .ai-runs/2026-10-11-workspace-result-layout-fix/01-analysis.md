# Analysis

## Evidence and root-cause hypothesis

- The supplied screenshot shows the middle repair panel scrolled such that its panel heading/provider section is out of view and an amber blocker starts clipped at the top edge. Wide result panels are individually scrollable at `min-width: 1201px`; `.workspace-result-panel-heading` currently scrolls away with the content.
- The right event list contains a long unbroken pytest node ID. `.workspace-result-event-content strong` has no overflow wrapping, so the title can collide with/truncate against the event status column at the screenshot's narrow card width.
- The actual local Workspace route was reviewed in system Chrome. At its initial scroll positions all three panel headings are visible (`/tmp/aiqa-current-result-after-sidebar.png`); this distinguishes the screenshot's independent inner-scroll state from a missing component. The CSS still has no sticky context while an inner panel is scrolled, and long titles are not robustly constrained.

## Scope and impact

- Relevant implementation: `apps/web/src/features/workspace/workspace.css`; markup for panel headings and event title is in `WorkspaceRunResult.tsx`.
- Preserve the existing wide-screen internal scrolling decision and responsive breakpoints. Do not alter the run, runtime, API, database, or project data.
- Risk: MEDIUM user-visible shared result view; no state/data behavior changes expected.

## Acceptance

1. On wide layouts, each independently scrolled result panel keeps its heading visible, so its context does not disappear while reading content.
2. Long unbroken event titles wrap inside their grid column and do not overlap the status badge or panel boundary.
3. Normal initial view, internal scrolling, and responsive layouts still render without page-level horizontal overflow.
4. Frontend checks pass; real system-Chrome review confirms the affected layout.

## Validation update

A native wheel scroll in system Chrome reproduced the clipped top strip and confirmed that pinning the panel heading with a negative offset matching its 13px padding removes the strip while retaining panel scrolling. The long pytest node ID also reproduced within the narrow event column; CSS wrapping keeps it and its status separate. No markup/state change was needed.
