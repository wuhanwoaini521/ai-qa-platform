# Code Review

Second-pass review of the discovery decision loop, frontier persistence, and regression tests:

- The configured confidence threshold is unchanged.
- Only a valid attempted candidate rejected for missing/low confidence is skipped; it is never marked selected or executed.
- `skipped_candidate_ids` prevents a retry loop; the next iteration reloads persisted state and evaluates remaining candidates under existing domain, action-safety, and Jev gates.
- Other Jev/provider fallback cases preserve required-Jev blocking. Test asserts a fallback with no attempted choice remains blocked.
- The new event reports candidate ID and confidence metadata without exposing page content or credentials.
- No persistence schema/API contract changes or unrelated cleanup.

Findings: no P0/P1 blockers. No required follow-up fixes.
