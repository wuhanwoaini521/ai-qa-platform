# Release Candidate baseline — ai-qa-platform

Freeze round: **no product changes, no new modules, no push / merge / deploy.**
Everything below was produced by the command beside it on the frozen tree; nothing is copied from a
document without re-running it.

| Item | Value |
| --- | --- |
| Frozen commit | `a17275d test(release): re-run the studio acceptance on the frozen tree` (evidence commit; the baseline document itself lands in the next commit) |
| Code commit under test | `b8958e2 test(pytest): put a hang guard on the suite and stop a timeout test racing its own budget` |
| Local RC tag | `rc-2026.10.22` (annotated, **local only**) |
| Recoverable archive | `runtime/backups/aiqa-rc-2026.10.22.bundle` — **self-contained** git bundle (62 MB, `git bundle verify` → "The bundle records a complete history"): it carries the whole history plus the tag, so it restores without the remote; untracked, local, never pushed |
| Unpushed commits | `origin/main..HEAD` = **37** (13 feat, 11 docs, 6 fix, 4 test, 1 style, 1 refactor, 1 chore) |
| Tracked tree | clean (`git status --porcelain` shows only untracked evidence dirs) |
| Migrations head | `0021_artifact_actor_width` |
| Date range of the delivery | 2026-10-20 → 2026-10-22 |

## 1. Which revision each number belongs to

The two full-suite logs were produced **before** the commit `b8958e2` was created, so their `HEAD:` line
reads `460cf3e` (the base commit). The tree under test is byte-identical to `b8958e2`: the following
command prints nothing, which is the proof.

```bash
git diff --stat b8958e2 -- pyproject.toml uv.lock \
  apps/api/tests/test_discovery_coverage_e2e.py apps/api/tests/test_failure_workflow.py
# (empty)
```

`b8958e2` contains exactly those four files plus the refreshed acceptance evidence and the regression logs,
so the tree that ran is the tree that is committed.

| Claim | Revision | Command | Evidence file |
| --- | --- | --- | --- |
| Backend SQLite **996 passed / 11 skipped / 890.37 s / exit 0** | tree of `b8958e2` (base `460cf3e`) | `uv run python -m pytest apps/api/tests packages -q` | `.ai-runs/overnight-delivery/regression/final-sqlite.log` |
| Backend PostgreSQL 16 **999 passed / 8 skipped / 2066.93 s / exit 0** | same tree | `AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test uv run python -m pytest apps/api/tests packages -q` | `.ai-runs/overnight-delivery/regression/final-postgres.log` |
| Frontend **227 pass / 0 fail**, `tsc` clean, `eslint --max-warnings=0` clean | `0f11fa3` (frontend unchanged after it; re-run on the frozen tree) | `pnpm --filter @ai-qa/web test` | output of this round's re-run |
| Real Chromium **24/24 PASS**, `failed: []` | frozen tree, re-run in this freeze round on `279ccd2` | `uv run python .ai-runs/overnight-delivery/rounds/r17_acceptance.py` | `.ai-runs/overnight-delivery/rounds/r17-acceptance.json` + `screenshots/after-r17-*` |
| Real Chromium Round 22 chains **15/15 PASS**, `failed: []`, `console_errors: []` | `53b7276` (no product code changed afterwards) | `uv run python .ai-runs/overnight-delivery/rounds/r22_acceptance.py` | `.ai-runs/overnight-delivery/rounds/r22-acceptance.json` |
| Real Chromium Round 21 UX/perf **12/12 PASS** | `6a865c3` | `uv run python .ai-runs/overnight-delivery/rounds/r21_acceptance.py` | `rounds/r21-acceptance.json`, `rounds/r21-perf-{before,after}.json` |
| Two-process runtime drill **8/8** | `19d845e` | `uv run python .ai-runs/overnight-delivery/rounds/r18_two_instances.py` | `regression/r18-two-instances.json` |
| Compose deployment drill **12/12** | `8b1c07d` | `uv run python .ai-runs/overnight-delivery/rounds/r20_deploy_drill.py` | `rounds/r20-deploy.json` |
| Test-hang guard active (180 s default, thread method, 900 s e2e mark) | `b8958e2` | a 10.9 s test dies at `--timeout=2`; the 168.8 s e2e survives `--timeout=30` | this round's shell output; `pyproject.toml` |

## 2. Working tree, untracked evidence, and what a clone would miss

```
$ git status --porcelain | grep '^??'
.ai-runs/{context-continuity,d1-d2-lifecycle,discovery-downstream,discovery-live,e2e-round12..e2e-round16,
          final-acceptance,gap-ux,governance,night-continuation,rc-acceptance/screenshots,recorder-studio,
          repair-chain,ui-redesign}/        (17 dirs, 2.2 GB total)
runtime/backups/                            (1.7 MB: three SQLite backups from 2026-10-19)
```

- **Inside git**: `.ai-runs/overnight-delivery/**` (the delivery evidence: reports, JSON, screenshots,
  regression logs) and every source file.
- **Outside git by design**: the older per-round `.ai-runs/*/` screenshot archives (2.2 GB) and
  `runtime/backups/`. `.gitignore` covers `runtime/projects|workspaces|artifacts|dev-logs|platform-v2-*`
  and `.ai-runs/*/test-work/`; the rest of `.ai-runs/**` is simply never staged. A fresh clone of this RC
  therefore has all code + the delivery evidence, but not the 2.2 GB of historical screenshots.
- The bundle in §"Recoverable archive" carries the whole history and the tag (restore with
  `git clone <bundle> ai-qa-platform-rc`), not the untracked files.

## 3. Sensitive-information audit

Scanned every added line in `git diff origin/main..HEAD` for provider keys, bearer tokens, private keys
and passwords, and separately scanned the committed evidence for provider material.

| Finding | Verdict |
| --- | --- |
| `POSTGRES_PASSWORD=drillonlypassword` in `.ai-runs/overnight-delivery/rounds/deploy-drill/drill.env` | **drill-only** local compose credential, paired with `APP_SECRET_KEY=drill-only-secret-key-not-for-production`, `QA_AI_ENABLED=false`, `JEV_ENABLED=false`; the stack it starts is created and destroyed by the same drill |
| `-e POSTGRES_PASSWORD=postgres` in a documented PostgreSQL-16 test-channel command (`docs/agent-handoff.md`) | the standard throwaway local test container, same value the repo already documents |
| Real provider credentials | **none in the repository.** The AI provider and Jev keys live only in the runtime environment/config (`config/config.yaml` reads `${QA_AI_*}` / `${JEV_*}`); no key appears in the evidence tree |
| Private keys / cloud credentials | none found |

## 4. Backups and migrations — recovery path, verified now

**Backup → restore drill (this round, on the live developer database):**

```
bash scripts/backup_db.sh /tmp/rc-drill        # WAL-safe snapshot through SQLite's backup API
bash scripts/restore_db.sh /tmp/rc-drill/aiqa_sqlite_20261022_140107.db.gz /tmp/rc-drill/restored.db
```

Result: every table compared — **44/44 identical**, including `test_runs` 76, `failure_records` 24,
`failure_analyses` 28, `agent_tasks` 103, `ai_invocations` 1631, `workflow_definitions` 41,
`discovery_evidence` 624, `discovery_suggestions` 13, and `alembic_version = 0021_artifact_actor_width`
on both sides.

**Migration drill on an empty database (this round):**

```
DATABASE_URL=sqlite+aiosqlite:////tmp/rc-drill/fresh.db uv run alembic -c apps/api/alembic.ini upgrade head
```

Result: `alembic_version = 0021_artifact_actor_width`, **44 tables**. `downgrade base` then leaves 36
tables, because `apps/api/alembic/versions/0001_baseline.py` deliberately keeps its tables
(`# Baseline reversal deliberately preserves all application data and tables.`) — a clean "drop
everything" reset is **not** a supported operation. `upgrade head` after that returns to 44 tables and
`0021`, so the upgrade path itself is idempotent.

**Supported rollback path** (and the one that is proven): roll back **one revision at a time**.
Round 20 drilled `downgrade 0021 → 0020` followed by `upgrade head` on a live PostgreSQL container
(`rounds/r20-deploy.json`), and `apps/api/tests/test_runtime_migrations.py` round-trips every migration
(the baseline excepted, by design) — 6 passed.

**Runbook, in order:** stop the API → `scripts/backup_db.sh` → `alembic downgrade -1` (only if the target
revision requires it) → restore the matching dump with `scripts/restore_db.sh` (it snapshots the current
file to `*.pre-restore.<ts>` before overwriting) → `alembic current` must equal the expected revision →
`GET /api/health` must return `{"status":"healthy","checks":{"database":"connected","artifact_storage":"writable"}}`.

## 5. The three release blockers

| # | Blocker | Code evidence | Why it blocks | Acceptance criteria to close it |
| --- | --- | --- | --- | --- |
| B1 | **DAG execution route missing** | `apps/api/app/services/workflow_definition_service.py:226 compile_plan` exists and `apps/api/app/services/task_scheduler_service.py` really honours `depends_on`, but `apps/api/app/api/workflow_definitions.py` exposes no execute route — `POST /api/workflows/{id}/execute` returns **404** (asserted in `r22_acceptance.py` and `r17_acceptance.py`) | a published definition cannot be run end to end, so the studio is a definition tool only (`DAG_EXECUTION_PASS` is BLOCKED) | a route that compiles a **published** version into `TaskStepSpec`s and starts it through the existing `TaskRuntimeService`; approval nodes still gate every `writes` node; an acceptance run that publishes v1, executes it, and reaches `COMPLETED` with per-step status; no second scheduler appears in the diff |
| B2 | **Cancel is not fenced across replicas** — *addressed by Hotfix 1, see §5.1* | `apps/api/app/services/task_command_service.py` writes the terminal `CANCELLED` row without checking the lease; recorded as `R18-B2` in `.ai-runs/overnight-delivery/blockers.md` | a non-owner replica can overwrite a task another process is still running, which is exactly what the lease in `19d845e` was added to prevent | cancel becomes a **request** row that only the lease holder may turn into a terminal state (or a fenced write that fails when `lease_owner` differs); a two-process test where a peer's cancel does not clobber a live owner's task; the existing `test_task_lease.py` fence tests stay green |
| B3 | **Remote CI and deploy/rollback acceptance never ran** | `.github/workflows/ci.yml` only runs on push to `main`, which this mission forbids; the same command set passes locally on SQLite **and** PostgreSQL; deployment is proven only as a single-host compose drill (`rounds/r20-deploy.json`, 12/12) | there is no evidence from a fresh machine or from the CI service, and no rolling replacement or rollback of a deployed version | a CI run on a real push (or a nightly schedule) that is green, including the PostgreSQL channel and the browser E2E; a deployment of two consecutive versions with a proven rollback to the first, on a clean host |

### 5.1 Hotfix 1 closed the B2 mechanism (PARTIAL, not a PASS)

`0022_task_cancel_request` adds `agent_tasks.cancel_requested_at/by`; `TaskRepository.request_cancel` records a
request with one conditional UPDATE (never a terminal state), and `TaskRepository.finish_fenced` is the only
path that may write `CANCELLED`, matching either `lease_owner+lease_token` or "no live lease". The owner
notices the request at the DAG loop head, at the step boundary and in the heartbeat, and any `FAILED/BLOCKED`
outcome that races a request is rewritten to `CANCELLED` with the original outcome kept in
`verification.interrupted_outcome`.

Evidence: `apps/api/tests/test_task_cancel_fencing.py` (10 cases, 9 on SQLite + 1 PostgreSQL-only),
`rounds/r18b_cancel_acceptance.py` on real Chromium + real backend + real SQLite (14/14), and the pre-fix
reproduction (a stale second process — an orphaned uvicorn from a previous stack — really was executing the
task and overwrote the cancel with `BLOCKED`, which is the defect in the field).

What is **not** closed: a second *host*. `MULTI_INSTANCE_PASS` therefore stays BLOCKED, and B1/B3 are untouched.

## 6. Minimal fix list for the next phase (nothing else)

Only the three items above, in this order, each as its own commit with its own acceptance evidence:

1. **B2 cancel fencing** — smallest of the three, pure backend, already has a failing scenario in mind.
2. **B1 execution route** — larger; requires a human decision on which node kinds may run unattended and
   where the approval gate sits. **Do not start without that decision** (it is a product/security call,
   not an engineering one).
3. **B3 CI + deploy rollback** — needs a real push/schedule permission and a host; cannot be closed from a
   local-only session.

Acceptance standard for the whole phase: the numbers in §1 must not regress (backend 996/999, frontend
227, browser 24/24), every new claim needs its own JSON/log evidence with the revision recorded inside the
log, and no item may be reported PASS without a run on the final tree.

## 7. What stays BLOCKED at this freeze

`DAG_EXECUTION_PASS` **BLOCKED** (B1) · `MULTI_INSTANCE_PASS` **BLOCKED** (B2, and no second host) ·
`RELEASE_CANDIDATE_PASS` **BLOCKED** (B3 + B1/B2).
`CORE_PRODUCT_PASS` **PASS** and `WORKFLOW_STUDIO_PASS` **PASS** stand, with the evidence in §1.
