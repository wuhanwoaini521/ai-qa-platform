# Jenkins CI Integration & Mock Server

## 1. Overview
The Jenkins integration allows executing test suites across distributed Jenkins workers while preserving live console logs and test outcomes in the AI QA Platform.

---

## 2. Parameter Mapping
When triggering a Jenkins build, the platform passes parameterized arguments:
- `PROJECT_ID`: The project UUID.
- `WORKSPACE_ID`: Workspace UUID.
- `TARGET_NODEIDS`: Comma-separated list of pytest node IDs (or empty for full regression).
- `BROWSER`: `chromium`, `firefox`, or `webkit`.

---

## 3. Mock Jenkins Transport (`FakeJenkinsServer`)
For CI/CD and offline development without a live Jenkins instance, `FakeJenkinsServer` provides an in-memory transport implementing the Jenkins REST API:
- `GET /api/json`: Instance and job health check.
- `POST /job/{name}/buildWithParameters`: Returns queue item URL (HTTP 201).
- `GET /queue/item/{id}/api/json`: Emulates queue transitions to build numbers.
- `GET /job/{name}/{number}/api/json`: Returns build status and artifacts.
- `GET /job/{name}/{number}/logText/progressiveText`: Emulates progressive console log streaming.
