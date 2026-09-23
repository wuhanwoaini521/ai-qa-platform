# AI QA Platform — Architecture Stabilization Audit (Phase 13.5.0)

Read-only audit of `apps/`, `packages/`, tests, CI and docs at commit `16ac4da` (baseline before Phase 13.5 changes).
Every finding below is reproducible from the referenced `path:line`. This document is the input to Gates
13.5.1 – 13.5.12 and defines what Phase 13.5 must change and why.

---

## 0. Baseline (measured, not estimated)

| Signal | Value |
|---|---|
| Python | 16,904 LOC / 151 files |
| Frontend | 10,851 LOC / 20 ts/tsx files |
| Backend shape | 25 routers (126 routes), 26 services, 19 repositories |
| Tests | 71 passed in 11.8 s (`uv run pytest`) |
| Lint | ruff check + ruff format --check (187 files) + eslint: clean |
| Typecheck | `tsc --noEmit`: clean |
| Frontend build | 1 JS chunk `index-*.js` 490.12 kB (gzip 123.48 kB) + 7.81 kB CSS |
| CI | `.github/workflows/ci.yml`: backend (SQLite only) + frontend jobs, green at HEAD |

### Baseline defects observed during measurement

| # | Defect | Evidence |
|---|---|---|
| B1 | Three test modules call `init_db()` against the **real** runtime DB, polluting `runtime/ai_qa_platform.db` and leaking rows between runs | `apps/api/tests/test_production_operations.py:13` (autouse), `test_identity_rbac_security.py:23`, `test_distributed_execution.py:29`, `:162` |
| B2 | Monaco is **not bundled** — `@monaco-editor/react` loads the editor from a public CDN at runtime, so the production bundle size is not representative and the Studio needs internet access | `apps/web/src/pages/AutomationStudioPage.tsx:2`, `apps/web/package.json` (no `monaco-editor` bundle config, no vite manual chunking) |
| B3 | `scripts/test` never builds the frontend; the build is only exercised in CI | `scripts/test:10-14` |

---

## 1. Largest files

### Frontend (top 10)

| File | Lines | Note |
|---|---|---|
| `apps/web/src/pages/AutomationStudioPage.tsx` | 2025 | 45 `useState`, 3 `useEffect`, 1 `useRef`, 24 API calls, 4 modals, zero child components |
| `apps/web/src/pages/RequirementsPage.tsx` | 1094 | 24 `useState`, 5 modals |
| `apps/web/src/types/index.ts` | 1063 | ~90 hand-written DTO interfaces |
| `apps/web/src/pages/TestCasesPage.tsx` | 914 | 17 `useState`, 1 field typed `any` (`:63`) |
| `apps/web/src/pages/RunsPage.tsx` | 840 | SSE ref + terminal ref |
| `apps/web/src/pages/FailuresPage.tsx` | 827 | 20 `useState`, 5 `alert()` error paths |
| `apps/web/src/pages/QualityPage.tsx` | 821 | |
| `apps/web/src/pages/SecurityPage.tsx` | 764 | |
| `apps/web/src/api/client.ts` | 596 | ~110 methods, 23 with no call site |
| `apps/web/src/App.tsx` | 182 | tab state machine + ad-hoc cross-page params |

### Python (top 10)

| File | Lines |
|---|---|
| `packages/project-model/project_model/models.py` | 1232 (single flat DTO module) |
| `apps/api/app/services/test_run_service.py` | 482 |
| `apps/api/app/persistence/models.py` | 455 |
| `apps/api/app/services/workspace_service.py` | 450 |
| `packages/qa-core/qa_core/ai/provider.py` | 448 |
| `packages/integrations/integrations/testrail_adapter.py` | 424 |
| `packages/integrations/integrations/github_adapter.py` | 376 |
| `packages/integrations/integrations/jenkins_runner.py` | 373 |
| `packages/qa-core/qa_core/orchestrator/orchestrator.py` | 323 |
| `apps/api/app/services/quality_intelligence_service.py` | 310 |

---

## 2. Layering: routers → services → repositories

Layering is directionally clean: **no repository imports a service**, **no package imports `apps/`**
(`project_model ← qa_core ← integrations ← apps` is acyclic). The problems are elsewhere.

### 2.1 Pass-through services

~128 public service methods; **23 are strict pass-throughs** (body == `return await repo.method(...)`,
no rule, authz, transaction, orchestration or validation):

| Service | Public methods | Strict pass-throughs |
|---|---|---|
| `job_queue_service.py` | 6 | 5 (`dispatch_next_job:35`, `complete_job:38`, `fail_job:41`, `cancel_job:46`, `list_jobs:55`) |
| `worker_service.py` | 6 | 5 (`register_worker:19`, `heartbeat:22`, `list_workers:29`, `get_worker:32`, `delete_worker:35`) |
| `team_service.py` | 7 | 4 (`get_team:19`, `list_teams:22`, `update_team:37`, `remove_member:66`) |
| `user_service.py` | 5 | 2 (`get_user:19`, `list_users:22`) |
| `jira_service.py` / `testrail_service.py` | 5 / 4 | 2 / 2 (adapter reads) |
| `ai_service`, `pr_service`, `release_service`, `runner_service` | 5/4/6/6 | 1 each |

A further ~20 methods are "mapping-only" wrappers (single repo call + `_to_dto`). `job_queue_service` and
`worker_service` are pure repository facades; `DashboardService` even reaches into a peer repository's
private session (`dashboard_service.py:28`, `RunHistoryRepository(lambda: run_repo.session)`).

### 2.2 Authorization: implemented, never enforced

- Exactly one auth mechanism exists: `Depends(get_current_user)` (`apps/api/app/api/auth.py:23-33`).
- Only **3 of 25 routers** use it (`auth.py`, `users.py`, `teams.py`). The other **22 routers / ~111 routes are unauthenticated**,
  including all writes (`projects`, `runs`, `failures/apply-repair`, `workers`, `jobs`, `releases`, `quality`, `workspaces/{id}/file`).
- `AuthService.check_permission` (`services/auth_service.py:143-145`) is **dead code**; `Permission`/`ROLE_PERMISSIONS`
  are only used to echo a permission list back at login (`auth_service.py:80-81`).
- `authenticate_token_or_key` **falls back to the seeded admin when no `Authorization` header is present**
  (`services/auth_service.py:107-112`), so even the guarded routers are open.
- Token verification swallows every exception (`auth_service.py:137-138`).
- Passwords and API keys are unsalted SHA-256 (`repositories/user_repo.py:19-20`, `repositories/api_key_repo.py:20-21`);
  `api_keys.key_hash` is indexed but **not unique**.

### 2.3 Import-time amplification

`app/api/__init__.py` imports all 25 routers and `app/services/__init__.py` imports all 25 services, so any
`from app.services.x import y` executes the whole graph — including `integrations.github_adapter`,
`integrations.jenkins_runner`, `integrations.jira_adapter`, `integrations.testrail_adapter` and
`qa_core.orchestrator`. `app/settings.py:44-46` performs `mkdir` at import; `api/artifacts.py:9`,
`api/auth.py:19-20`, `api/jobs.py:10`, `api/workers.py:9` build stateful singletons at import.

Positive finding: **no optional heavy SDK is imported anywhere** (no `openai`, `anthropic`, `boto3`,
`google.*`, `playwright`). Only `httpx` (qa-core, integrations) and stdlib `urllib` are pulled in.

### 2.4 Two coexisting transaction models

`get_db` (`persistence/database.py:26-32`) commits after the response; repositories constructed without it
(`api/flaky.py:16`, `api/runners.py:17`, `api/artifacts.py:9`, `api/jobs.py:10`, `api/workers.py:9`,
`api/audit.py:47`, `api/qa_assistant.py:10`) open **independent** sessions and commit inside `_exec`, so a later
failure cannot roll them back. Other routers pass `lambda: session` so their services share the request
transaction (`api/failures.py:28-29`, `api/ai.py:26`, `api/quality.py:31`).

### 2.5 Dead code / unused surface

| Symbol | Location | Status |
|---|---|---|
| `app/persistence/artifact_store.py` (`ArtifactStore`, `LocalArtifactStore`) | — | never imported; `ArtifactStorageService` writes bytes directly |
| `app/services/secret_store.py` (`SecretStore`) | — | production-dead; only its own test imports it |
| `AuthService.check_permission` | `auth_service.py:143` | never called |
| `MetricsService.increment_counter` | `metrics_service.py:36-37` | never called, counter never read |
| `JobRepository.get_by_id` / `list_all` | `job_repo.py:59/90` | never called |
| `runner_backends.LocalProcessRunnerBackend` / `DockerRunnerBackend` / `DistributedWorkerBackend` / `RunnerBackendProtocol` | `services/runner_backends.py:8-70` | test-only |
| `integrations/contracts.py` (all 6 symbols) | — | dead, superseded by adapter-specific protocols |
| `qa_core/explorer/` (whole subpackage) | `engine.py:17` | no consumer |
| `qa_core/contracts.py` protocols (`TestRunner`, `FailureAnalyzer`, `TestAuthor`, `LocatorHealer`, `BrowserExplorer`, `QAOrchestrator`) | `contracts.py:98-133` | implemented only by fakes |
| `qa_core/author/`, `qa_core/knowledge/` | — | reachable only via `ProductionQAOrchestrator.author_test`, which no app code calls |
| `TEST_AUTHOR_PROMPT`, `TestAuthorResponse`, `AIInvocationRecord`, `TestSuiteResult`, `GitRepositoryProtocol`, `AuthoringRequest/Result` (contracts copy) | — | defined, never used |
| 23 `api.*` methods in `apps/web/src/api/client.ts` | — | no call site |
| `apps/worker/worker/jobs.py` (`InMemoryJobQueue`), `executor.py` (`JobExecutor`) | — | production worker never uses them |

### 2.6 Fake-only production paths

| Fake | Reached from production when… | Evidence |
|---|---|---|
| `FakeAIProvider` | no `QA_AI_PROVIDER` / no key configured (default provider) | `qa_core/ai/registry.py:53`, `:47` |
| `FallbackAIProvider` | real provider errors | `qa_core/ai/provider.py:396` |
| `FakePullRequestAdapter` | no `GITHUB_TOKEN` | `integrations/github_adapter.py:41`, `pr_service.py:57` |
| `GitHubPullRequestAdapter.create_pull_request` | no token → silently returns a *simulated* created PR | `github_adapter.py:246-248` |
| `FakeJiraAdapter` / `FakeTestRailAdapter` | no Jira/TestRail env | `jira_service.py:41`, `testrail_service.py:38` |
| `FakeQAOrchestrator` | always — the production worker daemon has no real orchestrator | `apps/worker/worker/daemon.py:13,50` |
| `LocalRunnerBackend` (stub behaviour: `trigger` always `RUNNING`, `stop` always `True`) | `qa_core/execution/runner_backend.py:57-77` | holds a `PytestRunner` but never calls it |

`apps/worker` is a **second, disconnected distributed-execution stack**: it polls nothing, shares no code with
`JobQueueService`/`WorkerService`, and executes through `FakeQAOrchestrator`. The API-side job queue
(`/api/jobs`) and the container worker never meet.

### 2.7 Proven runtime defects

| # | Defect | Evidence | Impact |
|---|---|---|---|
| D1 | `AutomationBindingORM` has `nodeid`/`file_path`; impact analysis reads `b.test_file_path`/`b.test_node_id` | `services/quality_intelligence_service.py:269-271` vs `persistence/models.py:159-160` | `POST /api/quality/impact` raises `AttributeError` → 500 whenever the project has ≥1 binding. The existing test passes only because its fixture has zero bindings (`tests/test_quality_and_releases.py`) |
| D2 | Metrics compare lowercase literals against uppercase enums | `services/metrics_service.py:59-65` vs `WorkerStatus` (`project_model/models.py:1136`), `JobStatus` (`:1170`) | `workers_online`, `workers_busy`, `jobs_queued/running/completed/failed` are permanently `0` in `/metrics` and `/health`; alerts built on them can never fire |
| D3 | Frontend/backend `AutomationBinding` contract diverges 3 ways | FE type `apps/web/src/types/index.ts:115-133` (`framework_type`, `test_file_path`, `test_node_id`, `AutomationStatus`) ; FE usage `TestCasesPage.tsx:234-239,255-259` ; API schema `project_model/models.py:250-267` (`workspace_id`, `nodeid`, `file_path`, `AutomationBindingStatus`) ; endpoint `api/test_cases.py:79-82` | Saving a binding from the UI sends `{test_file_path, test_node_id, status}` with **no `workspace_id`/`nodeid`** → 400 "Mismatched test_case_id"/422; the binding card renders `binding.test_file_path` which the API never returns → blank file/nodeid and an unusable Run button |
| D4 | `get_workspace_dir` prefix check is not path-boundary-safe | `services/workspace_service.py:41-46` (`str(target).startswith(str(self.base_dir))`) | `workspace_id="../workspaces-evil"` resolves to a **sibling directory** whose name starts with the base path → traversal escape (the file-level guard at `:48-55` is correct; this one is not) |
| D5 | `login` in the web client hardcodes the password | `apps/web/src/api/client.ts:470` (`password='password123'`) | the UI's login is a stub, not a real credential flow |
| D6 | `runs` SSE + metrics are in-process singletons | `services/test_run_service.py:37-58`, `metrics_service.py:14-18` | multi-worker deployments lose SSE fan-out and per-process counters |
| D7 | Artifact storage path diverges from the health-checked path | `services/artifact_storage_service.py:17` (`/tmp/ai_qa_artifacts`) vs `settings.artifact_storage_dir` checked at `api/health.py:20` | `/health/ready` can report writable while artifacts go elsewhere; `storage_path` stores an absolute host path |

---

## 3. Domain model duplication

`project_model` is the single Pydantic source for API DTOs; the ORM re-declares the same fields and each
service re-maps them by hand (`_to_dto`). Most of that is a legitimate serialization boundary. The
**genuine defects** are:

| Duplicate | Definitions | Verdict |
|---|---|---|
| `TestDesignSuggestion` | `project_model/models.py:488` **and** `qa_core/ai/models.py:72` | true duplicate, same name, bridged by hand-written field copies (`ai_service.py:4-12`, `orchestrator.py:66-92`) |
| `TestCaseGenerationItem` | `project_model/models.py:495` **and** `qa_core/ai/models.py:83` | true duplicate |
| `RequirementAnalysisDTO` / `RequirementAnalysisResponse` | `project_model/models.py:481` / `qa_core/ai/models.py:65` | identical shape, two names |
| `TestExecutionStatus` vs `RunStatus` | `qa_core/execution/models.py:13` / `project_model/models.py:55` | two enums, two value sets; the web adds a third (`types/index.ts:282`) |
| `AIProviderStatus` vs `ProviderHealth` | `project_model/models.py:441` / `qa_core/ai/models.py:14` | two shapes for one concept |
| `AuthoringRequest/Result` | `qa_core/contracts.py:55-68` / `qa_core/author/models.py:14-25` | divergent field sets (`existing_page_objects` vs `workspace_knowledge`) |
| Inline router DTOs | `ClaimJobRequest`/`CompleteJobRequest`/`FailJobRequest` (`api/jobs.py:13-23`), `AddMemberRequest` (`api/teams.py:14-16`) | belong in `project_model` next to `ExecutionJobCreate`/`TeamMember` |
| `AutomationBinding` | 3 layers, **inconsistent fields** | see D3 — this one is a live bug, not a boundary |
| `TestExecution.retry_count` | present in ORM (`persistence/models.py:227`) and web (`:291`), **missing** from the Pydantic DTO (`project_model/models.py:356-368`) | API silently drops a field the UI renders |
| `utc_now()` | `persistence/models.py:12`, `apps/worker/worker/jobs.py:11`, `integrations/github_adapter.py:24` | three copies |

---

## 4. Database assumptions (SQLite vs PostgreSQL)

| # | Assumption | Where | Divergence |
|---|---|---|---|
| P1 | SQLite ignores `ON DELETE CASCADE` because `PRAGMA foreign_keys` is never enabled | `persistence/database.py:12-14` (only `check_same_thread`) | Production (PostgreSQL) cascades; tests (SQLite) leave orphans / raise. Every FK-cascade behavior is untested |
| P2 | Timestamps are stored timezone-aware | `DateTime(timezone=True)` on every model, `utc_now()` defaults | SQLite returns **naive** datetimes, PostgreSQL returns **aware** ones. Worked around in exactly one place (`worker_repo.py:113-114`); `dashboard_service.py:38-41` compares `.date()` of a stored value against `now(timezone.utc)`, and API responses differ in tz-awareness per backend |
| P3 | NULL ordering is irrelevant | `order_by(TestExecutionORM.started_at)` ASC with a nullable column (`test_run_repo.py:221-224`); `desc(started_at)` (`run_history_repo.py:55`) | SQLite sorts NULLs first, PostgreSQL last → different execution ordering per backend |
| P4 | `String(36)` headroom | `team_repo.py:18`, `user_repo.py:23` store full 36-char UUIDs | enforced on PostgreSQL, ignored on SQLite |
| P5 | JSON is TEXT | `JsonList`/`JsonDict` → `TypeDecorator(impl=Text)` (`persistence/models.py:16-48`) | portable, but NULL and empty are indistinguishable, and `repair_proposal` (nullable) always reads back `{}` |
| P6 | No migrations | `init_db` = `Base.metadata.create_all` (`database.py:34-37`) | schema changes never apply to an existing database on either backend |
| P7 | `workspaces.project_id` is unique | `workspace_repo.get_by_project_id` uses `scalar_one_or_none` (`:16-18`) but no constraint exists | duplicate workspaces → `MultipleResultsFound` at runtime |
| P8 | Client-side column defaults are sufficient | `default=list`/`default=dict`/`default=utc_now` on all models | raw SQL inserts bypass them → NULL, which `JsonList` then reads back as `[]` |
| P9 | Pool sizing is safe | PostgreSQL `pool_size=20` (`database.py:19`) with repos opening their own sessions per call | connection amplification under load |

---

## 5. Frontend state ownership & routing

### 5.1 State ownership today

- `App.tsx` owns `currentTab`, `projects`, `selectedProjectId`, `loadingProjects`, plus the ad-hoc cross-page
  params `studioTargetFile` (`App.tsx:25`) and `runsTargetId` (`:26`) which are **never cleared** — a later
  `onNavigateToRuns()` with no id re-uses a stale target.
- Every page owns its own list/detail/selection state; **no page defines a child component** (grep for
  `React.FC|function [A-Z]` returns only page exports); there is no context, store, `useMemo` or `useReducer`
  anywhere. `useRef` appears only in `RunsPage` (SSE/terminal) and `AutomationStudioPage` (editor).
- `AutomationStudioPage` holds 45 `useState`; 12+ of them are read/written by 2-4 panels (tabs/`activeTabPath`,
  `sidebarTab`, `diffResult`, `validationIssues`, `currentBranch`, `showDiffView`, `activePR`/`prChecks`,
  `saving`, `runningTest`/`lastRunResult`, `fileOpModal`, `assistantMessages`). Full panel map with line
  ranges: audit input `agent://WebAudit` §2.
- Dirty tracking has a real gap: `handleInsertSnippet` writes the Monaco buffer imperatively through
  `editorRef` (`AutomationStudioPage.tsx:666-680`) and only the fallback branch calls `handleUpdateContent`,
  so `isDirty` can be stale.
- `api.getGitStatus` is fetched and discarded (`AutomationStudioPage.tsx:227`).

### 5.2 Duplication

| Duplication | Evidence |
|---|---|
| 4 competing modal shell conventions for identical markup; `modal-card`, `modal-content`, `modal-backdrop`, `modal` are **not defined in CSS** | ProjectsPage:153, RunsPage:579/693, TestCasesPage:697/773, AutomationStudioPage:804/880/941/992, QualityPage:612/681, RequirementsPage:561/628/689/761/861/957, FlakyPage:317 |
| 3 status-badge factories | `DashboardPage.tsx:50-60`, `RunsPage.tsx:233-252`, `FailuresPage.tsx:250-279` |
| Execution-history UI implemented twice on the same DTO | `FlakyPage.tsx:316-459` vs `TestCasesPage.tsx:592-693` |
| Fetch-on-mount effect template copy-pasted 11× | Dashboard:30, Requirements:91, TestCases:80, Runs:63, Failures:78, Flaky:35, Quality:59, Security:57, Workers:41, App:28, Header:20 |
| Date formatting inlined at 8 sites; two spinner class names, neither defined in CSS (`spin`/`spinning`) | Requirements:402, Projects:117, Failures:643, Security:322/379/423; Flaky:100, Quality:170, Workers:169 |
| Loading/empty markup string-repeated ≥12× | Dashboard:47, Failures:311, Flaky:207, Projects:71, Requirements:365, Runs:301, TestCases:330, Security:341… |

### 5.3 Routing

- Navigation is a `NavTab` union (`components/Navigation.tsx:21-32`) mutated by `onClick` on `<div>`s
  (`Navigation.tsx:63-72`). No URL is ever produced or read; refresh always resets to Dashboard; Back leaves the app.
- Entity navigation is in-memory only: `TestCasesPage:515` (test case → studio file), `TestCasesPage:281` and
  `FailuresPage:206` (deferred 1.2 s `setTimeout` navigations with no cleanup), `AutomationStudioPage:604/1887`,
  `FlakyPage:422`, `QualityPage:503` (**no id — target lost**), `RunsPage:494` (`onNavigateToFailures()` without an id
  although the prop accepts one).
- Deep-link hazards to resolve during migration: `RunsPage.initialRunId` is only honoured if the run appears in the
  first page of results (`RunsPage.tsx:72-79`); project selection lives in `Header.tsx:56`/`App.tsx:20` with no URL;
  the Studio hides the global Header and adds `full-bleed` layout by tab id (`App.tsx:77-91`).

### 5.4 Error / loading handling

No `ErrorBoundary` (`main.tsx:5-9`), no page-level error state, no retry control anywhere. Failures surface as
`console.error` (≈40 sites) or blocking `alert()` (18 sites: TestCases ×3, AutomationStudio ×8, Runs ×2,
Failures ×5). Missing empty states in QualityPage tables and the Studio's problems/PR panes.

### 5.5 Dead frontend surface

Dead props: `DashboardPage.onOpenCreateProject:21`, `RequirementsPage.onNavigateToStudio:34`, `Header.actions:13`.
23 unused `api.*` methods; 4 duplicate method pairs (`getRunners`/`getRunnerProfiles`, `checkRunnerHealth`/`getRunnerHealth`,
`getSemanticLocatorReview`/`reviewSemanticRepair`, `getExternalArtifacts` as a `getTestRun` wrapper).
Unused dependency: `clsx` (never imported).

---

## 6. Unused / misdeclared dependencies

| Dependency | Declared in | Reality |
|---|---|---|
| `clsx` | `apps/web/package.json` | never imported → remove |
| `project-model` | `apps/worker/pyproject.toml` | worker source never imports it → remove |
| `asyncpg` | `apps/api/pyproject.toml` | never imported directly (correct for a driver) but **never exercised by any test or CI job** |
| `httpx` | declared 3× (`qa-core`, `integrations`, worker) | used; fine under a uv workspace |
| `integrations` | **not declared** by `apps/api/pyproject.toml` | imported at runtime (`workspace_service.py:10`, `jira_service.py:4`, `testrail_service.py:5`, `pr_service.py:5`, `test_run_service.py:8`) — works only through root `pythonpath` |
| `lucide-react` | web | used |
| `@monaco-editor/react` | web | used, but pulls the editor from a CDN (B2) |

---

## 7. Test coverage gaps

71 tests: API 40, qa-core 18, integrations 12, worker 1. All database tests run on SQLite only.

| Risk area | Coverage |
|---|---|
| RBAC **denial** paths | **none** — zero `403/401` assertions; the enforcement itself is missing (§2.2) |
| Failure repair surface (7 of 8 endpoints: diagnose, diagnose-ai, repair-proposal, semantic-review, recurrence, apply-repair) | untested — the platform's central human-in-the-loop safety feature |
| SSE lifecycle (`GET /api/runs/{id}/events`) | untested |
| Job claim/complete/fail/cancel, worker get/delete, users/teams update+delete | untested |
| Workspace isolation, symlink escape | untested (only `..` read/write vectors: `test_workspace_security.py`) |
| Subprocess/argument injection (collect/bootstrap/validate) | untested |
| Runner recovery: worker death mid-job, requeue, heartbeat reaper | untested |
| Git: branch switch endpoint, push without remote (simulated success), auth failures | partially |
| External adapters live paths (GitHub/Jira/TestRail/Jenkins) | fakes/dry-run only |
| PostgreSQL | **zero** |
| Worker daemon against the real API job queue | none (the worker is tested against fakes only) |

Hygiene: 3 modules write to the real runtime DB (B1); `test_distributed_execution.py:121-133` asserts literal
command strings; `test_health.py:10` accepts 3 equivalent statuses; `test_workspace_security.py:35` accepts
`200|400|404`; fixed `/tmp` paths are never cleaned up; no markers, so everything runs in one CI job.

CI gaps: no PostgreSQL service, no marker lanes, no security suite, no coverage, no e2e, no Docker build check,
no `scripts/prod_smoke_test.sh` invocation, Python 3.11 (the declared floor) never validated.

---

## 8. Roadmap & documentation safety

Platform invariant (stated in `docs/PRODUCTION_AI.md:7` and `docs/ARCHITECTURE.md:55-56`):
**AI never decides PASS/FAIL, and AI never mutates code without explicit human approval.**

Violations / blurring to fix in Gate 13.5.9:

| Location | Text | Problem |
|---|---|---|
| `docs/ROADMAP.md:10` | "Self-Healing Locator **Auto-Apply** Mode … auto-apply for locator repairs … **auto-created git PR**" | promises unattended code mutation gated only by a confidence score |
| `docs/ROADMAP.md:19` | "Autonomous Regression **Oracle**: Deep **reinforcement learning** agent …" | names an autonomous oracle/RL agent; breaks the deterministic-oracle boundary |
| `docs/PLATFORM_WORKFLOW.md:3`, `:69` | "self-healed test execution", "Self-Healing" | blurring |
| `docs/QA_CORE.md:12-14` | "LocatorHealer — Broken selector self-healing", "BrowserExplorer — Autonomous UI exploration" | blurring |
| `docs/LEGACY_QA_FRAMEWORK_MIGRATION.md:15` | "Port autonomous browser agent loop" | blurring |
| `docs/QUALITY_INTELLIGENCE.md:80` | recommended action "apply AI locator healing" | implies automatic application |

Doc drift also found (fix opportunistically): `docs/QUALITY_INTELLIGENCE.md:88,107,159` document
`/api/quality/{project_id}/coverage`, `…/risks`, `/api/releases/{id}/gate` while the routes are
`/api/quality/coverage?project_id=`, `/api/quality/risk-matrix`, `/api/releases/{id}/gate-evaluate`;
`README.md` links `docs/JIRA_TESTRAIL.md` and `docs/GITHUB_WORKFLOW.md` which do not exist (actual names:
`JIRA_INTEGRATION.md`, `GITHUB_INTEGRATION.md`); `README.md:135` and `docs/AUDIT_LOG.md` promise S3/MinIO
artifact storage while `ArtifactStorageService` is local-filesystem only (and `storage_path` is an absolute host path).

---

## 9. Remediation plan (mapped to gates)

| Gate | Action | Rationale |
|---|---|---|
| 13.5.1 | Split `AutomationStudioPage` into `features/automation-studio/{components,hooks,types}`; extract shared modal/status/loading primitives; split `RequirementsPage` and `TestCasesPage` along their existing master/detail/modal regions | 2025/1094/914-line components with 45/24/17 state cells cannot be reviewed or unit-tested |
| 13.5.2 | Replace `NavTab` with `react-router` routes for the required paths; move `studioTargetFile`/`runsTargetId`/selection into params; keep the Studio's full-bleed layout as a route layout | restores deep links, refresh, back/forward; kills stale-param bugs |
| 13.5.3 | Run the suite on PostgreSQL in CI (service container + `AI_QA_TEST_DATABASE_URL`); fix P1–P4 in code, not in tests | production is PostgreSQL; SQLite currently hides FK, tz and NULL-ordering differences |
| 13.5.4 | Add `unit`/`integration`/`postgres`/`security` markers; repair B1; add denial-path, workspace-escape, repair-surface and SSE tests | 71 tests under-cover a 126-route platform |
| 13.5.5 | Remove dead modules and unused members (§2.5); collapse the pure pass-through services into their repositories **or** give them the missing authorization/audit responsibility (§2.2); delete the duplicated DTOs (§3) | remove weight without a mass rewrite |
| 13.5.6 | Align `AutomationBinding`, `TestExecution.retry_count` and the AI DTO families; fix D1/D3 | proven cross-layer bugs |
| 13.5.7 | Keep `api/client.ts` as the only network layer; delete the 23 dead methods; type the one `any`; remove `clsx` | single, typed network boundary |
| 13.5.8 | Add `ErrorBoundary` + per-page error/empty/retry states; replace blocking `alert()` with in-page errors; fix D5 (real login) | a platform that renders a blank screen on API failure is not operable |
| 13.5.9 | Rewrite `ROADMAP.md:10,19` into assisted/deterministic/human-approved semantics; normalize "self-healing"/"autonomous"; fix doc drift | the safety invariant must not be contradicted by the roadmap |
| 13.5.10 | Drop unused deps (`clsx`, worker's `project-model`), declare `integrations` in the API package, mark `asyncpg` as the PostgreSQL driver | declared graph must match the real graph |
| 13.5.11 | Verify the API starts with no provider/integration credentials; make B2 (Monaco CDN) explicit | startup must not depend on optional configuration |
| 13.5.12 | Record bundle size; lazy-load the Studio route; give Monaco a local/vendored chunk | keep the first paint small and remove the CDN runtime dependency |

Out of scope for Phase 13.5 (deliberately deferred): SSR/wasm Monaco alternatives, migrations/Alembic,
Redis backplane for SSE/metrics (D6), multi-tenant routing. These are recorded as known limitations in
`docs/RELEASE_READINESS.md` rather than silently left in the code.
