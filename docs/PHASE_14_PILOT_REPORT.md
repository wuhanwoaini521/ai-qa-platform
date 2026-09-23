# Phase 14 Pilot Report — Real Project Onboarding & Hardening

Reference repository: `docs/PILOT_REFERENCE_PROJECT.md` (`/Users/hans/Code/github/playwright-test`).
Everything below was executed against the platform API on 2026-09-23; the reference repository was
hashed before and after and is byte-identical.

---

## 1. Import isolation (Gate 14.3)

| Step | Result |
|---|---|
| Preview | 146 files, 946,893 bytes, excluded: `.git`, `.venv`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, `allure-results` |
| Import | copied to `runtime/workspaces/<project id>` — the same path every other component derives from a project id — and registered in the `workspaces` table |
| Source integrity | aggregate SHA-256 before `ac79db91196abd2eb81e56522d500e3c7fa6ab959e6c2f0c7365e238176787ba`, after **identical** |

## 2. Runtime isolation (Gate 14.4)

`POST /api/onboarding/{id}/runtime` → `uv sync` inside
`<workspace>/.qa-platform-runtime` (never the platform's own interpreter), exit 0:
Python 3.12.14, playwright 1.62.0, pytest 9.1.1, pytest-xdist 3.8.0, pytest-rerunfailures 16.6,
allure-pytest, playwright 1.62.0.

## 3. Real collection (Gate 14.5)

`POST /api/onboarding/{id}/collect` → `COLLECTED`, exit 0, 2.1 s, **71 tests over 14 files** with
class-based ids and fixed fixtures preserved (`tests/test_baidu_search.py::TestBaiduSearch::test_open_homepage[chromium]`).
A deliberately broken project returns `COLLECTION_ERROR` with pytest's diagnostics — never "0 tests".

## 4. Test identity (Gate 14.6)

`NodeIdCaseMapper` resolved 71 logical tests in 4 ms. The reference repository's C-id convention lives
in its Test Management integration layer, not on the unit tests, so the honest result is: **0 tests
carry a case id, 71 are tracked by node id** (`unmapped_nodeids` is reported, not silently empty).
One-parameterised-function-to-many-logical-tests is modelled: each `[param]` instance is a distinct
logical test sharing its function's mapping unless an explicit `.qa-platform-cases.yaml` overrides it.

## 5. Safe execution (Gate 14.7)

| Requested | Executed | Refused (reasons) |
|---|---|---|
| 2 live UI tests + 1 unit test | 1 unit test, **PASSED** in 5.3 s total | `requires the 'page' fixture`, `contains 'https://'` → `calls page.goto()` |
| 69 `tests/unit/**` node ids | **68 executed, 68 passed** (1.15 s) | 1 refused: `test_fake_browser_adapter_navigation_and_observation` calls `navigate()`/`fill()`/`click()` on a *fake* adapter — indistinguishable from a real browser statically, so the policy errs towards refusing (an operator can override with `allow_unsafe`) |

Safety is enforced per test, not per marker (`-m smoke` in this repository would run live tests).

## 6. xdist and rerun modelling (Gate 14.8)

- **xdist**: the same 68 executed unit tests run three ways, with identical logical counts:

  | Mode | exit | logical | physical | passed | failed |
  |---|---|---|---|---|---|
  | sequential | 0 | 68 | 68 | 68 | 0 |
  | `-n 1` | 1 | 68 | 68 | 67 | 1 |
  | `-n 2` | 1 | 68 | 68 | 67 | 1 |

  The single failure under parallelism is the reference project's own
  `test_worker_id_and_retry_index_resolution`, which asserts the worker id is `master`/`none` — a real
  finding about the *reference* project, not a platform defect. Each xdist worker writes its own report
  file (a shared file would be truncated and interleaved), the controller does not write at all, and
  previous runs' log files are cleared before each run.
- **rerun**: two controlled tests with two retries allowed → **2 logical tests, 4 physical attempts,
  2 reruns**; the flaky test is `PASSED` with `attempts=2, reruns=1` (never counted twice), the
  locator test `FAILED` with `attempts=2, reruns=1`.

  Run options are named (`n_workers`, `reruns`) rather than arbitrary flags: an earlier `extra_args`
  passthrough allowed any pytest flag (`-c`, `--rootdir`, `-p`, `--junitxml`) to reach the project
  process at `automation:edit` privilege and was removed.

Rerun accounting no longer depends on parsing `RERUN` lines: the platform writes a small pytest
plugin into the workspace that records one JSON line per attempt, because the reference project's own
logging interleaves with pytest's progress output.

## 7. Allure compatibility (Gate 14.9)

`POST /api/onboarding/{id}/allure` imported **4 real result files** produced by the pilot run
(`ERROR ×2`, `FAILED ×1`, `PASSED ×1`) with `historyId`, `fullName`, labels (`parentSuite`, `suite`,
`framework`, `language`, `package`) and attachments. Allure remains evidence: the run's verdict comes from pytest's exit status, never from Allure. The
per-test outcomes come from a platform-written report log that lives **outside** the workspace and is
cross-checked against pytest's own summary line, so a project cannot rewrite its own verdicts.

## 8. Failure pilot (Gates 14.10 / 14.11)

A controlled locator regression inside the imported workspace produced:

| Stage | Result |
|---|---|
| Failure record | `LOCATOR_CHANGED`, `failing_locator = #checkout-submit`, suggestion "Target web element locator could not be resolved in the DOM" |
| AI diagnosis | root cause + confidence 0.92 (deterministic fake provider) |
| Repair proposal | `old_locator #checkout-submit` → `[data-testid="submit"]`, strategy `semantic-attribute`, confidence 0.92, **`applied: false`** |
| Application | manual only: the UI's apply step is a separate, human-triggered call |

## 9. History and flaky analytics

`GET /api/flaky?project_id=…` returned 71 entries with score components
(`sample_count`, `failure_rate`, `rerun_recovery_rate`, `alternation_rate`, `recent_instability`,
`confidence`, `classification`); `GET /api/flaky/history?nodeid=…` shows the rerun as
`retry_count: 1` on one logical test rather than a second test.

## 10. Scale and performance (Gate 14.17)

Seeded 20 projects / 1000 requirements / 10 000 test cases / 2000 runs / **100 000 executions** /
2000 failures / 5000 jobs, then measured the endpoints the gate names:

| Endpoint | Before | After | Note |
|---|---|---|---|
| `GET /api/dashboard/stats` | 5 458 ms | **843–1047 ms** | counts and the five rendered rows are queried, not whole tables |
| `GET /api/quality/risk-matrix` | **HTTP 500** | **676 ms** | crash fixed (see below) |
| `GET /api/flaky` | 532 ms + 1 query per test | **682–787 ms, 1 query total** | window function replaces the N+1 |
| `GET /api/quality/coverage` | 368 ms | 376–382 ms | |
| `GET /api/flaky/history` | 283 ms | 280–296 ms | |
| `GET /api/workspaces/{id}/files` (file tree) | — | 297 ms | |
| `ContextSelector.select(...)` (AI context) | — | **9 ms**, 6 fragments, 8.4 KB | |
| `GET /api/runs?project_id=…&limit=50` | 382–418 ms / **799 KB** | unchanged | *known gap*: listing runs eager-loads every execution |

Defects found by running at scale (all three were invisible in the small test fixtures):

1. `calculate_risk_matrix` read `flaky_score.flip_rate`, which does not exist on `FlakyScore` → HTTP
   500 for any project with flaky tests. Fixed to use `alternation_rate`.
2. `list_flaky_tests` issued one query per distinct test. Replaced with a single window-function
   query (`ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY started_at DESC)`), portable across
   SQLite and PostgreSQL.
3. `GET /api/failures?project_id=…` silently ignored the filter (`FailureService.list_failures`
   took no arguments), so the Failures page showed every project's failures. The filter now joins
   the failure's run and is covered by `test_failures_are_scoped_to_the_requested_project`.
4. `GET /api/testrail/runs/{id}/preview` returned HTTP 500 as soon as a run had executions
   (`TestExecutionORM` has `nodeid`, not `test_name`), so the TestRail publish preview had never
   worked on real data. Fixed and covered by
   `test_testrail_publish_preview_with_real_executions`.

## 11. Reliability (Gate 14.16)

- Abandoned runs can no longer stay `RUNNING` forever: `POST /api/runs/recover-stale` and a startup
  recovery pass close runs that never reached a terminal state — as `CANCELLED`, never as a
  fabricated PASS/FAIL.
- SSE: a stale token returns to the sign-in screen instead of a silent blank screen. The client now
  handles the event names the server actually publishes (`RUN_STARTED`, `TEST_FINISHED`, `LOG_STREAM`,
  `RUN_FINISHED`, `RUN_ERROR`, `RUN_CANCELLED`); a dropped connection still falls back to a one-shot
  refetch (the client closes the stream on error rather than reconnecting).
- Worker: registration/heartbeat now send the schema the API accepts and report real load.
- AI: provider failures fall back to the deterministic fake provider with `fallback_used=true`
  recorded on the invocation row.

## 12. Security (Gate 14.18)

| Vector | Result |
|---|---|
| Path traversal on workspace ids | rejected (symlink/sibling/`..` covered by tests) |
| pytest flag injection via node ids (`--pyargs=os`, `-p evil`, `--collect-only`, shell fragments) | rejected with 400 before reaching the command line |
| Marker expression injection (`smoke --alluredir=/tmp/evil`) | rejected with 400 |
| Symlink escape from a workspace | rejected on read and write |
| Unauthenticated access to any non-probe route | 401 (36 authorization tests) |
| Role escalation (VIEWER writing, ENGINEER gating a release) | 403 |
| Secret leakage in prompts/traces | `SensitiveRedactor` + context selection excludes non-related files |
| Process/socket/file access from a selected test | refused (case-insensitive call matching, driver-import and socket coverage, escaping-path detection) — nine evasion cases pinned by test |
| Absolute node id pointing at a host file | rejected by validation and by the policy |
| Arbitrary pytest flags in the run request | the raw `extra_args` passthrough was removed; only named `n_workers`/`reruns` options remain |

## 13. UX dogfooding (Gate 14.19)

Findings from running the workflow end to end in a browser, and their disposition:

| Finding | Status |
|---|---|
| Saving an automation binding always failed (frontend sent `test_file_path`/`test_node_id`; API requires `nodeid`/`file_path`/`workspace_id`) | **fixed** — verified in the browser: binding saves, card shows file path and node id |
| Every "run test" action failed with 422 (`target_nodeids`/`triggered_by`, no `workspace_id`) | **fixed** — payloads now match `TestRunCreate` |
| Failure rows rendered blank test ids and default badges (`nodeid`/`category` fields the API never returns) | **fixed** — uses `test_nodeid`/`classification` |
| Projects table's Studio/Requirements buttons opened the *previously* selected project | **fixed** |
| `/projects` showed the Requirements title | **fixed** |
| Studio deep link with `%` in a path could crash the view | **fixed** (encoded once) |
| A stale session rendered a blank screen | **fixed** — returns to sign-in |
| Run list payload is large (≈800 KB for 50 runs) | open (P2, see `docs/PILOT_GAP_ANALYSIS.md`) |

## 14. Test suite at the end of the phase

| Lane | Result |
|---|---|
| SQLite (`uv run pytest`) | 177 passed, 3 skipped |
| PostgreSQL (`AI_QA_TEST_DATABASE_URL=…`) | 179 passed |
| Lint (ruff check + format, eslint) | clean |
| Frontend typecheck + build | clean; entry chunk 254 kB (gzip 77 kB) |
| GitHub Actions | `Backend Lint & Test`, `Backend Tests (PostgreSQL 16)`, `Frontend Lint & Build` — see `docs/RELEASE_READINESS.md` |

## 15. Jenkins compatibility (Gate 14.14)

The reference repository has **no Jenkinsfile** (`ls Jenkinsfile` → absent), so there is no real job
contract to map against. What was verified instead:

- the platform's parameter mapping against the fake Jenkins server:
  job defaults (`REGION`, `NUM_PROCESSES`) merge with per-request parameters (platform values win),
  `markers` and `nodeids` map onto the configured Jenkins parameter names
  (`CASES_SPECIFIED`, `TARGET_TESTS`), and an empty selection adds no empty parameters
  (`test_jenkins_parameter_mapping_matches_the_configured_job_contract`);
- no enterprise Jenkins was triggered: the pilot never contacted a real CI system.

**Not verified:** a real Jenkinsfile's parameter contract, credentials, and build-status polling.

## 16. TestRail compatibility (Gate 14.15)

The reference repository's own mapper (`integrations/test_management/mapping.py`, imported read-only
with `PYTHONDONTWRITEBYTECODE=1`) was executed in its own virtualenv next to the platform's
`NodeIdCaseMapper` on the same inputs:

| Input | Reference mapper | Platform mapper | Match |
|---|---|---|---|
| `tests/test_c1001_login.py::test_login` | `C1001` | `C1001` | ✅ |
| `tests/test_x.py::test_c2002_flow` | `C2002` | `C2002` | ✅ |
| marker `testrail("C4242")` | `C4242` | `C4242` | ✅ |
| marker `case_id='c777'` | **`Cc777`** | `C777` | ❌ reference defect |
| explicit map `…::test_checkout_total → C9001` | `C9001` | `C9001` | ✅ |
| unmapped test | `None` | `None` | ✅ |

Equivalence holds on 5 of 6 cases; the single divergence is a normalisation bug in the *reference*
project (it prefixes `C` to an already-prefixed lowercase id, producing `Cc777`), which the platform
normalises to `C777`. One test → many cases and parameterised case mapping are supported through the
explicit `.qa-platform-cases.yaml` and the marker/docstring/function-name extraction.

Publishing remains **preview only**. Against the pilot run's two executions
(`tests/unit/test_pilot_controlled.py`, one PASSED / one FAILED) the platform produced:

```json
{"total_tests": 2, "mapped_tests": 0, "unmapped_tests": 2,
 "items": [{"test_name": "test_pilot_flaky_passes_on_retry", "mapped_testrail_status": "Passed", ...},
           {"test_name": "test_pilot_locator_regression", "mapped_testrail_status": "Failed",
            "comment": "… TimeoutError: Locator.wait_for: Timeout 30000ms exceeded …"}]}
```

and `POST /api/testrail/publish` with `confirm_publish=false` returned
`{"success": true, "published": false, "total_published": 0}` — no result was written to any
TestRail instance. Finding the preview crash (see §10) was a direct result of running it against
real executions rather than an empty run.
