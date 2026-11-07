# AI 探索与回归修复改进

- run-date: 2026-11-06
- task-type: new-feature
- scale: standard

## Implemented

- Moved deterministic live-page evidence extraction before the blocked-task branch and attached a redacted exploration summary to the existing bounded browser-history artifact.
- Added a backend eligibility flag for a narrow whitelist of non-safety stop reasons, requiring at least one successful replayable action with verified locators where needed.
- Added an explicit “incomplete draft” path in RecorderPage that downloads the existing artifact only after the user clicks; the current converter continues to reject unverified locators and partial-draft mode accepts successful actions only.
- Partial drafts do not claim goal completion or synthesize a page-title assertion. The UI warns that the goal is incomplete and calls for a business-outcome assertion when none was observed.
- Clarified that the actual regression verification scope is shown in the created Run.

## Constraints preserved

- No additional provider, runtime, agent, persistence table, or automatic source write.
- AI suggestions remain proposals; repair apply remains human-approved and execution outcome remains deterministic.
