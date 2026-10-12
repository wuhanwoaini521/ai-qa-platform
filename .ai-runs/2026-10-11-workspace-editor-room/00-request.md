# Request

The workspace editor area is too narrow while the context column uses space without useful content. The supplied screenshot shows this on the automation/code stage (viewport approximately 1524×906). Follow-up screenshots also show a run failure mislabeled as provider unavailability despite a successful provider health check, plus a missing Python language server.

- Task type: ui-feature (scoped workspace layout and AI trace status behavior)
- Scale: small
- Risk: MEDIUM (stage-specific layout state; workspace navigation remains available through the existing toggle)
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Initial status: many pre-existing modified and untracked files, including `WorkspacePage.tsx`, `workspace.css`, and `.ai-runs/`; preserve all existing changes.
