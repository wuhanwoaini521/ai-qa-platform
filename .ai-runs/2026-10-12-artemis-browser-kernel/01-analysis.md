# Architecture Audit

## Current boundaries
- `apps/api/app/ports/browser_runtime.py` defines the BrowserRuntime contract; `adapters/playwright/browser_runtime.py` owns the API-process Playwright sessions. Recorder, task browser agent, quality discovery, platform health, and locator verification inject the same singleton from `app.container`.
- Browser agent accesses `BrowserPage` for observation but sends browser actions through BrowserRuntime. Recorder uses the runtime for its session but still performs human mouse/keyboard interactions on the returned page.
- Standard pytest runs use `qa_core.execution.PytestRunner` in isolated runner processes; live browser telemetry records worker-owned Playwright sessions. Debugger starts a separate debugpy/pytest process. They do not share the API-process BrowserRuntime Page/context.
- `TaskRuntimeService` is a composition root for `TaskCommandService`, `TaskSchedulerService`, and `TaskExecutionOrchestrator`. Capability ownership is delegated to task services/ports. TestRun execution has a separate scheduler/service appropriate to pytest runs.
- `FailureRepairWorkflow` is a Pydantic response model. Run failure repair is implemented by `FailureWorkflowService` + `FailureService`; task repair is implemented by `TaskFailureRepairService`. Run repair has candidate selection, Playwright verification, diff/proposal, apply, exact-case rerun, status reconciliation and rollback. Task repair checks that AST assertions are unchanged and gates writeback on approval, then validates the workspace and follows its task DAG.

## Provider and execution evidence
- App lifespan activates `AIProviderRegistry` and `AIExecutionService`; browser planning uses `TaskAIService.complete_browser_action_candidates`. The provider middleware persists AI invocation IDs, provider/model, request/task/run IDs, status and usage.
- Jev is called by `TaskDecisionService`/`DecisionService` through `JevDecisionProvider` (configured `/v1/systemone` endpoint). Confidence policy and fallback are applied by `DecisionService`.
- Current browser Agent calls Jev only for multiple candidates or explicit/configured requirement. AI, Jev, decision, and action events are individually recorded, but their IDs are not tied together per observe/decide/act cycle.
- Existing `test_browser_agent_e2e.py` E2E tests use fixture planner and patched Jev; they run real local Playwright but are not real-model acceptance evidence.

## Workspace and contracts
- Recorder sessions can be attached explicitly by `recorder_session_id`; session restoration is persisted by the Recorder UI. Studio run drawer and Runtime use task/run events and telemetry; Debugger and pytest launch their own process/session. Therefore cross-panel continuity exists in portions, not as one universal shared browser session.
- API contracts are FastAPI/Pydantic with hand-maintained web TypeScript types. `test_architecture_boundaries.py` checks the failure workflow DTO parity, but not every contract is generated from OpenAPI.
- Task/browser state and event history are persisted and resumable; browser Agent keeps only the most recent 20 raw action records. There is no compressed/searchable archive of evicted action history.
- Browser actions have an initial target verification before Jev, then persistence/decision latency, then a URL-only dispatch check. The target is not revalidated at the final dispatch boundary; stale same-URL DOM targets can be acted on.

## ARTEMIS concepts adapted
- Adopt observe/act/verify loop, semantic + multimodal evidence (existing accessibility tree, visible text, screenshot), fast deterministic pytest vs agent exploration, pre-dispatch Safety Net, independent post-action observation, incident recovery, compact searchable action history, and shared execution/evidence correlation.
- Do not copy Android/ADB/mobile-specific device implementation. No parallel browser runtime or artificial success provider.

## Scope/constraints
- Keep current user Web changes, existing runtime artifacts, and prior audit documents untouched; selectively stage/commit only files owned by this run.
- No MCP or SDK entry point currently exists. This run prioritizes strengthening the existing API/task execution kernel and documenting other missing entry points rather than adding an ungrounded second server.
- UI is not being redesigned in this run; verify the existing workspace/run interface in a real browser and preserve current dirty UI work.
