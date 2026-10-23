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

## 4. Cancel is a request, not a terminal write (Hotfix 1)

Before Hotfix 1 the cancel endpoint changed the terminal state itself:
`TaskCommandService.cancel` executed `update_task(status=CANCELLED)` on whatever process served the HTTP
request. With a lease that meant a non-owner could overwrite a task another process was still executing —
the owner then wrote its own terminal state over the cancel, or the cancel hid a task that kept running.

Now the two halves are separate:

| Path | Who may write it | How it is guarded |
| --- | --- | --- |
| Cancel request (`cancel_requested_at`, `cancel_requested_by`) | any authorized caller | `TaskRepository.request_cancel` — one conditional UPDATE, first request wins, terminal rows untouched |
| Cancel finalization (`CANCELLED`) | the lease owner, or a recovery acting where no live lease exists | `TaskRepository.finish_fenced(require_no_live_lease=True)` for the API/recovery path; owner + token match for `_finish` |

The owner notices the request in three places: the DAG loop head and the step boundary read the row before
starting more work, and the heartbeat (every 20 s) cancels its own execution task. Every terminal write that
would land `FAILED`/`BLOCKED` while a request is pending is rewritten to `CANCELLED`, with the original
outcome recorded in `verification.interrupted_outcome` — so a cancel never loses the step that was interrupted.

Cancelling an already-terminal task still returns 409 and writes nothing; repeating a cancel records no
second request and no second terminal event.

## 5. What is verified

- `apps/api/tests/test_task_lease.py` — claim/token/expiry, renewal, fencing on a lost lease, release.
- `apps/api/tests/test_task_cancel_fencing.py` — ten cases: owner ends its own task at a step boundary; a
  non-owner only records the request (no `task.cancelled` event); an expired owner's `finish_fenced` returns
  false and changes nothing; after lease expiry a cancel is terminal immediately; recovery turns a requested
  cancel into `CANCELLED` and an unrequested orphan into `BLOCKED`; cancel-vs-completion leaves exactly one
  terminal event; a worker that lost its lease records `task.lease_lost`; a repeated cancel is idempotent;
  the new columns round-trip; and (PostgreSQL only) two concurrent transactions leave one terminal state.
- `.ai-runs/overnight-delivery/rounds/r18b_cancel_acceptance.py` — real Chromium, real backend, real SQLite:
  14/14 checks, no console error. A running `FIX_FAILURE` task cancelled from the UI records the request in
  the same second, reaches `CANCELLED` within two seconds, releases its lease, writes one request event and
  one terminal event, leaves no step `RUNNING`, shows a terminal state after a reload, and refuses a second
  cancel with 409.
- `apps/api/tests/test_multi_instance_recovery.py` — a fresh requirement analysis, a moving discovery run, a
  leased task and a live provider call all survive a peer's startup; stale rows in the same tables are
  still recovered.
- `.ai-runs/overnight-delivery/rounds/r18_two_instances.py` — a real two-process drill on a scratch copy of
  the database (SQLite `backup()` snapshot, instances on 8030–8033, real AI provider). 8/8 checks:
  instance A takes a lease; a peer startup leaves the live analysis running and closes the orphaned one; the
  running task is untouched by the peer and still completes under its own owner; a restart right after a
  hard kill leaves an unexpired lease alone; after expiry a restart recovers the orphan as `BLOCKED`.

## 6. What is not verified (BLOCKED, not PASS)

- **Multi-host / multi-worker**: the drill runs two processes on one host against one SQLite file. The
  PostgreSQL suite runs on a local container, so `FOR UPDATE`/`SKIP LOCKED` behaviour is exercised by tests
  but cross-host clock skew and connection-pool contention are untested.
- **Cancel across two real hosts**: the request/finalization split is proven in-process and on PostgreSQL
  with two sessions, and the pre-fix behaviour was reproduced when a stale second process really was
  executing the task. No second host exists in this environment, so `MULTI_INSTANCE_PASS` stays unclaimed.
- **Discovery pause/stop across instances**: `QualityDiscoveryService` pause/stop signals are still
  in-process events; a stop issued on another replica only takes effect through `recover_interrupted_runs`
  once the run is stale. This is documented behaviour, not a new fix.
- **SQLite write contention**: the drill shows two processes can interleave short transactions, but it does
  not measure contention under load.
