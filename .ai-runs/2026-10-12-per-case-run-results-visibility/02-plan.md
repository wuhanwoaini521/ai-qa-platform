# Plan — Per-Case Run Results Visibility

## UX Direction
Use an execution-ordered, compact list as the shared source of truth for both result surfaces. Each row shows status, exact case ID/title when uniquely bound, full nodeid as a technical identifier, duration, and its own error/failure action. Keep successes visible so the complete run can be distinguished; keep long stack traces progressive-disclosed. Reuse the existing Runtime tab/navigation and theme tokens rather than creating another page or replacing the failure workflow.

## Implementation
1. Add and test a pure execution identity model: exact `TestCase.binding.nodeid` match; unmatched rows use the test nodeid; ambiguous mappings never choose arbitrarily; failures pair by run/execution ID.
2. Add one shared per-execution results list for the Workspace result surface and the existing `RuntimeRunResults` component. Show each error independently and preserve a per-failure link.
3. Wire `RuntimeRunResults` into a discoverable Runtime Results tab. Open that tab from the Workspace Run-results action; leave Flow as the default for task workflows.
4. Identify the specific case represented by the existing single-failure diagnosis summary so it cannot be mistaken for an aggregate of all failures.
5. Add English/Chinese strings and responsive styles using current tokens.

## Expected Files
- `apps/web/src/features/runs/testExecutionResultsModel.ts` and `apps/web/tests/test-execution-results-model.test.mjs` (new)
- `apps/web/src/features/runs/TestExecutionResults.tsx` and its stylesheet (new shared presentation)
- `apps/web/src/features/workspace/WorkspaceRunResult.tsx`, `WorkspacePage.tsx`, `workspace.css`
- `apps/web/src/features/runtime/RuntimeDetail.tsx`, `RuntimeRunResults.tsx`, `runtime.css`
- English and Simplified Chinese `workspace.json` / `runtime.json`

## Verification and Review
- Targeted model tests for unique match, unmatched nodeid, ambiguous mapping, multiple failures, and empty executions.
- Web test suite, lint, typecheck, build, and `git diff --check`.
- Real browser: reproduce the supplied 8-case run; verify eight individually labeled results, failed case and message, then open Runtime Results and verify same identities. Use read-only browser state/mock data only if needed to exercise multiple simultaneous failures; no backend records will be created or mutated.
- Inspect 1524px desktop, 768px tablet, and 360/390px phone, light/dark as practical; verify the detail tab and individual failure links.
- Independent second-pass code review, UI review, and regression of task Runtime Flow, Workspace event stream and existing Run summary.
