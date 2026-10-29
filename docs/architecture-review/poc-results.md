# Isolated PoC Results — Partial; No Framework Adoption Decision

**Run date:** 2026-10-28.<br>
**Evidence detail:** `experiments/architecture-review/poc/evidence-2026-10-28.md`.<br>
**Isolation:** existing API tests use per-test temporary SQLite databases and temporary workspaces. Browser test uses a temporary HTTP server bound to `127.0.0.1`. No production source, user database, customer/third-party website, external provider, paid API, or package installation was used.

## Summary

| PoC | Evidence status | Result |
|---|---|---|
| A — Agent orchestration | **PARTIAL** | Exercised existing `TaskRuntimeService` state/approval/replan contracts through an 8-test isolated slice. Persistence, idempotent create, pause/resume state, approval endpoint and conservative restart recovery are represented. The selected tests mostly prepare state directly; they do not measure an alternative orchestrator, prove automatic retry recovery, or exercise production multi-process leases. |
| B — AI browser exploration | **PARTIAL** | Existing Playwright/Discovery baseline passed against a controlled loopback site with real Chromium/DOM geometry/frame evidence and fixture AI/decision. Browser Use and Skyvern were not installed/run; no comparable success, timing, locator, recovery or cost numbers exist. |
| C — AI test lifecycle | **PARTIAL / NOT COMPLETE** | Existing tests prove isolated Pytest result and evidence paths, including one deterministic failure/approval/targeted-rerun test. There was no model-generated scenario/test, independent user approval, or complete requirement→discovery→generation lifecycle. |

**Conclusion:** the existing platform is a valid control baseline worth preserving, but the user's required comparative PoC acceptance is **not met**. Phase 5 Gate remains **DEFERRED**. No candidate framework can be accepted or rejected on benchmark evidence from this run.

## PoC A — Agent Orchestration

### Existing system used

`TaskRuntimeService` is the only orchestration implementation exercised. Tests cover `TaskORM`/`TaskStepORM` persistence, task event cursors, an idempotency key, pause/resume, restart recovery, human approval endpoint, and replan. The source design is described in `current-state.md`; raw command output is in the experiment evidence file.

### Results by acceptance item

| Requested capability | Evidence / status | What was not established |
|---|---|---|
| State persistence | **PARTIAL** — task, steps, and events persist in the disposable DB; cursor replay test passes. | One persistence test manually sets terminal status/adds terminal event; not every step ran through a real scheduler/worker. No process restart against a fresh real app process in this test. |
| Node failure retry | **NOT TESTED as automatic retry.** A replan test turns a prepared failed step back to pending and preserves a completed step. | It does not inject a transient node exception and observe automatic retry attempt/backoff/duplicate effect. Do not equate operator replan with automatic retry. |
| Pause / resume | **PARTIAL** — pause boundary stores execution budget; resume returns the task to pending; separate tests cover workspace drift and concurrent resume. | Selected PoC slice prepares paused state rather than exercising a full browser task through pause/restart/resume. |
| Human approval | **PARTIAL** — waiting task is owner-scoped and approval endpoint transitions the step/task. | The API test itself posts `approved=true`; this is not a human study or independent user action. No real generated proposal was approved in this PoC. |
| Duplicate execution protection | **PARTIAL** — duplicate QA goal create with the same idempotency key returns the same task ID. | Does not prove no duplicate side-effecting execution across two API processes or after lease expiry. |
| Restart recovery | **VERIFIED for conservative block path** — a task/step prepared as RUNNING is marked BLOCKED/FAILED rather than replayed. | Does not auto-resume; worker crash, DB lease, browser state and cross-process scheduler reconciliation are not covered. |
| Candidate orchestrator comparison | **NOT RUN** | LangGraph and other candidate packages absent; network prevented fetching/installing them. |

### Exact verification

The initial six-test run passed (**6 passed / 8.02 s**). Fresh QA independently reran a combined eight-test slice (**8 passed / 9.57 s**, exit 0), including the PoC B and C control tests. These are acceptance-scoped evidence only; they are not the full backend suite.

## PoC B — AI Browser Exploration

### Sample and protocol

- **Sample:** one controlled local site, three pages (`/`, `/search`, query results), named “QA Shop”; user intent is navigate to Products and observe/search a safe form. No destructive action or external site.
- **Existing baseline:** `apps/api/tests/test_quality_discovery_live_e2e.py::test_live_discovery_stream_carries_real_frames_geometry_and_highlights` using `PlaywrightBrowserRuntime`, Playwright 1.62.0 and local system Chrome 150.0.7871.125.
- **Comparison candidates:** Browser Use and Skyvern. Their release/license/manifest metadata was verified in a later bounded source pass (see `framework-p0-verification-2026-10-28.md`); neither was installed or run, and project compatibility remains untested.
- **AI/provider controls:** `DiscoveryFixtureAI` plus a test-controlled `DecisionService.choose`; the real-provider readiness gate is bypassed by the fixture test. It is a real browser/runtime observation path, **not real AI success**.

### Observed evidence

- Test passed **1/1 in 16.78 s** in the initial standalone execution. QA's later 8-test combined slice also passed the same browser test.
- The test asserts streamed browser-frame bytes are real JPEGs and match bytes captured by the adapter; minimum frame payload exceeds 2 KB.
- The test asserts live page DOM geometry for a Search input and Products link is within **±8 CSS px** of fixed fixture coordinates; exact observed deltas are not printed/captured.
- A real locator/inventory, page highlight overlay, persisted state and screenshot artifact are asserted. The controlled decision fixture is attributed in the result.
- Cleanup asserts runtime sessions/resources/process-local Discovery tasks are closed and the test run is terminal.

### Comparison table

| Metric | Existing Playwright/Discovery baseline | Browser Use | Skyvern |
|---|---|---|---|
| Same local sample/task | **Run** | **NOT RUN** | **NOT RUN** |
| Page recognition | Fixture-backed real DOM observation; test assertions pass | No observation | No observation |
| Action success rate | One controlled fixture test passed; no statistical rate | No data | No data |
| Locator stability | Geometry+locator existence asserted on fixed page; no mutation/flakiness sample | No data | No data |
| Provider/model tokens & cost | 0 model calls in this fixture; not comparable to real AI | No data | No data |
| Wall time | 16.78 s for pytest test process, including fixture/runtime setup/cleanup; not a per-action latency metric | No data | No data |
| Failure recovery | Cleanup/resource release asserted; no forced browser/model failure comparison | No data | No data |
| Evidence quality | JPEG matches adapter capture; geometry, highlight, state and screenshot artifact asserted | No data | No data |

This is a **single controlled integration test**, not a benchmark. Do not extrapolate success rates or token cost. Official release/license/manifest metadata is now known for Browser Use and Skyvern, but the comparison remains NOT RUN until dependency compatibility and Skyvern legal review pass, and each uses the same site, tasks, retry budget, provider policy (or identical local model), and evidence rubric.

## PoC C — AI Test Lifecycle

### Exercised deterministic control

`apps/api/tests/test_agent_tasks.py::test_real_failure_record_repair_approval_and_targeted_rerun` ran in an isolated workspace. It creates an actual initial failing Pytest run, persists failure evidence, uses the deterministic fallback classifier and test-supplied repair data, submits a fixture API approval, runs the targeted test again, and checks the persisted result. Test: **1 passed in 3.88 s**, and it passed again in QA's combined slice.

### Requested lifecycle coverage

| Stage | Status | Evidence or gap |
|---|---|---|
| Requirement | **NOT TESTED in a single lifecycle** | Other Task Runtime tests validate requirement preview/context, but not tied to this test's browser/test output. |
| Page exploration | **PARTIAL** | PoC B visits a loopback local page; the run is fixture-driven and not tied to a generated scenario. |
| Scenario suggestion | **MISSING** | No model-generated scenario was produced. |
| Human confirmation | **PARTIAL** | Approval state/API path exists, but tests post the decision automatically; not a real operator confirmation. |
| Test generation | **MISSING for this PoC** | Repair test changes an existing assertion based on supplied old/new values; it does not generate a new test from an approved scenario. |
| Pytest execution | **VERIFIED in isolated test path** | Real local Pytest failure and targeted rerun are used. Deterministic execution status is the source of truth. |
| Result analysis | **PARTIAL** | Failure classification and persisted result are asserted, but no model-generated explanation is validated. |
| Evidence | **PARTIAL** | Isolated persisted failure/run/evidence path is exercised; no full provenance package from AI scenario through approved generated test exists. |

Thus PoC C is **not** the requested complete AI Test Lifecycle; it verifies deterministic controls surrounding a failure repair flow. No AI statement is treated as PASS/FAIL evidence.

## Reproduction

From repository root, with the existing project environment and no dependency sync:

```bash
uv run --no-sync pytest -q \
  apps/api/tests/test_agent_tasks.py::test_task_api_persists_task_steps_and_replayable_terminal_events \
  apps/api/tests/test_agent_tasks.py::test_goal_preview_uses_selected_context_and_duplicate_start_is_idempotent \
  apps/api/tests/test_agent_tasks.py::test_pause_boundary_persists_execution_budget_before_resume \
  apps/api/tests/test_agent_tasks.py::test_restart_recovery_blocks_active_steps_without_replaying_them \
  apps/api/tests/test_agent_tasks.py::test_task_approval_resumes_only_an_owned_waiting_task \
  apps/api/tests/test_agent_tasks.py::test_replan_retries_failed_step_and_preserves_completed_steps \
  apps/api/tests/test_agent_tasks.py::test_real_failure_record_repair_approval_and_targeted_rerun \
  apps/api/tests/test_quality_discovery_live_e2e.py::test_live_discovery_stream_carries_real_frames_geometry_and_highlights
```

This command is known to use test-only DB/workspace fixtures; still inspect `apps/api/tests/conftest.py` before reuse. Do not remove `--no-sync`, invoke a real model/provider (including Jev), or replace the loopback site with an unauthorized external target for the architecture review.

## Stop / next gate

No additional candidate packages should be installed or provider calls made without an explicit cost and environment plan. Resume only after dependency compatibility, legal review (Skyvern), an approved bounded environment/provider budget, and the PoC scope pass. Record those results separately; do not overwrite this partial baseline evidence.
