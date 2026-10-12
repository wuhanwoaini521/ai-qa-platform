# Plan

1. In the existing discovery decision loop, detect a Jev fallback caused by low/missing confidence when `attempted_choice` maps to a current safe option.
2. Mark only that option `SKIPPED`, emit an explanatory event/frontier reason, and continue the loop. Keep all other fallback/provider-error blocks intact.
3. Add a deterministic API-level regression test: low-confidence candidate is not executed, the run continues, and a later valid Jev decision can proceed.
4. Run the discovery tests and the related browser-runtime/decision regressions, review the full diff, and preserve all unrelated user changes.

## Acceptance

- Rejected actions remain unexecuted and confidence policy is unchanged.
- A valid candidate can still be explored after one low-confidence candidate is skipped.
- Provider-unavailable/no-attempted-choice behavior remains blocked.
