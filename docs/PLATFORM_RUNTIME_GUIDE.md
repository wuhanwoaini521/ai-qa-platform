# Platform Runtime & Execution Engine Guide

This document is the unified technical reference for the test execution runtime: from test run creation, subprocess execution, runner backends, and Server-Sent Events (SSE) streaming to Live Browser CDP screencasting, cancellation, debugpy debugging, run history, and failure flows.

---

## 1. Test Execution Lifecycle & Architecture

```text
+--------------------+      +--------------------+      +---------------------+
| User / Studio / CI | ---> | POST /api/runs     | ---> | TestRunService      |
+--------------------+      +--------------------+      +---------------------+
                                                                   |
                                                      (Async Background Task)
                                                                   v
                                                        +---------------------+
                                                        | RunnerBackend       |
                                                        | Local / Jenkins     |
                                                        +---------------------+
                                                                   |
                            +--------------------------------------+
                            | Line-by-Line stdout/stderr stream & telemetry
                            v
+------------------+  SSE   +--------------------+
| Frontend Web UI  | <===== | TestRunEventBus    |
| (Terminal View)  |        | GET /runs/{id}/evts|
+------------------+        +--------------------+
```

`TestRunService` creates and persists `run_id`, then dispatches to the selected `RunnerBackend`:
- Local runs execute via `LocalRunnerBackend` in a native subprocess inside the workspace.
- Remote runs dispatch via `JenkinsRunnerBackend` or distributed Worker nodes.

```text
TestRun (run_id)
  └─ TestCaseExecution (case_execution_id, nodeid)
       ├─ Worker (worker_id)
       ├─ BrowserSession (browser_session_id)
       ├─ Failure / logs / artifacts
       └─ DebugSession (debug_session_id, explicitly created from a case)
```

Pytest test results are parsed per node ID and written to `TestCaseExecution` (database ID `case_execution_id`). Parallel pytest-xdist workers are identified by `worker_id`. Live Browser telemetry correlates via `run_id + worker_id + nodeid` and links to `case_execution_id`. Browser sessions carry a unique `browser_session_id` and are never inferred purely from test titles.

---

## 2. Pluggable Runner Backends & Artifacts

The platform supports pluggable runner backends implementing `RunnerBackend`:

1. **`LocalRunnerBackend`** (`qa_core.execution.runner_backend`):
   - Executes pytest inside the local workspace subprocess.
   - Captures real-time stdout/stderr lines and streams them via SSE.
2. **`JenkinsRunnerBackend`** (`integrations.jenkins_runner`):
   - Dispatches remote Jenkins builds with parameters (`PROJECT_ID`, `WORKSPACE_ID`, `TARGET_NODEIDS`, `BROWSER`).
   - Polls build status and streams remote console logs via SSE.

### External Artifact References
When runs complete on CI or workers, external reports are tracked via `ExternalArtifactReferenceORM`:
- **`ALLURE`**: HTML Allure Report URL.
- **`HTML_REPORT`**: Pytest HTML test execution report.
- **`SCREENSHOT`** / **`TRACE`**: Playwright trace zip and screenshot artifacts.

---

## 3. Core Execution Engine (`PytestRunner`) & Deterministic Verdicts

- **Subprocess Safety**: Launched using `asyncio.create_subprocess_exec("pytest", "-v", "--capture=no", ...)`. No shell interpolation (`shell=False`).
- **Line Parsing**: Captures structured pytest status lines matching:
  ```python
  r"^(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR)"
  ```
- **Execution States**:
  - `QUEUED`: Stored in DB, awaiting execution.
  - `RUNNING`: Subprocess active, streaming logs in real time.
  - `PASSED`: Subprocess exited with code 0 and all tests passed.
  - `FAILED`: Subprocess exited with non-zero exit code; failure records created automatically.
  - `CANCELLED`: Process gracefully terminated via `SIGTERM` / `SIGKILL`.
- **Deterministic Verdict Guarantee**: Pytest exit codes and assertion outcomes are the single source of truth. AI never modifies or overrides execution verdicts.

---

## 4. Real-Time SSE Protocol

Clients subscribe to `GET /api/runs/{run_id}/events` (or `/api/tasks/{task_id}/events`) and receive structured SSE event streams:

```json
event: message
data: {"type": "status", "run_id": "uuid", "status": "RUNNING"}

event: message
data: {"type": "log_chunk", "run_id": "uuid", "chunk": "tests/test_cart.py::test_coupon PASSED\n"}

event: message
data: {"type": "execution_update", "run_id": "uuid", "execution": {"id": "uuid", "nodeid": "tests/test_cart.py::test_coupon", "status": "PASSED", "duration_ms": 1420}}

event: message
data: {"type": "complete", "run_id": "uuid", "status": "PASSED"}
```

---

## 5. Live Browser Telemetry Architecture

Local runner writes a telemetry plugin into the run's artifacts directory. The plugin hooks into the Playwright page driven by the test fixture and reads real frames via Chromium CDP screencast; it never spawns a dummy browser. Frames are streamed ephemerally over SSE; session metadata, worker ID, node ID, URL, and status are stored as metadata. Frames are not persisted.

`LiveBrowserPlugin` writes event files per xdist worker, and the API tails these files for SSE streaming. Events include session start, navigation, frame, and finish. UI presents a primary worker tab with compact secondary indicators. When SSE disconnects, the browser client requests a fresh short-lived ticket and reconnects.

CDP screencasting applies to Chromium. Other browser engines without CDP report session and navigation metadata without synthesized frames.

---

## 6. Run History & Stable Test Identity

Tests are tracked across runs to compute stability analytics, regression detection, and duration trends:

- **Stable Test Identity**: Tests are uniquely identified by `(nodeid, project_id)`.
- **Data Models**:
  - `TestRunORM`: Batch execution run root record.
  - `TestExecutionORM`: Individual test node outcome within a run.
  - `RunHistoryRepository`: Queries last $N$ executions of a `nodeid`, pass/fail/skip rates, P95 duration trends, and failure signature recurrence.

---

## 7. Cancellation, Cleanup & Stale Recovery

- **Atomic Transitions**: Run states only transition from `QUEUED` / `RUNNING` to terminal states. Repeated cancellation calls are idempotent; late runner logs or worker updates cannot overwrite `CANCELLED`.
- **Subprocess Tree Teardown**: Runners terminate child subprocess trees gracefully (`SIGTERM` followed by `SIGKILL` on timeout). Distributed workers poll job status and abort active pytest tasks upon cancellation.
- **Stale Recovery**: Startup recovery handles local stale `LOCAL` runs. Each submitted case result shares a database row lock with the Run; if cancellation commits first, late results do not append new executions.

---

## 8. Stream Credentials & URL Redaction

- **Stream Tickets**: Run/task SSE streams require a 5-minute server-signed stream ticket sent via the `Authorization` header. Recorder and debugger WebSockets send the ticket in their first frame. Tickets grant read access only to their specific stream and cannot be used as general API tokens.
- **URL Redaction**: URLs entering BrowserSession, SSE, locator decisions, AI traces, logs, and evidence have userinfo, query params, and fragments removed. Non-HTTP URLs (`data:`, `blob:`, `file:`) retain only the scheme. Test execution navigation continues using raw URLs to preserve test inputs.

---

## 9. Debug Runtime

- Studio's top-level "Debug" runs all tests in the current file using active breakpoints. All modified files are auto-saved before debugger startup.
- Debugger executes via `DebugSessionService` which launches a real `debugpy` DAP (Debug Adapter Protocol) adapter. It reuses the project workspace and pytest node ID, without recreating or interfering with the test run's browser.
- Session lifecycle is tracked under `debug_session_id`. Breakpoints are synchronized as complete sets to `debugpy`. If a session crashes, its state remains at the last saved status without faking a running state.

---

## 10. AI → Jev Flow and Failure Intelligence

- Regular AI providers handle QA assistance, requirement analysis, case generation, and failure diagnosis.
- Jev handles structured decision selection (e.g. locator candidates). Configurations, credentials, and health states are strictly separated.
- Locator candidates must pass Playwright verification before application. AI output or Jev choices never equate to a verified locator; human approval is always required before code patching.
- Failure analysis stream (`POST /api/failures/{id}/analyze/stream`) executes step-by-step inspection (UI, API, Python evidence) with persisted history. Verification runs must pass the exact failed test node ID to confirm resolution.
