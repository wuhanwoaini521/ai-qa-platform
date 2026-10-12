# AI QA Platform V2 — Live Product Audit

**Date:** 2026-10-12
**Target:** `http://127.0.0.1:5173` with API `http://127.0.0.1:8000`
**Branch:** `agent/qa-platform-v2-overhaul` (created from `a0b4976`)
**Baseline:** dirty worktree preserved; no application source edited during this observation pass.

## Product goal and golden journey

The product's core value is the traceable QA lifecycle: project → requirement and acceptance criteria → AI/Jev analysis and scenario design → test cases and automation binding → real test execution → per-case evidence and failure diagnosis → reviewed repair and verification.

Observed a real browser session on the running local product. The current local database is populated (26 projects, including four indistinguishable `Reference QA (playwright-test)` records and benchmark fixtures), so the initial audit did not assume an empty database. To protect all existing project data, created one additive, isolated sandbox through the product UI:

- Project: `V2 Overhaul Sandbox 2026-10-12` (`proj_ec58fd0e508e`)
- Requirement: `Quickstart account and cart lifecycle` (`req_50b5366b20f3`)
- One scenario-derived test case adopted so far: `Invalid credentials are rejected without a session`
- The project uses the local quickstart scaffold; no external repository or production system was configured.
- The case was bound to `tests/test_login.py::test_login_invalid_password` and executed as `run_f99148bf55de`: the real TestRun status is `PASSED`, 1/1 case result persisted, 0 failed. The completed AI analysis task remains separate from this TestRun.

The requirement-analysis workflow completed with the configured real providers: `openai-compatible / deepseek-flash` (6.6s) and Jev `jev-1.13.0` (two successful decisions, 0.5s each; confidence 0.98 and 0.97). The persisted analysis reported 3 risks and 4 scenarios. No fallback was reported. This is an observed positive path, not proof that every AI/Jev workflow works.

## Route / task coverage

| Area | User goal / action observed | Outcome and evidence | Remaining coverage |
|---|---|---|---|
| Dashboard `/` | orient to pending work, metrics, recent runs | initial capture showed skeletons at 800ms; content was visible by the 3s capture. Browser resource timing: `GET /api/dashboard/stats` 1.48s / 126,750 bytes, `GET /api/tasks` 141ms; see screenshots | slow dashboard stats request and metric scope/provenance remain unoptimized/unverified |
| Projects `/projects` | find/open/create a project | duplicate records now carry stable ID suffixes; project table has responsive horizontal scroll, keyboard navigation and a mobile swipe hint; additive sandbox creation worked | no search/filter behavior added |
| Workspace — requirement | inspect criteria; create and analyze requirement | created requirement in sandbox; AI and Jev decisions succeeded; 4 scenario drafts shown | analysis/ambiguity views and persistence after a clean reload |
| Workspace — cases | adopt scenario into a case | one scenario adopted successfully; requirement links and intent rendered | adopt remaining cases, select/empty cases, automation binding |
| Workspace — automation | inspect code editor, choose a bound case, open run controls | Python language service remains unavailable: the active Python environment lacks `basedpyright` and `nodejs_wheel`; see ISSUE-002. Bound case ran successfully in the isolated sandbox. | restore/verify the Python language service in a compatible dependency environment |
| Workspace — discovery | inspect Quality Discovery form and existing result | current historical external-site run is `BLOCKED`; no new discovery run was started | local-only discovery in sandbox; no external site was contacted |
| Runs `/runs` | inspect a failed run, per-case results and failure link | existing `run_1a8bf6d5a021` shows 8 results, 7 passed/1 failed; new sandbox `run_f99148bf55de` shows 1/1 passed with its saved case result | retry and verified failure repair; existing Golden Demo TC-002 mismatch remains unchanged |
| Failure detail | inspect AI diagnosis and repair affordance | real-provider diagnosis and evidence shown; repair remained un-applied; evidence package reports missing screenshot/trace/DOM | Jev-backed repair proposal and human approval/retry flow |
| Settings `/settings` | check effective AI/Jev config without changing it | UI reports AI and Jev enabled and `READY_CONFIGURED`; secrets remained masked | no settings or credentials changed |

## Findings (reproducible observations)

### ISSUE-001 — Project records with identical identity cannot be distinguished

- **Priority:** P2 — navigation and project-selection friction.
- **Evidence:** `screenshots/issue-001-project-duplicates.png`, `projects-initial-snapshot.txt`.
- **Reproduction:** open **项目管理**. Four consecutive rows have the exact same title `Reference QA (playwright-test)`, same imported repository path, same branch, and same creation date. The global project selector repeats that same label four times. Each row exposes the same actions and no project ID or differing metadata.
- **User impact:** a user cannot tell which project they are opening or selecting; accidental work in the wrong project is plausible. The issue is presentation/disambiguation; no project records were removed or edited.
- **Disposition:** fixed in presentation only. Duplicate names receive a stable, collision-expanded ID suffix across navigation, Studio, project lists, run/task/settings selectors, requirement/case forms, and Workspace context; unique names stay unchanged. No project records were edited or merged. Verified at 1440px, 768px and 390px; screenshots: `screenshots/project-names-after-desktop-final.png`, `screenshots/project-names-after-tablet-final.png`, `screenshots/project-names-after-mobile-final-light.png`.

### ISSUE-002 — Python language service is unavailable in Automation Studio

- **Priority:** P1 candidate — automation authoring assistance/diagnostics are unavailable; basic editor text remains visible.
- **Evidence:** `screenshots/issue-002-language-service-unavailable.png`, `automation-language-service-plain.png`.
- **Reproduction:** open the sandbox or Golden Demo Automation stage and select a Python test file. The editor loads, but the status reads `Python 语言服务不可用`; validation remains `—` and workspace checks are not run.
- **Root cause:** `PythonLanguageService.start()` imports `basedpyright` and `nodejs_wheel.executable`; both modules are absent from the active Python 3.13 environment. `uv.lock` provides the Node wheel for macOS 13+, while this host is macOS 12.7.6. A system Node 24.21.0 exists, but `basedpyright` does not.
- **Disposition:** unresolved environment blocker. `uv sync --locked --package api --no-install-project --dry-run` would add `basedpyright` and the Node wheel while removing shared `pytest-asyncio`, `ruff`, and `worker` packages from the active environment. Sync was not run; no environment dependencies were changed.
- **User impact:** Python diagnostics/navigation remain unavailable in this environment. Re-test after installing dependencies in a supported isolated environment; do not silently suppress the service failure or weaken diagnostics.

### ISSUE-003 — AI requirement-task completion briefly appears as a successful test run

- **Priority:** P1 candidate — incorrect execution status risks a false QA pass.
- **Evidence:** `v2-requirement-ai-analysis-result.png` records the successful requirement task; `v2-sandbox-runs-empty-after-analysis.png` shows zero test runs. The transient workspace status was captured in the browser output during the same flow (Run Control changed to `运行通过`, Results to `执行完成`) before navigating away; it returned to `就绪 / 尚无运行记录` after re-entering the Workspace.
- **Reproduction:** in the sandbox, run `让 QA Agent 分析需求`, wait for the analysis task to complete, close its task drawer, and observe the workspace stepper. It temporarily reports a passed run even though **运行** for this project reports `执行记录（0）` and no test run exists.
- **User impact:** it conflates successful AI analysis with successful test execution and can mislead a QA gate or user.
- **Disposition:** fixed. `workspaceRunDockState` prioritizes a real TestRun and maps task completion/failure/blocked/cancelled to distinct workflow labels; task completion explicitly says no TestRun was created. Regression tests cover task/run precedence and failure states. The empty `display_id` case now falls back to the case ID suffix. Verified in Chinese and English, dark theme, desktop/tablet/mobile; see `screenshots/task-complete-status-dock-final-dark-desktop.png`, `screenshots/task-complete-status-dock-final-dark-tablet.png`, and `screenshots/task-complete-status-dock-final-dark-mobile.png`.

### ISSUE-004 — Dashboard initially shows only skeletons for several seconds

- **Priority:** P2 candidate — delayed orientation on the landing page.
- **Evidence:** the original 800ms capture shows skeletons and the current retest shows content by 3s (`screenshots/dashboard-after-retest-800ms.png`, `screenshots/dashboard-after-retest-3s.png`). The page's `GET /api/dashboard/stats` took 1.48s and returned 126,750 bytes; `GET /api/tasks` took 141ms. No browser page errors were reported.
- **Reproduction:** navigate to **总览**, capture at 800ms and after the data settles.
- **User impact:** useful metrics/recent-run content is delayed while dashboard data loads. The slow stats request explains the 800ms skeleton, but the exact end-to-end delay beyond the request is not isolated.
- **Disposition:** not changed because the remaining render/data dependency has not been proven and the endpoint/data scope is outside the confirmed UI defects. Track API timing and consider progressive dashboard sections separately.

### ISSUE-005 — Project table columns are clipped on narrow screens

- **Priority:** P2 — project selection details/actions were not reliably reachable on a phone-width viewport.
- **Evidence:** initial project-page mobile screenshot; before the fix the table rendered at 762px inside a 344px card, with no responsive scroll region.
- **Disposition:** fixed by wrapping the table in an accessible horizontal-scroll region, supporting ArrowLeft/ArrowRight and Home/End, and adding a localized mobile swipe hint. At 390px the document remains 390px wide while the table scroll range is 418px. Verified keyboard scrolling moves 80px per arrow press and Home/End reach both ends.

## Validation summary

- Real sandbox AI/Jev analysis completed with the configured OpenAI-compatible `deepseek-flash` and Jev; no fallback was used. The separate real TestRun `run_f99148bf55de` passed 1/1 and persisted the case result.
- Frontend: `pnpm --filter @ai-qa/web test` — 137 passed; `lint`, `typecheck`, and `build` passed. Build retains the existing Monaco chunk-size warning (>500KB).
- Backend/workspace: `uv run --no-sync pytest -q` — 669 passed, 7 skipped; `uv run --no-sync ruff check .` and `ruff format --check .` passed. `AI_QA_TEST_DATABASE_URL` was not configured, so PostgreSQL-only coverage was skipped.
- Browser: real system Chrome via CDP (agent-browser's bundled Chrome cannot launch on this macOS host); project names/table at 1440/768/390, run dock at 1440/768/390 in dark mode, and both Chinese/English labels were checked. Axe reported 0 violations on Projects and Workspace; color-contrast checks were incomplete on some elements because of transparent/pseudo-element backgrounds. Manual computed color checks were above 4.5:1 for sampled text (Projects header 5.4:1; Workspace muted number 6.49:1, strong label 16.42:1, muted small text 8.37:1).
- Full screen-reader, Firefox/WebKit, Linux/Windows, PostgreSQL, and video checks were not completed. No video was recorded because `ffmpeg` is absent.

## Environment blockers and boundaries

- A new isolated `agent-browser` session could not launch Chrome: Chrome for Testing exited with `Symbol not found: (_kVTCompressionPropertyKey_ReferenceBufferCount)` in the local VideoToolbox framework. The existing authenticated session remained usable. Fresh-session verification is therefore incomplete.
- `agent-browser record start` is unavailable because `ffmpeg` is not installed. Screenshot evidence was captured instead; no video is claimed.
- No business project, AI setting, credential, existing test script, or existing run was modified by the exploration. Only the explicitly named V2 sandbox project, requirement, and one scenario-derived test case were added.
- Existing historical Quality Discovery data references `https://www.uniqlo.com.hk/`; it was viewed but not re-run or contacted.
