# Implementation

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

## Frontend A (backend unchanged)
- `apps/web/src/features/runtime/RuntimeDetail.tsx`: replaced hand-written initial loading/error markup with shared `LoadingState` / `ErrorState`, retaining Runtime shell layout and retry action. In-snapshot stream errors remain non-blocking reconnect notices.
- `apps/web/src/api/client.ts`: `downloadArtifact` now uses the existing authenticated `requestBlob` transport, consistent `APIError` handling/401 behavior, and encoded artifact IDs. The existing `getArtifactBlob` method and public client methods remain intact.
- No frontend requests were moved outside the API client. WebSocket payload protocols remain owned by Recorder/Debugger/LSP feature clients; HTTP/SSE endpoints remain public API contracts.

## Backend B (API contract unchanged; frontend unchanged)
- `apps/api/app/api/quality_discovery.py`: removed the cross-Router import/injection of `get_task_command_service`; the route now calls a complete service use case and retains permissions, HTTP response model and error translation.
- `apps/api/app/container.py` + `apps/api/app/services/quality_discovery_service.py`: inject the shared `TaskCommandService` from the container's singleton `TaskRuntimeService` into Quality Discovery.
- `apps/api/app/services/quality_discovery_draft.py`: draft creation uses the injected command service; all existing evidence, URL, locator, redaction, and human-approval checks remain unchanged.
- `apps/api/app/api/tasks.py` no longer owns module-level aliases to TaskRuntime/Execution/Scheduler; request command resolution uses app lifespan state or the container singleton.
- `apps/api/app/main.py` now gets the same runtime from the composition root and remains the sole production start/stop owner.
- Tests that previously imported runtime objects from a Router now resolve the container service. The task SSE test now checks `Last-Event-ID` replay and rejects a malformed cursor.

## Compatibility / Safety
- Backend OpenAPI before/after canonical JSON comparison was byte-identical. No route, status, response or authorization contract was changed.
- The Discovery proposal remains pending human approval; the integration test verifies the workspace file is absent before approval and after rejection, and appears only after explicit approval.
- No Repository implementation was changed; repository responsibilities remain persistence/data access.
