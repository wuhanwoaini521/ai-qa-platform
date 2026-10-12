# Implementation

## Scope delivered

- Extended the existing `TaskBrowserExecutor` and injected `BrowserRuntime`; no parallel browser runtime, provider path, or MCP server was added.
- Correlated each browser decision/action with one ID across AI planner invocation `run_id`, Jev decision `run_id`, persisted decision/action events, selected candidate, action result, and verification trace.
- Added dispatch-boundary re-observation after decision/event persistence. The executor compares URL and page fingerprint, checks the exact observed target identity/visibility/enabled state, and re-verifies the locator before executing. Stale actions are blocked, evidenced, and replanned without consuming the browser action budget.
- Added `ExecutionIncident` records with failure category, bounded recovery attempt, evidence reference, and recovering/recovered/unresolved events. Public event metadata remains allowlisted.
- Added bounded action-history compaction (20-action live window; 10-action archive chunks; maximum 50 chunks), relevant history retrieval for planning, an action-history artifact, and Recorder script replay across archived and recent actions. Archived records are passed through `SensitiveRedactor` before retaining them.
- Added `agent` and `fast` browser strategies. Agent requires Jev from the Recorder UI and uses it for ambiguity; Fast favors AI candidate ranking and skips optional Jev unless effective platform policy requires it. Strategy and policy are also enforced at the backend boundary.
- Added a Recorder strategy selector and copy explaining the different policies. The selector is disabled while a task is pending/running.
- Added deterministic regression coverage and an opt-in live-provider acceptance test. The test saves a sanitized JSON receipt and browser screenshots when `AI_QA_LIVE_EVIDENCE_DIR` is set.

## Implementation files

- `apps/api/app/services/task_browser_executor.py`
- `apps/api/app/services/task_ai_service.py`
- `apps/api/app/services/event_normalizer.py`
- `packages/qa-core/qa_core/failure/models.py`
- `packages/qa-core/qa_core/failure/__init__.py`
- `apps/api/tests/test_browser_agent.py`
- `apps/api/tests/test_browser_agent_e2e.py`
- `apps/api/tests/test_browser_agent_live_e2e.py`
- `apps/api/tests/test_runtime_events.py`
- `apps/web/src/pages/RecorderPage.tsx`
- `apps/web/src/pages/recorderAgentModel.ts`
- `apps/web/src/index.css`
- `apps/web/tests/recorder-agent-model.test.mjs`

Some Web files were already dirty before this task. The changes above are incremental task hunks; pre-existing work was preserved and not staged.

## Delivery state

The 13 task-owned source/test files were committed on `main` and pushed to `origin/main` as `728e94a` (`feat: harden browser agent execution kernel`). Run artifacts and evidence remain in this `.ai-runs/2026-10-12-artemis-browser-kernel/` directory and were not included in the commit.
