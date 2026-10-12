# Analysis — Per-Case Run Results Visibility

## Evidence and Root Cause
- Reproduced the supplied Workspace result route using the real Golden Demo run `run_1a8bf6d5a021`: 8 planned/saved executions, 7 passed and 1 failed. The result page showed only `run.nodeids[0]` (the test file) and a single failure summary; no per-execution list was rendered.
- Opened “运行详情”: `RuntimeDetail` exposed Overview/Flow/Timeline/Trace/Browser/Artifacts but no test-result view. `RuntimeRunResults.tsx` already contains a Run-results table, but it is not imported by any Runtime detail route and currently identifies tests only by nodeid.
- Read-only API evidence: `TestRun.executions` carries each execution's nodeid/status/error/stack; runtime failures carry `execution_id`; project TestCases include exact automation bindings. Seven of the eight fixture nodeids matched one unique case binding; one historical binding differs, so that row must fall back to its nodeid rather than be guessed as another case.
- Root cause is presentation/integration: per-test execution data exists, but the Workspace result view aggregates it and the existing runtime result component is disconnected from the runtime tabs.

## Architecture / Impact
- `WorkspaceRunResult` already receives `run`, project `testCases`, and the run Runtime snapshot. It can display all executions and associate each runtime Failure by execution ID.
- `RuntimeRunResults` already loads the selected `TestRun` through the shared `useRunStore`; it can load project cases from the run's `project_id` and reuse the same result-list presentation.
- `RuntimeDetail` is the shared run/task detail surface. Add a Results tab for Run snapshots (and task snapshots containing child runs) without removing existing tabs; select it by default when opening run details from the Workspace result.
- Resolve a TestCase only by exact `binding.nodeid`. When no unique match exists, preserve the full pytest nodeid and report ambiguity rather than infer identity from similar test names.

## Constraints / Risks
- Frontend-only change; no API/model/persistent data changes and no live Run execution or Failure creation.
- MEDIUM risk: shared Runtime detail surface and multiple result consumers. Preserve task Flow, Overview and existing run-event behavior; test all current consumers and responsive views.
- Existing user changes are unrelated and remain uncommitted. `.gitignore` does not mention `.ai-runs/`; retain the task log locally and leave version-control policy to the repository/user.
