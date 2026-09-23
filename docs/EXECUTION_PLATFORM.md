# Test Execution Platform Architecture

The Test Execution Platform delivers real-time, deterministic pytest execution with asynchronous subprocess control and live Server-Sent Events (SSE) streaming.

---

## 1. Execution Lifecycle

```text
+--------------------+      +--------------------+      +---------------------+
| User / Studio / CI | ---> | POST /api/runs     | ---> | TestRunService      |
+--------------------+      +--------------------+      +---------------------+
                                                                   |
                                                      (Async Background Task)
                                                                   v
                                                        +---------------------+
                                                        | PytestRunner        |
                                                        | (Safe Subprocess)   |
                                                        +---------------------+
                                                                   |
                            +--------------------------------------+
                            | Line-by-Line stdout/stderr stream
                            v
+------------------+  SSE   +--------------------+
| Frontend Web UI  | <===== | TestRunEventBus    |
| (Terminal View)  |        | GET /runs/{id}/evts|
+------------------+        +--------------------+
```

---

## 2. Core Execution Engine (`PytestRunner`)

- **Subprocess Safety**: Launched using `asyncio.create_subprocess_exec("pytest", "-v", "--capture=no", ...)`. No shell interpolation.
- **Line Parsing**: Captures structured pytest status lines matching `r"^(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR)"` without requiring brittle custom plugins.
- **Execution States**:
  - `QUEUED`: Stored in DB, queued for runner execution.
  - `RUNNING`: Subprocess active, streaming stdout/stderr in real time.
  - `PASSED`: Subprocess completed with exit code 0 and all tests passed.
  - `FAILED`: Subprocess exited with failure code; failure records created automatically.
  - `CANCELLED`: Process gracefully terminated via `SIGTERM` / `SIGKILL`.

---

## 3. Real-Time SSE Protocol

Clients subscribe to `GET /api/runs/{run_id}/events` and receive structured event streams:

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

## 4. Deterministic Verdict Guarantee

The platform strictly respects pytest exit codes and assertion outcomes:
- **Pytest is the Single Source of Truth**: AI never modifies or overrides execution verdicts.
- **Execution Tracing**: Detailed execution duration, error messages, and stack traces are captured per test node.
