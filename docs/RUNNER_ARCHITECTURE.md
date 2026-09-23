# Multi-Runner Platform Architecture

## 1. Overview
The platform supports pluggable runner backends via the `RunnerBackend` interface:

```text
               ┌───────────────────────┐
               │     RunnerBackend     │
               └───────────┬───────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
   ┌───────────────────┐       ┌───────────────────┐
   │ LocalRunnerBackend│       │JenkinsRunnerBackend│
   └───────────────────┘       └───────────────────┘
```

---

## 2. Runner Backends
1. **`LocalRunnerBackend`**: Executes pytest in subprocess inside the local workspace container, capturing real-time stdout/stderr lines and JSON reports.
2. **`JenkinsRunnerBackend`**: Triggers remote Jenkins job builds with parameter mappings (`WORKSPACE_ID`, `NODEIDS`, `BROWSER`), polls queue duration, and streams console logs to SSE.

---

## 3. External Artifact References
When runs complete on CI (e.g. Jenkins or Docker), external reports are linked via `ExternalArtifactReferenceORM`:
- **`ALLURE`**: HTML Allure Report URL.
- **`HTML_REPORT`**: Pytest HTML test execution report.
- **`SCREENSHOT`** / **`TRACE`**: Playwright trace zip and screenshot artifacts.
