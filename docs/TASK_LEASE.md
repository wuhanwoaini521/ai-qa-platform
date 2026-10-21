# Task Lease and Multi-Instance Recovery

This document records what the runtime actually guarantees when more than one API process serves the
same database, what it does not, and how each claim was tested. It replaces nothing: `TaskRuntimeService`
is unchanged as the single owner of task state, and no second scheduler exists.

## 1. What was wrong (Round 18 audit)

| Symptom | Code before | Why it broke with two processes |
| --- | --- | --- |
| A peer's live task became `BLOCKED` when a second instance started | `apps/api/app/services/task_scheduler_service.py` `recover_interrupted()` acted on `tasks.unfinished()` | Startup treated "not finished" as "abandoned", so a rolling restart failed the work another replica was running |
| A peer's live requirement analysis became `FAILED` | `apps/api/app/services/requirement_lifecycle_service.py` `recover_interrupted()` rewrote every `RUNNING` history entry to `FAILED` with `API restarted before requirement analysis completed` | Same assumption, one layer up |
| A peer's live exploration was paused | `apps/api/app/services/quality_discovery_service.py` `recover_interrupted_runs()` paused every non-terminal run | Same |
| A peer's live failure analysis became `INTERRUPTED` | `apps/api/app/services/failure_workflow_service.py` `recover_interrupted_analyses()` | Same |
| A dead process could still write a terminal state | no ownership check on the write path | Nothing stopped a zombie from finishing a task a new owner had already taken |

The claim itself was already safe: `TaskRepository.claim_for_execution` is a conditional `UPDATE`, so two
processes could not run the same task at once. Everything that broke was *recovery*, not claiming.

## 2. The lease

Migration `0020_task_lease` adds three columns to `agent_tasks`:

| Column | Meaning |
| --- | --- |
| `lease_owner` | the runtime instance that currently owns the task (`TaskRuntimeService.runtime_instance_id`, a random hex per process) |
| `lease_token` | fencing token, incremented on every claim |
| `lease_expires_at` | when the claim stops being believable without a renewal |

- **Claim** — `claim_for_execution(task_id, owner, lease_seconds)` only succeeds when the task is `PENDING`
  *or* unfinished **and** unleased or past `lease_expires_at`. It returns the new fencing token.
- **Renewal** — a heartbeat task per running task renews every `HEARTBEAT_SECONDS` for `LEASE_SECONDS` (90).
- **Fencing** — `TaskExecutionOrchestrator._finish` checks `holds_lease(task_id, owner, token)` before any
  terminal write. If the lease moved, it records `task.lease_lost` and writes nothing. This is what stops a
  zombie process from overwriting a new owner's result.
- **Release** — a graceful stop hands the task back (`release_lease`) so a peer recovers it immediately
  instead of waiting for expiry.

## 3. Recovery windows

Startup recovery is the one place a process *cannot* know whether a peer is alive without a lease. Each
recovery therefore only touches rows that are provably stale:

| Recovery | Rule | Constant |
| --- | --- | --- |
| Task scheduler | unfinished and either unleased or past `lease_expires_at` | `TaskRepository.unfinished_stale(grace_seconds=0)` |
| Requirement analyses | last analysis `started_at` older than the analysis window | `STALE_AFTER_SECONDS` |
| Discovery runs | `updated_at` older than the same window (the loop stamps it on every state and action) | `QualityDiscoveryService.STALE_AFTER_SECONDS` |
| Failure analyses | `created_at` older than the configured analysis budget | `get_config().repair.analysis_timeout_seconds` |
| AI invocations | `created_at` older than 30 minutes | `AIRepository.STALE_INVOCATION_SECONDS` |

Anything fresher is left alone. That is a deliberate trade: a process that dies seconds after starting work
leaves its row untouched until the window passes, which is the honest outcome when no lease proves the owner
is gone.

## 4. What is verified

- `apps/api/tests/test_task_lease.py` — claim/token/expiry, renewal, fencing on a lost lease, release.
- `apps/api/tests/test_multi_instance_recovery.py` — a fresh requirement analysis, a moving discovery run, a
  leased task and a live provider call all survive a peer's startup; stale rows in the same tables are
  still recovered.
- `.ai-runs/overnight-delivery/rounds/r18_two_instances.py` — a real two-process drill on a scratch copy of
  the database (SQLite `backup()` snapshot, instances on 8030–8033, real AI provider). 8/8 checks:
  instance A takes a lease; a peer startup leaves the live analysis running and closes the orphaned one; the
  running task is untouched by the peer and still completes under its own owner; a restart right after a
  hard kill leaves an unexpired lease alone; after expiry a restart recovers the orphan as `BLOCKED`.

## 5. What is not verified (BLOCKED, not PASS)

- **Multi-host / multi-worker**: the drill runs two processes on one host against one SQLite file. No
  PostgreSQL instance is available in this environment, so `FOR UPDATE`/`SKIP LOCKED` behaviour, cross-host
  clock skew and connection-pool contention are untested.
- **Cancel and retry races across instances**: cancellation still writes through
  `TaskCommandService.cancel`, which sets `CANCELLED` directly. A cancel issued on instance B while A is
  mid-step is not fenced the way a terminal write is.
- **Discovery pause/stop across instances**: `QualityDiscoveryService` pause/stop signals are still
  in-process events; a stop issued on another replica only takes effect through `recover_interrupted_runs`
  once the run is stale. This is documented behaviour, not a new fix.
- **SQLite write contention**: the drill shows two processes can interleave short transactions, but it does
  not measure contention under load.
