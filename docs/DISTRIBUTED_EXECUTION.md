# Phase 12 — Distributed Execution Platform & Cluster Architecture

## Overview

The **Distributed Execution Platform** decouples test suite triggers from local compute resources, dispatching test suites across worker nodes, containerized Docker runners, and ephemeral cloud sandboxes.

```
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

## 1. Node Discovery & Liveness Protocol

Worker nodes register with the central orchestrator and transmit periodic heartbeats (`POST /api/workers/{id}/heartbeat`):
- **Status lifecycle**: `ONLINE` $\to$ `BUSY` (when processing jobs) $\to$ `ONLINE` $\to$ `LOST` (if heartbeat missed for $>60\text{s}$) $\to$ `OFFLINE`.
- **Capability tags**: `browsers: ["chromium", "firefox", "webkit"]`, `os: "linux"`, `max_concurrency: 8`, `current_load: 2`.

---

## 2. Distributed Job Queue & Scheduling

- Tasks are prioritized (`priority: 10` default, high priority P0 regressions scored `priority: 50+`).
- Workers claim tasks matching their hardware/browser profiles using `POST /api/jobs/claim`.
- Comprehensive task lifecycle: `QUEUED` $\to$ `ASSIGNED` $\to$ `RUNNING` $\to$ `COMPLETED` / `FAILED` / `CANCELLED`.

---

## 3. Runner Backends

1. **LocalProcessRunnerBackend**: Native async process execution for local developer loops.
2. **DockerRunnerBackend**: Containerized execution with volume mounting and isolated ephemeral dependencies (`mcr.microsoft.com/playwright/python`).
3. **DistributedWorkerBackend**: Networked dispatch to remote worker pools.
