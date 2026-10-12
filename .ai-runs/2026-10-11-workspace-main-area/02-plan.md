# Plan

1. Add a small pure layout-mode calculation based on measured workspace width, context width/open state, view, and Inspector width; cover threshold boundaries with unit tests.
2. Measure the Workspace grid with `ResizeObserver`, expose adaptive context stacking and Inspector-modal classes, default the context rail closed in compact workspace widths without overwriting the desktop preference, and preserve current focus semantics.
3. Update workspace CSS so constrained context stacks above the main area and Inspector occupies a grid column only when enough main width remains; leave existing ≤820px behavior intact.
4. Run layout-model and workspace tests, frontend lint/typecheck/build, and live Chrome checks at desktop, tablet, and phone sizes including context/Inspector interactions and resize boundaries.
5. Perform structured diff review and regression through workspace cases, automation editor, and results stage; record final worktree without disturbing pre-existing changes.
6. UI-review refinement: reclaim mobile editor height, hide redundant embedded context by default while preserving its Tools toggle, and make the <=820px file tree a usable overlay that closes after selection. Keep editor actions and Problems access available in compact mode.
