# Plan

1. Adjust only the existing Workspace result grid: three columns on wide desktop, two columns with the activity panel spanning below at intermediate sizes, and one column on narrow layouts. Keep the existing evidence row and natural document flow.
2. Run the real Vite UI with deterministic, mocked API responses (no backend startup or data mutation). Inspect PASSED/FAILED result states and computed layout at 1440×900, 1024×900, 820×1024, and 390×844; verify no horizontal overflow and no clipped panel content.
3. Perform a structured second-pass review of the CSS diff for breakpoint ordering, duplicate overrides, and panel reachability.
4. Run Web tests, typecheck, lint and production build; run `git diff --check`. Preserve all pre-existing work and leave everything unstaged/uncommitted.

## Acceptance

- At a wide desktop viewport, the summary, repair timeline and current task/event log occupy three side-by-side columns, matching the supplied reference hierarchy.
- Intermediate/narrow layouts intentionally reduce columns without causing clipping, overlap, horizontal page overflow, or nested panel scroll traps.
- Existing status colors, actual run content, buttons, event filters, evidence and no-data states remain unchanged and usable.
- Relevant automated checks and live browser verification pass; no backend/runtime/database writes occur.
