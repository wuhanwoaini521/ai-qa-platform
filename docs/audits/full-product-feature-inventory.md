# Full Product Feature Inventory

**Audit date:** 2026-10-11
**Repository:** `main` at `cdf954a`
**Scope:** Local authenticated application, pre-existing worktree changes plus the scoped mobile-navigation refinement, SQLite runtime, and browser-visible primary workflows. No production system was accessed.

## Platform and runtime

- **Frontend:** React, TypeScript and Vite; route composition is in `apps/web/src/app/routes.tsx`.
- **API:** FastAPI under `apps/api/app/api` and `apps/api/app/services`.
- **Worker:** distributed execution service in `apps/worker`; no Worker was started during this audit.
- **Persistence:** local SQLite. Readiness returned `ready`, with database and artifact storage `ok`; migration was at `0007_quality_discovery_version`.
- **Live services during review:** API `127.0.0.1:8000`, web `127.0.0.1:5173`; health, readiness and web root returned HTTP 200. These services were started for the audit and stopped afterward.
- **Provider configuration:** real AI (`openai-compatible / deepseek-flash`) and Jev (`jev-1.13.0`) were enabled and tested without displaying or changing credentials.

## Route and feature coverage

| Feature / entry point | Observed route or action | Result and boundary |
|---|---|---|
| Dashboard | `/` | Loaded authenticated data after the initial API requests; reviewed at 1920×1080, 1440×900, 1366×768 and 390×844. A final follow-up captured before/after navigation screenshots at all four sizes. |
| Primary navigation | Dashboard, Workspace, Projects, Runs, Quality | At 390×844, labels were increased from 8px to 9px and scroll items from 42px to 52px. Concise English/Chinese mobile labels are unclipped while full link accessible names are preserved. All five primary destinations were browser-verified reachable by horizontal scrolling, with no document overflow. Desktop/tablet rules remain unchanged. |
| Project list and overview | `/projects`, `/projects/proj_golden_shop_v1` | Both routes rendered. Golden Demo Shop remained the selected project for scoped Workspace flows. |
| Requirement lifecycle | `/projects/:projectId/requirements/:requirementId` and Workspace `requirement` stage | Legacy object URL redirected to the project-scoped Workspace. Golden Demo has one existing requirement. No new analysis was started. |
| Test designs and cases | `/projects/:projectId/test-cases/:testCaseId` and Workspace `cases` stage | Legacy object URL redirected to Workspace; existing case details rendered. Golden Demo has eleven cases. No cases were created or edited. |
| Automation Studio | `/projects/:projectId/studio/file/...` and Workspace `code` view | Legacy Studio URL redirected to Workspace. Monaco loaded the bound test file and the project file tree. No automation or test source file was edited through the Studio. |
| Browser recorder | Workspace `browser` view | Created a temporary browser session, loaded the API-hosted local Demo Shop and received a browser frame. No page action, case save or source write was performed; session was closed. |
| Python debugger | Workspace `debug` through Test Explorer | Debugged `tests/test_shop.py::test_product_detail` through the UI/debugpy. The test ended **1 passed in 2.51s**. Existing breakpoints were accepted by debugpy but not hit by this target. No breakpoint was added or removed. |
| Run result | `/runs/:runId` and Workspace `results` stage | Existing `run_eb4ccaf35252f5440324e6f938cbeb7d` rendered as PASSED. Its UI correctly states that this successful run did not invoke failure repair. |
| Failure analysis and repair | `/failures/fail_16d594548ce0` and Workspace failure stage | Legacy failure URL redirected into Workspace. Existing failure history and the verified repair/retest state rendered. No repair or rerun was triggered in this audit. |
| Quality Discovery | Workspace `discover` view | Empty launch form and instructions rendered. No discovery run was launched; its generated coverage/gaps were not revalidated in this audit. |
| AI workflow | `/workflow` | Task/workflow page rendered. No task was created or approved. |
| Library / reports | `/library` | Rendered. No artifacts were changed. |
| Runs | `/runs` | Rendered. No run was started from this page. |
| Quality metrics | `/quality` | Rendered. |
| Worker cluster | `/workers` and authenticated cluster API | UI rendered. One registered Worker was OFFLINE; no Worker was started. The cluster summary reported 200 queued jobs (summary cap), while read-only SQLite counts showed 5,000 queued jobs. |
| AI/Jev settings | `/settings` | Real AI and Jev connection probes returned success. The Jev Playground returned `preserve_read_only`, confidence `1.0`, provider `jev`, model `jev-1.13.0`, and `fallback_used=false`. |
| Security | `/security` | Rendered; no access-control mutations were made. |
| Flaky tests | `/flaky` | Rendered; no action was taken. |
| Compatibility routes | `/recorder`, `/automation`, `/tasks`, requirement/case/Studio/run/failure legacy routes | Browser-observed redirects preserved project/context where applicable; `/automation` resolves to Library and `/tasks` to Workflow. |

## Project and queue safety

A read-only comparison of `runtime/ai_qa_platform.db` against the pre-start checkpoint showed identical execution-job and Golden Demo run counts:

- **All execution jobs:** 5,004 total — 5,000 QUEUED and 4 COMPLETED.
- **Golden Demo execution jobs:** 4 COMPLETED, 0 QUEUED, 0 RUNNING.
- **Other queued jobs:** 5,000, belonging to benchmark projects.
- **Golden Demo runs:** 5 FAILED, 5 PASSED, 1 CANCELLED at final check. `run_51c9455dff71` was RUNNING in the pre-start checkpoint, then API startup automatically marked it CANCELLED as stale after its 7,200-second recovery threshold; no manual cancellation occurred.
- **Worker registry:** one OFFLINE Worker, zero ONLINE/BUSY Workers.

No Worker was started or allowed to claim from the existing queue. The prior Golden Demo scoped-Worker acceptance is separately recorded in [`playwright-golden-journey-acceptance.md`](playwright-golden-journey-acceptance.md); it is not presented as a new Worker execution in this audit.

## Real provider evidence

- AI connection probe: HTTP 200, `connected=true`, `openai-compatible / deepseek-flash`; structured JSON probe succeeded.
- Jev connection probe: HTTP 200, `connected=true`, model `jev-1.13.0`.
- Jev runtime check: `CONNECTED / READY`, enabled, budget available, no reasons.
- Jev Playground decision: `preserve_read_only`, confidence `1.0`, `fallback_used=false`.

These were real UI/API calls. The tests added normal provider-invocation telemetry; no key, token or credential value was recorded in this report.

## Coverage limits

The audit did not claim a fresh Worker run, fresh Quality Discovery run, PostgreSQL behavior, complete debugger breakpoint-hit behavior, human rejection, retry-failure coverage, or tablet direct-refresh acceptance. Detailed overall disposition is in [`full-product-final-acceptance.md`](full-product-final-acceptance.md).
