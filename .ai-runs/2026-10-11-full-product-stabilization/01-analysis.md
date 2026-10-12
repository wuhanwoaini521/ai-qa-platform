# Analysis

## Architecture and product shape

- Frontend: React + TypeScript + Vite; route table is `apps/web/src/app/routes.tsx`, top-level navigation is in `apps/web/src/components/Navigation.tsx` and `app/navigation.ts`.
- API: FastAPI routers in `apps/api/app/api`, services/repositories under corresponding boundaries; lifespan initializes Alembic, recovers interrupted work, starts the Task Runtime, and runs readiness checks.
- Worker: `apps/worker/worker/daemon.py`, claims distributed jobs through `/api/jobs/claim`; supports `WORKER_PROJECT_IDS` and passes it to the API. Worker will not be started without that project allowlist.
- Persistence: local SQLite at `runtime/ai_qa_platform.db`; database tests use per-test temporary databases. Current migration is at head.
- The product routes include Dashboard, Workspace (requirement/discovery/cases/automation/browser/debug/results/failure), workflow, library, projects, runs, quality, security, workers, settings, flaky, and legacy redirects. Several requested areas are unified views/redirects rather than independent routes.
- Real AI and Jev configuration is present. No credentials were emitted. `docker` is unavailable, so PostgreSQL/container validation is not available in this environment unless another local service appears.

## Safety and baseline

- Existing database is large and contains prior user/demo/test history. A consistent read-only checkpoint was saved before API startup.
- There are 5,000 queued jobs across benchmark projects and no online Workers. Do not run a global Worker. Restrict demo execution to `proj_golden_shop_v1` and verify unrelated queues remain unchanged.
- One Golden Demo Run was RUNNING at checkpoint (`started_at=02:20:51.117140`). The initial API start was below the two-hour stale-run recovery threshold. A later continuation start occurred after the threshold and the API automatically marked it CANCELLED; this runtime side effect is recorded in final evidence. No manual cancellation or restoration was performed.
- Full SQLite DB has 26 projects, 1 requirement and 11 test cases in the Golden Demo. Prior acceptance files document earlier run IDs, but final acceptance must use newly observed evidence and not treat them as this run's result.
- Existing worktree is substantially dirty; any new source change must avoid overwriting or broadly staging existing edits.

## Risk and acceptance

- **Risk: HIGH** (cross-layer product/runtime, real provider calls, worker queue, persistent run history, broad UX assessment).
- Prioritize read-only inspection and existing test suites first. For runtime tests, reuse the existing demo and avoid cleanup. Start API/web with the repo's `pnpm dev`; only start a Worker after authenticating and setting `WORKER_PROJECT_IDS=proj_golden_shop_v1`.
- Use browser screenshots/interactions for observed routes, and mark unvisited actions/pages BLOCKED rather than inventing coverage. AI/ Jev claims require provider/model/run evidence and no fallback.
- Do not commit unrelated pre-existing work. Gate 3 is about final-code regression, not committing; preserve the worktree and report the actual status.

## Follow-up continuation: mobile navigation readability

- The stable 390×844 Dashboard entry screenshot (`docs/audits/full-product-evidence/before/dashboard-390x844.png`) shows mobile navigation labels rendered at 8px and compressed into 42px-wide items. This is a concrete readability issue in the shared mobile navigation, although the horizontal scroller keeps destinations reachable and the page has no document overflow.
- Scope: improve only the mobile primary-navigation label size and item width in `apps/web/src/index.css`; desktop/tablet styles and navigation semantics remain unchanged. User data, API contracts, queue processing and provider calls are out of scope.
- A follow-up real-browser check in English showed the longer `Dashboard` and `QA Workspace` labels clipped inside 50px items, even though their accessible names remained intact. Compact responsive labels are required in both locales; preserve the full accessible names.
- Acceptance: mobile labels compute to 9px in 52px items; compact English and Chinese labels are not clipped; all five primary destinations remain reachable through the horizontal scroller; no document-level overflow at 390×844; desktop/tablet layout and full accessible names remain unchanged. Capture matching Dashboard before/after screenshots at 1920×1080, 1440×900, 1366×768 and 390×844, then rerun browser verification in both locales and final regression.
- Risk: MEDIUM, because the shared app shell is visible across routes, but the CSS change is scoped to the existing `max-width: 600px` rule.
