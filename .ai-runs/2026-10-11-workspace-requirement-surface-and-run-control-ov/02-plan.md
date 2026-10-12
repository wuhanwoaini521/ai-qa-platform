# Plan

## Design Tokens / Layout

- Canvas `#F3F7FD`; paper `#FFFFFF`; ink `#1C2942`; separator `#D8E2F0`; QA action blue `#256BFA`; pass green `#22B875`.
- Plus Jakarta Sans for interface text; JetBrains Mono for requirement/acceptance identifiers only.
- Left-aligned heading/actions → existing requirement-to-result stage path → one white requirement sheet → traceable acceptance ledger → rules / constraints columns.
- Rejected a larger generic panel/card layout: it would dilute the actual QA evidence and duplicate the reference's content structure.

## Implementation

1. In `workspace.css`, place the run-control launcher in the workspace header flow rather than fixed over scrollable content, preserving its dialog and handlers.
2. Give the embedded requirement detail one continuous token-based paper surface; preserve existing IDs, rows, tabs, criteria editor, and lower evidence sections.
3. Ensure header actions wrap at constrained widths and sheet padding adapts on phones.

## Acceptance / Verification

- At 1488×880, the launcher does not overlap rules/constraints or other content and the requirement sheet reads as one work surface.
- At 768px and 390px, controls and criteria remain reachable with no horizontal page overflow.
- Opening/closing run controls remains functional without starting a run or AI action.
- Light/dark theme remain legible; no browser page errors.
- Run web lint, test suite, production build, `git diff --check`, and a structured code/UI review.
