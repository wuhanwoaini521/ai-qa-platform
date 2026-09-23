# Worker Node Architecture

## 1. Worker Lifecycle

1. **Bootstrap & Registration**:
   - On startup, workers report hostname, IP, supported browser engines, and concurrency limits to `/api/workers`.
2. **Heartbeat Loop**:
   - Every 15 seconds, worker sends load telemetry to `/api/workers/{id}/heartbeat`.
3. **Task Polling & Claiming**:
   - Worker polls `/api/jobs/claim` when `current_load < max_concurrency`.
4. **Execution & Artifact Shipping**:
   - Runs test execution subprocess, captures traces/snapshots, streams live stdout/stderr events, uploads test artifacts, and reports completion to `/api/jobs/{id}/complete`.
