# Analysis

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

## Current Boundaries
- Web business code already centralizes REST through `apps/web/src/api/client.ts`; HTTP errors flow through `api/errors.ts`. SSE ticket/reconnect parsing is owned by the same client plus `eventStream.ts`. WebSocket data protocols (Recorder, Debugger, LSP) are intentionally different transports, not duplicate REST clients.
- Runtime API models already appear in generated OpenAPI, but `apps/web/src/types/runtime.ts` duplicates their fields. `RuntimeDetail` also hand-renders initial loading/error state instead of using the existing shared `AsyncState` components.
- `downloadArtifact` bypasses `requestBlob`, duplicating an artifact endpoint and returning a different error shape; `getArtifactBlob` already uses the shared API transport.
- API task runtime is already composed in `container.py`, but `api/tasks.py` creates router-module aliases and `main.py` imports runtime lifecycle from that Router. Quality Discovery's Router also imports `get_task_command_service` from the task Router and passes this service collaborator into a business method.
- `QualityDiscoveryService` already owns the draft-validation and construction behavior; its task-command collaborator belongs in service composition, not Router orchestration.
- BrowserRuntime is a low-level browser session port/adapter; TaskRuntime owns AI task command/execution/scheduling lifecycle; TestRunService owns test execution run lifecycle/results; DebugSessionService owns DAP process/session lifecycle; generic AI providers are called via the AI registry/orchestrator; DecisionService selects evidence-grounded decisions and Jev is its configured provider. These are distinct responsibilities, not candidates for a blanket shared runtime/status enum.
- Repository dependencies: API consumes `project-model`, `qa-core`, `integrations`, `platform-config`; Worker consumes `qa-core` and `platform-config` and talks to API over HTTP; `qa-core` consumes `project-model`; Web talks to API via public HTTP/SSE/WebSocket contracts and does not import API internals.

## Risks / Invariants
- Keep HTTP path/status/response schemas byte-for-byte equivalent at OpenAPI level for the backend-only change.
- Keep task scheduler start/stop single-owned by FastAPI lifespan; keep tests using the same container singleton.
- Preserve discovery draft validation and `TaskCommandService.create` semantics; no direct workspace/source writes are introduced.
- Preserve stream-ticket authorization, SSE cursor replay, task state storage and API error normalization.
