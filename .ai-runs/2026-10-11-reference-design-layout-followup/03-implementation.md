# Implementation

- Changed only `apps/web/src/features/workspace/workspace.css`.
- Made the existing run-result summary, AI/Jev repair timeline, and current task/event log a three-column grid on wide content surfaces.
- Added a named inline-size container on the existing result surface so the layout responds to actual available content width (not only the browser viewport): at `<=960px`, summary/repair share a two-column row and activity spans beneath; at `<=620px`, all three panels stack in document flow.
- Adapted current-task metadata to its own panel width: two columns in the narrow third desktop panel, expanding to four only when the activity panel is at least 700px wide. This prevents long case identifiers from breaking into tiny fragments.
- Removed the old full-width activity override and duplicate viewport/parent-container column rules. Existing panel styles, tokenized colors, evidence, event filters and natural scroll behavior are unchanged.
- No API, backend, run state, data, translations, or user preferences were touched.
