# Overnight delivery — final report

Mission: `m05387`, Rounds 17 → 22. Repo `/home/hans/self-github/ai-qa-platform`.
Every number below was produced by the command beside it on the final code; nothing is copied from an
earlier round without re-running it.

## 1. Final HEAD

this commit (subject: `docs(release): record the frozen final regression, both channels, and classify every
older record`) on top of `b8958e2 test(pytest): put a hang guard on the suite and stop a timeout test racing its own budget`.
35 commits ahead of `origin/main`, **nothing pushed** (the
mission forbids push/merge/deploy). The earlier code commits of the delivery are `53b7276` (Round 22),
`0f11fa3` (Round 17 re-audit) and `460cf3e` (report correction); everything measured below was re-run on
`b8958e2`.

## 2–3. Per round: commit and verdict

| Round | Commit | Verdict |
| --- | --- | --- |
| 17 Versioned QA Workflow Studio | `553995a` (definition) + `10ff830` (editor) + `ad49266` (docs) | **PASS A** definition, **PASS B** editor, **BLOCKED C** DAG execution |
| 18 Runtime reliability | `19d845e` | **PASS** two processes on one host; **BLOCKED** multi-host |
| 19 AI workflow planner | `3c0add5` | **PASS** planner + validation; execution **BLOCKED** |
| 20 CI / PostgreSQL / deployment | `8b1c07d` | **PASS** CI-command parity, PG channel, single-host compose drill; CI service **BLOCKED** |
| 21 UX / performance / observability | `6a865c3` | **PASS** |
| 22 Release candidate audit | `53b7276` | **PASS** audit; release level **BLOCKED** (see §12) |
| 17 re-audit + final engineering close | `0f11fa3` + `b8958e2` | **PASS** (7-phase verification, 24/24; hang guard + all-green final runs) |

## 4. Delivered

- Versioned workflow definitions: 25-kind catalogue with per-node input contracts and risk flags, draft →
  publish with an immutable published version, optimistic `base_checksum` guard, version compare and a
  definition-vs-execution diff, compile-to-plan through the existing `task_scheduler_service`.
- Canvas editor in the existing workspace: add/remove nodes from the whitelist, connect/disconnect, edit
  inputs, undo/redo, auto-layout, validation panel, version list, publish gated by permission.
- Natural-language planner: real provider call, catalogue-only node kinds, schema validation, bounded
  single correction, nothing persisted or executed without a human.
- Runtime leases: `lease_owner` / `lease_token` / `lease_expires_at`, per-task heartbeat, fenced terminal
  writes, staleness windows for all four startup recoveries.
- PostgreSQL parity fixes, runnable container images, a 12-check deploy/backup/rollback drill.
- Canvas legibility: measured readability floors (0.82 desktop / 0.72 narrow), 11 px minimum card text,
  stacked tree on phones, bounded retry for the fit effect, evidence pagination.

## 5. Not delivered (honest list)

- **DAG execution** of a published workflow. Definitions compile and the scheduler honours `depends_on`,
  but there is no approved end-to-end execution path; `POST /workflows/{id}/execute` is 404.
- **Multi-instance across hosts** (needs PostgreSQL + a second host), **cancel fencing across replicas**
  (a `cancel` from a non-owner replica still writes `CANCELLED` directly — recorded as `R18-B2`).
- **CI on a real runner**, **deploy/rollback beyond the single-host compose drill**, **Windows/macOS
  launchers**.
- Real task-level evidence association for every task type (`agent_task_evidence` is only written by the
  discovery-gap analysis), and E2E-generated cases are still ordinary cases in the dev project.

## 6–8. Test statistics (final code)

Final numbers are the ones measured on the frozen final code (logs carry HEAD, command, start/end and exit code under `.ai-runs/overnight-delivery/regression/`).

| Gate | Result (final code) |
| --- | --- |
| Backend pytest (SQLite) | **996 passed / 11 skipped / 63 warnings / 890.37 s / exit 0** — `regression/final-sqlite.log` |
| Backend pytest (PostgreSQL 16) | **999 passed / 8 skipped / 61 warnings / 2066.93 s / exit 0** — whole suite `apps/api/tests packages` on `postgres:16-alpine` (`aiqa-r20-pg`, port 55432), `regression/final-postgres.log`; the 3-test difference is the `postgres`-marked tests that skip on SQLite |
| Frontend tests | **227 pass / 0 fail** |
| TypeScript / ESLint | clean / clean |
| Ruff check + format | clean, 488 files |
| OpenAPI contract | current |
| i18n | 25 namespaces, 2 languages, 3390 keys |
| Alembic | `test_runtime_migrations.py` 6 passed (up/down round trip) |
| Test-hang guard | `pytest-timeout` 2.4.0, 180 s default (`timeout_method = "thread"`), real-browser e2e marked 900 s; both directions proven (a 10.9 s test killed at 2 s; the 168.8 s e2e survived `--timeout=30`) |
| Real Chromium E2E (Round 22 audit) | **15/15 PASS**, `failed: []`, `console_errors: []` — ran at `53b7276`; no product code changed afterwards |
| Real Chromium E2E (Studio, re-run on final code) | **24/24 PASS**, `failed: []` — `rounds/r17_acceptance.py` |

### 6.1 Regression records classified by the revision they actually ran on

| Record | Code state | Result | Status |
| --- | --- | --- | --- |
| `regression/final-sqlite.log` | final HEAD | 996 / 11 / 890.37 s / exit 0 | **final** |
| `regression/final-postgres.log` | final HEAD | 999 / 8 / 2066.93 s / exit 0 | **final** |
| `regression/durations-sqlite.log` | `460cf3e` | 1 failed / 995 passed / 1402.88 s | used only to choose the timeouts; the failure is a test-side race, fixed (see 6.2) |
| `r17-readaudit-backend` | `0f11fa3` | 996 / 11 / 706.27 s | valid for that revision, superseded by the final run |
| `r22-backend-verbose` | `53b7276` | 996 / 11 / 677.08 s | valid for that revision |
| `r22-backend-full-v2` | pre-R22-fixes (`6a865c3` + planner work) | 994 / 11 / 724.80 s | superseded by 996 |
| `r21` suite | `6a865c3` | 994 / 11 / 724.80 s | valid for that revision |
| `rounds/r20-postgres.txt` | `8b1c07d` | 838 / 8 / 1086.64 s | valid, but that run covered `apps/api` only |
| `backend-full-sqlite-r20` | `8b1c07d` | 989 / 11 / 1049.87 s | valid for that revision |
| `r22-backend-full` | — | `unrecognized arguments: --timeout=600` | **invalid** (plugin absent, suite never ran) |
| `r22-backend-full-final` | — | exit 143 | **invalid** (SIGTERM, killed by me) |
| `r22-backend-final-2` | — | 57 % progress only | **invalid** (truncated, no summary) |

### 6.2 The one failure in the final-code discovery run was a test-side race

`apps/api/tests/test_failure_workflow.py::test_analysis_timeout_ends_the_run_with_an_explicit_retryable_error`
asserted that the hanging provider coroutine received the cancellation within 3 s. The product side
was already correct in that same run: `run.timeout` was emitted, the log recorded
`Failure analysis timed out analysis_id=… budget=0.5s`, and the record ended `TIMEOUT` with
`block_reason=ANALYSIS_TIMEOUT` and `START_ANALYSIS` still allowed. The race: a 0.5 s budget can
expire during setup on a loaded suite *before* the provider call is entered, so there is nothing to
cancel and the event never fires. Fixed in the test only (budget 5 s, wait 10 s, reason in a comment);
the file is 50 passed, and the run below is the one that counts.

## 9. Real AI/Jev acceptance

`rounds/r22-acceptance.json` — provider `mimo-v2.6-flash` via the `openai-compatible` adapter, Jev
`jev-1.13.0`. Planner invocation `ffbaf78f-4998-4b17-a880-1c479e622b7d`: valid 14-node plan, first
attempt. Diagnosis/repair invocations are recorded in the same trace with their tokens
(`input 938 / output 1871` for the planner). Jev scoring is exercised by the Round 16 acceptance
(`score 0.505 / confidence 0.90`), not re-run here.

## 10. Database and migrations

Migrations `0019_workflow_definitions` → `0020_task_lease` → `0021_artifact_actor_width`, all reversible;
`test_runtime_migrations.py` walks the downgrade/upgrade round trip on SQLite and the same suite passes on
PostgreSQL 16. The Round 20 drill proved `alembic downgrade 0021→0020` then `upgrade head` on a live
container, and a `pg_dump` restore into a second database with identical row counts and migration version.

## 11. Multi-instance

`.ai-runs/overnight-delivery/regression/r18-two-instances.json` → **8/8**: two real processes on one host;
the peer's startup leaves a live lease alone and closes an orphaned one; an expired lease is recovered;
a task reaches `COMPLETED` under its own owner. Multi-host is **BLOCKED** (no second host).

## 12. CI/CD and deployment drills

CI service **BLOCKED** — the workflow only runs on push to `main`, which this mission forbids; the CI
commands were run locally instead and that is how the `pytest apps/api` collection bug and two stale tests
were found (`rounds/r20_ci_parity.md`). Deployment drill `rounds/r20-deploy.json` → **12/12** on an
isolated compose project. `RELEASE_CANDIDATE_PASS` is therefore **not** claimed.

## 13. Screenshots

- Round 21 before/after: `.ai-runs/overnight-delivery/rounds/screenshots/r21-{before,after}-{pipeline,execution,editor,failure,dashboard,failures,runs}-w{1560,1280,1024,390}.png`
- Round 17 editor: `.ai-runs/overnight-delivery/rounds/screenshots/r17-*`
- Round 18/20 drills are JSON + container logs (no UI).

## 14. Performance data (measured, not estimated)

Pipeline 0.82 zoom at 1560/1280/1024 and 0.72 at 390, smallest text 9 px / 7.9 px (before: 0.47 and
6.2 px, with 30 cards under 9 px at 1280/1024). Execution tree 1 / 0.957 / 0.876 / 1 (phone stacked,
nothing outside the viewport). Editor 0.95 / 8 px at 390. Stress run on a real-trace copy: 100/500/1000
nodes mounted in 853/944/1107 ms, pan 27.8/73.5/25.8 ms, DOM 537/9314/18410, 1000 nodes at 0.7 zoom. FCP
dashboard/runs/failures 220/180/188 ms. **Caveat:** `MAX_NODES = 30` and the 6-task project trace mean
100+ nodes are unreachable through product paths; the stress sample is scaled, and the 100-node figure
races the panel's 3 s poll.

## 15. Security conclusions

Single provider registry, no second agent loop, AI never decides PASS/FAIL (assertions come from real
exit codes). Planner containment verified: prompt cap 2000 chars, node fields rebuilt from
`{key≤60, kind≤80, inputs, rationale≤400}`, nested/undeclared fields dropped, unknown kinds rejected,
nothing written or executed. Project ACLs enforced on every new route (`AUTOMATION_EDIT` for planning,
role split for publish). Model request bodies are redacted before they reach the UI. The independent
reviewer's remaining findings are performance/quality debt, not security: `ExecutionTreePanel`'s
`nodesInitialized` dependency and the discovery-evidence ACL test using a non-existent run id (routes do
inherit `discovery_run_access`).

## 16. Remaining risks, by priority

- **P1 (product)**: a workflow definition cannot be executed end to end; the studio is a definition tool
  until an execution path is approved.
- **P1 (runtime)**: `cancel` is not fenced — a non-owner replica can write a terminal `CANCELLED`.
- **P2**: planner is model-dependent (3 of 4 real calls valid, one 122 s timeout before the budget fix;
  final acceptance needed 1 attempt) and slow (~50 s); the pipeline-viewport regression is fixed by
  reading but was not reproduced in a browser; evidence paging has no UI consumer; E2E runs create real
  cases in the dev project.

## 17. Suggested next steps for a human

1. Decide the execution contract for published workflows (which node kinds may run unattended, and where
   the approval gate sits) — that is the only thing between `WORKFLOW_STUDIO_PASS` and `DAG_EXECUTION_PASS`.
2. Add cancel-request rows so a non-owner replica cannot force a terminal state (`R18-B2`).
3. Turn CI on for a push (or a nightly schedule) so the PostgreSQL channel and the E2E suite run on a
   fresh machine; the container drill is ready to reuse.
4. Before any push: 34 commits are local, evidence is under `.ai-runs/overnight-delivery/` (committed) and
   the rest of `.ai-runs/**` stays untracked by design.

## 18. The five verdict levels, stated separately

| Level | Verdict | Why |
| --- | --- | --- |
| `CORE_PRODUCT_PASS` | **PASS** | Both business chains run end to end on real Chromium with the real provider: run → failure → analysis → human approval → apply → exact verification; and sentence → candidate workflow → draft → publish → stop before execution. 996/999 backend, 227 frontend, 15/15 + 24/24 real-browser checks, no console error. |
| `WORKFLOW_STUDIO_PASS` | **PASS** | Definitions are versioned, validated (writes need an approval ancestor), published immutably, restorable as a draft, diffable against a published version and against a real task; layout is saveable. 24/24 acceptance. |
| `DAG_EXECUTION_PASS` | **BLOCKED** | `WorkflowDefinitionService.compile_plan` exists and `task_scheduler_service` really honours `depends_on`, but no route executes a definition (`/execute` → 404) and no approved end-to-end execution of a stored graph is proven. |
| `MULTI_INSTANCE_PASS` | **BLOCKED** | Proven for two processes on one host only (lease, heartbeat, fencing, 8/8 drill). No second host and no PostgreSQL-backed multi-replica run; `cancel` is still unfenced across replicas (`R18-B2`). |
| `RELEASE_CANDIDATE_PASS` | **BLOCKED** | CI has never run in the CI service (the mission forbids push), deployment is proven only as a single-host compose drill, and multi-instance is blocked. What *is* proven: the CI command set passes locally on SQLite **and** PostgreSQL, images build and run, and the stack survives a downgrade/upgrade plus a database restore. |
