# Distributed Execution Platform & Worker Architecture

This document describes the distributed execution cluster architecture, worker node lifecycle, heartbeat protocol, capability matching, and job queue scheduling.

---

## Overview

The **Distributed Execution Platform** decouples test suite triggers from local compute resources, dispatching test suites across worker nodes, containerized Docker runners, and ephemeral sandboxes.

```text
      Test Run Trigger (API / Web / CI)
                      ↓
           Distributed Job Queue
           (Priority / Tag Matching)
                      ↓
      ┌───────────────┼───────────────┐
      ↓               ↓               ↓
Worker Node 1   Worker Node 2   Docker Container
  (Chromium)      (Firefox)       (Ephemeral)
      ↓               ↓               ↓
      └───────────────┬───────────────┘
                      ↓
           Object & Artifact Store
         (Traces, Allure, Screenshots)
```

---

## 1. Worker Node Lifecycle & Daemon Protocol

Distributed workers run the daemon process (`apps/worker/worker/daemon.py`) and follow a 4-stage lifecycle:

1. **Bootstrap & Registration**:
   - On startup, the worker reports hostname, IP, supported browser engines, OS, and concurrency limits to `POST /api/workers`.
2. **Heartbeat Loop**:
   - Every 15 seconds, the worker sends load telemetry to `POST /api/workers/{id}/heartbeat`.
   - **Status lifecycle**: `ONLINE` $\to$ `BUSY` (when processing jobs) $\to$ `ONLINE` $\to$ `LOST` (if heartbeat missed for $>60\text{s}$) $\to$ `OFFLINE`.
   - **Capability tags**: `browsers: ["chromium", "firefox", "webkit"]`, `os: "linux"`, `max_concurrency: 8`, `current_load: 2`.
3. **Task Polling & Claiming**:
   - When `current_load < max_concurrency`, the worker polls `POST /api/jobs/claim`.
   - An isolated worker can set `WORKER_PROJECT_IDS` to a comma-separated project allowlist. The daemon sends that scope with each claim, and the API filters before selecting/locking a job. Unset preserves global claiming.
4. **Execution & Artifact Shipping**:
   - Runs test execution subprocess with environment isolation, captures traces and snapshots, streams live stdout/stderr events, uploads test artifacts to `/api/artifacts/upload`, and reports final status to `POST /api/jobs/{id}/complete`.

---

## 2. Distributed Job Queue & Scheduling

- Tasks are prioritized (`priority: 10` default, high priority P0 regressions scored `priority: 50+`).
- Workers claim tasks matching their hardware/browser capability profiles using `POST /api/jobs/claim`.
- Comprehensive task lifecycle: `QUEUED` $\to$ `ASSIGNED` $\to$ `RUNNING` $\to$ `COMPLETED` / `FAILED` / `CANCELLED`.
- Cancellation is propagated to active worker tasks: workers terminate active child subprocess trees upon detecting cancellation.

---

## 3. Runner Backends

A runner profile (`RunnerProfile`, `/api/runners`) selects the execution backend used for its runs:

1. **`LocalRunnerBackend`** (`qa_core.execution.runner_backend`): native async process execution for local developer loops.
2. **`JenkinsRunnerBackend`** (`integrations.jenkins_runner`): remote pipeline dispatch with health checks, triggered by profile type `JENKINS` and its `base_url` / `job_name` config.

Profiles of any other type fall back to the local backend.
