# Architecture Boundaries / Dependencies

- run-date: 2026-10-14
- scope: validated working-tree structure for this refactor

## Dependency Direction

```text
apps/web ── REST / authenticated SSE / API-issued WebSocket URLs ──> apps/api
apps/worker ── authenticated HTTP job/heartbeat/result protocol ──> apps/api
apps/api ──> packages/project-model
         ├──> packages/qa-core ──> packages/project-model
         ├──> packages/integrations
         └──> packages/platform-config
packages/integrations ──> packages/qa-core + packages/project-model
```

- `apps/web` does not import API services, repositories, or persistence models. REST calls go through `src/api/client.ts`; request failures share `APIError` parsing; SSE uses stream tickets and event cursors. Recorder, Debugger, and LSP use WebSocket data protocols, with URL construction in the client and protocol handling in their feature clients; these are not alternate REST clients.
- OpenAPI JSON and `openapi-typescript` output are the public contract artifacts. Existing general DTOs use generated schema types; `src/types/runtime.ts` is still a handwritten Runtime projection DTO. Its property set was checked against generated `RuntimeSnapshot` schemas; OpenAPI marks some defaulted Pydantic fields optional while the server serializes those defaults. This remaining handwritten type should be migrated separately with a small contract-safe change.
- Worker is not an API module and imports no `app.api` code. `WorkerDaemon` owns registration, heartbeat, bounded job claiming, cancellation, and local `PytestRunner` execution; it calls the API over HTTP. `qa-core` supplies its execution and failure-snapshot contracts.

## Runtime / Lifecycle Ownership

| Concern | Owner | Boundary |
|---|---|---|
| Browser sessions and low-level navigation | `BrowserRuntime` port + Playwright adapter | Injectable browser capability; no API routing, task queue, or task state machine |
| AI Task state and commands | `TaskCommandService` | Creates tasks and owns task-level pause/resume/cancel/approval/replan commands over task repositories |
| Task execution | `TaskExecutionOrchestrator` | Executes task steps/tools and receives `BrowserRuntime` as a port |
| Task scheduling and recovery | `TaskSchedulerService` inside `TaskRuntimeService` | Owns bounded scheduling and process lifecycle; `main.lifespan` starts/stops the one container instance |
| Test-run lifecycle/results | `TestRunService` / Worker job execution | Separate test run, test result, and worker job states; not a second AI Task Runtime |
| Discovery lifecycle/evidence | `QualityDiscoveryService` | Owns discovery transitions and safe, evidence-backed pytest draft preparation |
| Debug sessions | `DebugSessionService` | Owns debugpy process/session and DAP forwarding lifecycle; its WebSocket is not Task Runtime control |
| Generic language-model calls | `AIProviderRegistry` and AI execution services | Provider selection, bounded calls, trace and fallback metadata |
| Candidate decisions | `DecisionService` with Jev provider | Evidence-grounded decision selection; Jev is not a general task scheduler or LLM execution runtime |

Task, TestRun, Discovery, WorkerJob, and DebugSession statuses remain separate because each describes a different persisted aggregate and lifecycle. They must not be collapsed into a shared enum or allowed to overwrite one another.

## Changes in This Round

Before: `main.py` reached into `app.api.tasks` for the task runtime; the task Router held module-level aliases for the same container singleton; the Discovery Router imported `get_task_command_service` from the task Router and passed it into a service method.

After: `main.py` and both API services resolve the single `TaskRuntimeService` from `app.container`. The Discovery factory injects its task-command collaborator into `QualityDiscoveryService`; the Discovery Router now handles HTTP permissions/status translation and calls the service use case without composing another Router's dependency. The Repository layer and public endpoint/response schema are unchanged.

## Approval / Safety Boundaries

The pytest draft remains a `CREATE_TEST` Task proposal. It is not a source write: the integration test confirms the workspace file is absent before human approval and after rejection, and created only after approval. The refactor adds no bypass or automated approval path.
