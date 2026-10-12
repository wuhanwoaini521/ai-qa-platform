# Fixes

## Product finding

- **Finding:** at 390×844, mobile navigation labels were 8px in 42px items; the Dashboard/Workspace labels were difficult to read.
- **Initial attempt:** 9px labels and 50px items improved the Chinese screenshot, but real English browser metrics showed `Dashboard` and `QA Workspace` still clipped. This was a product observation, not a test failure.
- **Final fix:** use 52px primary items and 9px concise localized mobile labels (`Home`, `Workspace`, `Projects`, `Runs`, `Insights`; compact Chinese equivalents). Keep full translated aria-labels unchanged. Desktop/tablet layout remains unchanged.
- **Retest:** both languages unclipped in Chrome; all five primary routes opened at mobile width; no overflow. Full regression passed after the final changes.

## Verification harness corrections

- A helper initially attempted to scroll to platform links hidden by existing mobile CSS; narrowed the assertion to the five primary links in scope.
- A Playwright `wait_for_function` helper initially passed `arg` positionally; corrected to the supported keyword argument.
- These were harness issues, not product defects.

## Runtime preservation event

API startup's stale-run recovery automatically transitioned `run_51c9455dff71` from RUNNING to CANCELLED after its 7,200-second threshold. The startup log confirmed the recovery. This event was not manually triggered or reversed; its persisted history and final state are reported transparently.
