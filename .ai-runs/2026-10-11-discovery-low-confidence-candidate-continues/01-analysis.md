# Analysis

## Evidence from the reported run

Read-only inspection of the matching local discovery record found:

- `require_jev=true` and `safe_mode=true`.
- Three Jev decisions passed confidence policy and three browser actions completed.
- The fourth provider response included an attempted candidate, but its confidence was `0.46`, below the configured `0.70` minimum. `DecisionService` converted it to a fallback with no executable `choice` and reason `below_minimum_confidence`.
- The service checks for a missing `choice` before checking `fallback_used`, so it reports “Jev 未返回可执行的候选动作” and terminates the entire run. The candidate was not executed.

## Root cause

A single low-confidence decision is treated as a fatal run-wide block even when Jev identified which candidate it could not confidently select. The run can safely skip that candidate and continue evaluating other already-vetted candidates without violating `require_jev`.

## Decision and constraints

- Keep the configured confidence threshold unchanged.
- Never execute the rejected/low-confidence attempted candidate.
- Mark only that candidate `SKIPPED` with a clear reason and continue the bounded exploration loop.
- If Jev has no valid attempted candidate or fails for another reason, preserve the existing required-Jev block behavior.
- Apply the same safe skip to missing-confidence responses with a valid attempted candidate; do not treat unknown confidence as permission to act.
