# Pilot Gap Analysis — what a real project exposed

The pilot (`docs/PHASE_14_PILOT_REPORT.md`) ran a real pytest + Playwright repository through the
platform. This document records what that exposed, what was fixed, and what is still open — including
the things the platform still cannot do. Nothing here is aspirational: every "fixed" row has a test or
a recorded run, and every "open" row names the concrete limitation.

---

## 1. Fixed during the pilot

| # | Gap | Impact before | Fix | Evidence |
|---|---|---|---|---|
| G1 | `calculate_risk_matrix` read `FlakyScore.flip_rate`, which does not exist | `GET /api/quality/risk-matrix` returned HTTP 500 for any project with flaky tests | use `alternation_rate` | 500 → 676 ms at 100k executions |
| G2 | `list_flaky_tests` ran one query per distinct test | endpoint cost grew with (tests × executions); 5.5 s dashboard at 20 projects | single window-function query, portable across SQLite/PostgreSQL | `test_flaky_and_history`, PostgreSQL lane |
| G3 | Dashboard loaded whole tables to count them and to show five rows | 5.5 s at 10k test cases | `count()` queries + `limit=5` for the rendered rows | 5.5 s → 0.9 s |
| G4 | Test identity/selection would have inherited the frontend/backend drift | binding save and every "run test" action failed in the UI | payloads aligned to the API schema; verified in a browser | `docs/PHASE_14_PILOT_REPORT.md` §13 |
| G5 | Marker selection collected *all* tests and then filtered at run time | selection did not match what executed | markers applied to collection as well as to the run | `test_onboarding_flow…`, marker test |
| G6 | Rerun accounting depended on parsing `RERUN` lines | the reference project's logging splits pytest's progress lines, so reruns were lost | platform-written pytest plugin records one JSON line per attempt | 2 logical / 4 physical / 2 reruns |
| G7 | xdist progress lines were not parsed | worker-parallel runs reported zero tests | `[gwN] [ nn%] OUTCOME nodeid` supported | unit test + `-n 2` pilot run |
| G8 | Parametrised node ids (`test_x[chromium]`) could not be inspected by the safety policy | browser tests were reported as "source could not be inspected" instead of a concrete reason | node id parsing keeps the class and strips the parameter | `test_safety_policy_inspects_parameterised_nodeids` |
| G9 | Safety policy flagged any file merely mentioning `https://` | 18 of the reference project's offline unit tests were refused (false positives) | AST-based analysis: fixtures, receiver calls, URL arguments, unsafe markers | 69/69 offline tests execute; live tests still refused |
| G10 | A crashed run stayed `RUNNING` forever | dashboards and pass rates permanently wrong | startup recovery + `POST /api/runs/recover-stale`, closing abandoned runs as `CANCELLED` (never a fabricated verdict) | `test_abandoned_runs_are_recovered…` |
| G11 | Node ids and markers reached the pytest command line unvalidated | a test selection could inject CLI flags | node ids/markers validated (shape, traversal segments, marker syntax) | 7 security cases |
| G12 | Worker registration/heartbeat payloads did not match the API schema | a distributed worker could never register | payloads fixed (`hostname`, `browsers`, `ONLINE/BUSY/OFFLINE`) + real load reporting | worker tests |
| G13 | The distributed job queue had no producer | Phase 12's "distributed execution" was unreachable in practice | `runner_type`-agnostic onboarding path executes imported projects; the queue gap is documented below | see §2 O1 |

## 1b. Fixed after the Phase 14 review (second pass)

| # | Gap | Impact before | Fix | Evidence |
|---|---|---|---|---|
| G14 | `subprocess.Popen`, `os.spawn*`, `socket.create_connection`, driver imports, host-file access and browser access through a helper/fixture were all classified **safe** | the safety policy's contract ("anything that touches the outside world is refused") did not hold for the most common evasions | case-insensitive call matching, browser-action names refused whatever the receiver, driver-module imports, socket calls, and escaping file paths | `test_safety_policy_refuses_the_evasions_a_real_project_can_use` (9 cases) |
| G15 | an absolute node id made the platform inspect and execute a host file outside the workspace | `AUTOMATION_EDIT` could execute any `test_*.py` on the API host | absolute paths rejected in validation; the policy refuses files outside the root | `test_absolute_node_ids_cannot_reach_host_files` (2 cases) |
| G16 | `extra_args` put arbitrary pytest flags on the command line at `automation:edit` privilege | `--junitxml`, `-c`, `--rootdir`, `-p` all reached the project process | the raw passthrough was removed; only named `n_workers`/`reruns` remain | `test_runner_options_are_named_not_raw_flags` |
| G17 | skipped and xfailed tests were recorded as `ERROR` with fabricated failure records and a diagnosis | inflated failure counts and pointless repair work for every skipped test | skip/xfail/xpass map to their real statuses; only genuine failures create records | `test_report_log_maps_skips_and_xfails_without_fabricating_failures` |
| G18 | the flaky query partitioned by node id only | a project's flaky tests disappeared when another project used the same node id more recently | partition by (project, node) + explicit newest-first ordering | `test_flaky_and_history`, PostgreSQL lane |
| G19 | the report log lived inside the workspace | the project under test could rewrite its own verdicts | the log lives in a platform directory outside the workspace and is cross-checked against pytest's summary | `QAProjectRunner(artifacts_dir=…)` + cross-check in `run()` |
| G20 | stale-run recovery used creation time and included Jenkins runs | a long-queued or CI-backed run could be cancelled while still running | staleness measured from `started_at`; Jenkins runs excluded | `test_abandoned_runs_are_recovered_and_never_stay_running` |
| G21 | the Runs page consumed SSE event names the server never publishes | live execution updates never applied | client handles the published event types | `RunsPage.tsx` |

## 1c. Fixed after the first pilot walk-through

| # | Gap | Impact before | Fix | Evidence |
|---|---|---|---|---|
| G22 | an imported project was registered with a workspace path (`workspaces/imports/<slug>`) that no other component derives from a project id | opening the Studio for an imported project showed an **empty** workspace, offered to scaffold over it, and a run started from the UI executed that scaffold instead of the imported tests; clicking Run on the scaffold then failed with `ModuleNotFoundError: No module named 'playwright'` because the platform's own interpreter was used | the import now targets `<workspace base>/<project id>`, the invariant every file/git/run endpoint already relied on; the stray scaffold and the parallel `imports/` layout were removed | `test_imported_workspace_is_the_one_the_studio_and_file_apis_address`; verified over HTTP: the file API returns the imported tree and a single case runs from the project's own virtualenv |
| G23 | a stray `pytest` invocation from the repository root collected generated workspaces under `runtime/` | the platform's own suite failed on third-party template files (`pages/login_page.py` importing playwright) | `norecursedirs` excludes `runtime/` (and caches/dist), so `pytest .` collects only the platform suite | `pytest . --collect-only -q` → 179 tests |

## 2. Still open (known limitations)

| # | Limitation | Why it matters | Recommended next step |
|---|---|---|---|
| O1 | **The distributed job queue still has no producer.** `JobQueueService.enqueue_job` has no caller: runs execute in the API process (`IMPORTED_PYTEST` / `LOCAL`) or through Jenkins, while `apps/worker` polls `/api/jobs/claim` and receives nothing | the "Distributed Execution Grid" is not exercised end to end; a worker container contributes no capacity | enqueue a job when a run is triggered with `runner_type=DISTRIBUTED`, and have the worker report per-test results back into the run |
| O2 | **`runner_type=DOCKER` is not implemented** | the runner profile accepts a type it cannot execute | implement or reject the type at the API boundary |
| O3 | **Object storage (S3/MinIO) is not implemented**; artifacts are local files and `stored_artifacts.storage_path` stores an absolute host path | multi-host deployments share no artifacts | implement an S3 backend or drop the `S3` storage type |
| O4 | **`SecretStore` is not wired into the adapters**; integration credentials come from environment variables | no central rotation, and the docs used to imply otherwise (now corrected) | wire `SecretStore` (or remove it) and document the rotation story |
| O5 | **No schema migrations** (`create_all` only) | a column change never reaches an existing database | adopt Alembic before the first production upgrade |
| O6 | **SSE and metrics are per-process** | multi-worker deployments lose stream fan-out and counters | Redis/backplane, or pin the deployment to one API instance and say so |
| O7 | **Run list payload ≈800 KB for 50 runs** because executions are eager-loaded | slow first paint on the Runs page | add a list projection without executions; fetch executions on the detail view |
| O8 | **Monaco is loaded from a public CDN** (`@monaco-editor/react` default loader) | the Studio needs internet access; the bundle size is not representative | vendor Monaco (and its workers) into the build |
| O9 | **AI output is only as grounded as the validator it passes** | a plausible-but-wrong test can still be adopted by a human | wire `GroundingValidator` into the authoring endpoint as a hard gate and surface violations in the UI |
| O10 | **Flaky ↔ case-id mapping is by node id only for this repository** | the reference project's C-ids live in its integration layer, not on the tests | adopt `.qa-platform-cases.yaml` for repositories without inline case ids |
| O11 | **Jenkins/TestRail/GitHub writes remain preview/dry-run** in every environment available here | no live, enterprise-verified write path | validate against real instances before claiming production proof |
| O12 | **Duplicated AI DTOs** (`project_model` vs `qa_core/ai/models.py`) remain, bridged by hand | two shapes can drift | collapse onto the shared package (out of Phase 13.5 scope) |

## 3. Reference-project findings (not platform defects)

| Finding | Detail |
|---|---|
| `test_worker_id_and_retry_index_resolution` fails under `-n 2` | asserts the worker id is `master`/`none`; under xdist it is `gw0`. The platform reported it honestly as a failure rather than hiding it |
| The repository's `smoke` marker selects live tests | the reason the platform never treats marker names as evidence of safety |
| CI is `workflow_dispatch`-only | the repository deliberately does not run its UI tests automatically; the pilot respected that by only executing the offline unit layer |

## 4. What the pilot did **not** prove

- No live Jira, TestRail, GitHub or Jenkins write was performed (no credentials were used): those
  integrations remain *preview/dry-run verified only*.
- No OIDC/SSO provider, multi-tenancy or SSO flow was exercised.
- Browser-driven Playwright execution was never performed on this machine: the reference project's own
  audit notes that prebuilt Chromium binaries are not installable here, so all UI tests were refused by
  policy rather than executed. The platform's browser execution path is therefore verified only
  through the local runner's contract, not with a real browser.
