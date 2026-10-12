# AI QA Platform V2 overhaul

- run-date: 2026-10-12
- task-type: ui-redesign
- scale: standard (large multi-page scope; recorded in plan)

## User goal and acceptance

Users can identify their project and QA context, distinguish AI task success from test-run success, author Python automation with a usable language service, and move from requirement analysis through a trustworthy run result without losing context. Preserve routes, API contracts, persistence, user settings, responsive behavior, bilingual labels, and all pre-existing worktree data.

Acceptance requires (a) evidence-backed root causes for changed behavior; (b) target tests covering success and failure/empty states; (c) real local sandbox workflow with real configured AI + Jev and no fallback; (d) responsive browser verification and screenshots; (e) review/regression; (f) selective commits containing only this task's diff.

## Current architecture / evidence

- React + TypeScript + Vite UI (`apps/web`); FastAPI services (`apps/api`); editable runtime project workspaces under ignored `runtime/`.
- User navigation follows Project → Workspace stages → Runs/Failure detail. Existing routes and APIs are explicitly preserved.
- Browser exploration recorded in `reports/v2/product-audit/REPORT.md`; live AI + Jev requirement analysis in sandbox `proj_ec58fd0e508e` succeeded (3 risks, 4 scenario drafts, two Jev decisions).
- Repro candidates: duplicate project labels (`ProjectsPage` and shared project selectors); Python language server unavailable in Automation Studio; an AI analysis task temporarily displayed a test-run pass despite zero run records; dashboard initially showed only skeletons for ~4 seconds.
- Browser reports no uncaught page errors on observed routes. The launchable existing session works; fresh Chrome launch is blocked by a local VideoToolbox symbol mismatch, and video recording is blocked by absent `ffmpeg`.

## Constraints / data safety

- Do not alter backend/API contracts, schemas, user AI/Jev configuration, or existing projects/runs.
- Only the explicitly named `V2 Overhaul Sandbox 2026-10-12` project, requirement and adopted case have been added through the UI. No existing business data has been edited.
- Do not stage pre-existing changes in `apps/web/src/features/{requirements,runtime,test-cases,workspace}`, `apps/web/src/pages/RunsPage.tsx`, translations, prior `.ai-runs/`, `docs/audits/`, or `runtime/runtime/`.
- `.gitignore` has no `.ai-runs/` rule; this task's log remains out of commits unless an explicit, safe inclusion decision is made.

## Root-cause outcomes and remaining unknowns

1. **Python language service:** active Python 3.13 environment lacks `basedpyright` and `nodejs_wheel`; `PythonLanguageService.start()` imports both. macOS 12.7.6 does not meet the locked Node wheel's macOS 13 minimum. A scoped uv sync dry-run would remove shared `pytest-asyncio`, `ruff`, and `worker`, so no sync was executed. Service restoration remains blocked on a compatible isolated dependency environment.
2. **Duplicate projects:** presentation-only disambiguation is safe; no stored project names/records need changing. Duplicate names receive collision-expanded ID suffixes.
3. **Task versus TestRun status:** `WorkspaceRunDock` treated task `COMPLETED` as passed. A separate state model now gives persisted TestRun status precedence and distinguishes task terminal states.
4. **Dashboard loading:** current browser timing shows `/api/dashboard/stats` took 1.48s / 126,750 bytes, while `/api/tasks` took 141ms; content was visible by the 3s capture. This explains the 800ms skeleton but does not isolate all remaining render time, so Dashboard code was not changed.
5. **Project table on mobile:** 762px table content was clipped in a 344px card. It now scrolls within an accessible region with keyboard controls and a localized swipe hint.
6. The sandbox project, requirement, case, binding, and run remain; cleanup is unavailable in the visible UI. Preserve as runtime data and do not claim deletion.
