# Findings

## ISSUE-001 — Proposal “Ignore” is not a persisted human rejection

- Evidence: `.ai-runs/refactor-audit/feature-validation.md` and `reports/nightly/HANDOFF.md` identify human-rejection acceptance as incomplete. Current browser/API call path uses `setRepairProposal(null)` only, while `get_repair_workflow` continues to allow `APPLY` from the stored `PATCH_READY` state.
- Impact: a user cannot record a durable rejection; a reload restores the candidate and the backend still accepts Apply. This leaves the review lifecycle incomplete and risks confusing user intent.
- Root cause: there is no persisted reject command/event; the Ignore button is local presentation state.
- Plan: persist rejection as the existing `BLOCKED` state with `block_reason=HUMAN_REJECTED`, expose a `REJECT` action only while `PATCH_READY`, display the decision, and deny Apply after rejection.
