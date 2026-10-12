# Implementation — Per-Case Run Results Visibility

- Added `apps/web/src/features/runs/testExecutionResultsModel.ts` to map executions to cases only by exact, unique `binding.nodeid`; unmatched/ambiguous cases retain their pytest nodeid rather than receiving a guessed title. Failure records match both `test_run_id` and `execution_id`.
- Added shared `TestExecutionResults.tsx` / `testExecutionResults.css`, used by `WorkspaceRunResult.tsx` and the previously disconnected `RuntimeRunResults.tsx`. Each row shows case ID/title when safely mapped, full nodeid, duration, status, error, progressive full evidence and its own Failure action.
- Added a Runtime Results tab to `RuntimeDetail.tsx`, with task tabs preserved and Results available for Runs / tasks with child Runs. Opening runtime from a Workspace result selects Results; opening a linked step continues to select Flow. The Runs page opens directly on Results.
- Annotated the existing single-failure diagnosis with the exact case/nodeid it summarizes and restricted expected-result comparison to a uniquely matched case.
- Added English and Simplified Chinese labels. No API, backend, model, or persisted data changes.
