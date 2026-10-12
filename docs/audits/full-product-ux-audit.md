# Full Product UX Audit

**Audit date:** 2026-10-11
**Browser:** system Chrome, authenticated local application
**Project context:** `proj_golden_shop_v1` unless a route was explicitly global.

## Workflow comparison

The current product routes core work through a project-scoped Workspace with five stages: **Requirement → Discovery → Cases → Automation → Results**. Browser navigation confirmed that six legacy entry categories now resolve into this shared Workspace: requirement, case, Studio, run-result, failure and recorder. The previous standalone failure screen is retained as a visual reference in [`overnight-evidence-2026-10-10/failure-ui/desktop.png`](overnight-evidence-2026-10-10/failure-ui/desktop.png); the current Workspace carries the same Golden Demo failure context through diagnosis, repair and retest status in one project context.

| User goal | Earlier / compatibility entry | Current observed path | UX effect |
|---|---|---|---|
| Open a requirement | `/projects/:id/requirements/:requirementId` | Redirects to Workspace `requirement` stage | Project context stays in the Workspace URL. |
| Review cases | `/projects/:id/test-cases/:testCaseId` | Redirects to Workspace `cases` stage | Case selection and requirement context are kept together. |
| Edit automation | `/projects/:id/studio/...` | Redirects to Workspace `code` view | Automation remains in the same project/stage shell. |
| Inspect a run | `/runs/:runId` | Redirects to Workspace `results` stage | Result view can open failure, code, runtime details or rerun actions in context. |
| Investigate a failure | `/failures/:failureId` | Redirects to Workspace failure stage | Failure queue, diagnosis/repair state, and retest result share one context. |
| Record a browser flow | `/recorder` | Redirects to Workspace `browser` view | Recorder is a Workspace automation view rather than a separate project route. |

**Workflow simplification gate: PASS (bounded to navigation/context consolidation).** This is evidence of fewer route/page transitions, not a claim that every repair branch is complete. Human rejection remains unsupported in the inspected failure workflow, and retry-failure coverage remains incomplete.

## Browser interaction and responsive review

The browser visited the Dashboard, Projects, Project Overview, Requirement, Cases, Studio, Run Results, Recorder, Debugger, Failure/Repair, Workflow, Library, Runs, Quality, Quality Discovery, Workers, Settings, Security, Flaky and legacy routes. At the four requested viewport sizes, the Dashboard and core Workspace Requirement/Cases/Results/Failure views showed no document-level horizontal overflow:

- 1920×1080
- 1440×900
- 1366×768
- 390×844

Screenshots were taken after page-specific loaded-state checks. The initial quick capture of the mobile Dashboard was a loading skeleton because it waited only for the app shell; it was replaced with a stable post-data screenshot. That was an evidence-capture timing issue, not a reproduced product defect.

### After evidence

All screenshots are under [`full-product-evidence/after/`](full-product-evidence/after/):

- Dashboard: `dashboard-{1920x1080,1440x900,1366x768,390x844}.png`
- Requirement: `workspace-requirement-{1920x1080,1440x900,1366x768,390x844}.png`
- Cases: `workspace-cases-{1920x1080,1440x900,1366x768,390x844}.png`
- Run result: `workspace-run-result-{1920x1080,1440x900,1366x768,390x844}.png`
- Failure: `workspace-failure-{1920x1080,1440x900,1366x768,390x844}.png`
- Additional desktop evidence: `automation-studio-1440x900.png`, `debugger-1440x900.png`, `recorder-live-1440x900.png`, and `settings-jev-playground-1440x900.png`.

Entry snapshots are under [`full-product-evidence/before/`](full-product-evidence/before/). They document the application as it existed when this audit began; they are **not** a pre-redesign source baseline. The historic failure screenshot above and current [`workspace-failure-1440x900.png`](full-product-evidence/after/workspace-failure-1440x900.png) do show the same retained failure context before analysis versus after the verified repair/retest journey. They differ in workflow state, not only layout.

### Controlled navigation before/after evidence

The continuation captured the loaded Dashboard before and after a focused mobile-navigation refinement. Visible Dashboard summary values remained the same; the pre-existing RUNNING test record was separately auto-recovered as stale during API startup before the final captures, so database-wide identity is not claimed. The baseline is in `full-product-evidence/before/`; the final browser captures are in `full-product-evidence/after/`. At desktop and tablet breakpoints the responsive rule is not active, so layout remains unchanged. At 390×844, primary navigation labels increased from 8px to 9px and each scroll item from 42px to 52px. Compact labels are localized in both languages, while link accessible names retain their full translations.

| Viewport | Before | After |
|---|---|---|
| 1920×1080 | [Dashboard](full-product-evidence/before/dashboard-1920x1080.png) | [Dashboard](full-product-evidence/after/dashboard-1920x1080.png) |
| 1440×900 | [Dashboard](full-product-evidence/before/dashboard-1440x900.png) | [Dashboard](full-product-evidence/after/dashboard-1440x900.png) |
| 1366×768 | [Dashboard](full-product-evidence/before/dashboard-1366x768.png) | [Dashboard](full-product-evidence/after/dashboard-1366x768.png) |
| 390×844 | [Dashboard](full-product-evidence/before/dashboard-390x844.png) | [Dashboard](full-product-evidence/after/dashboard-390x844.png) |

At 390×844, the real browser measured 9px labels in 52px items, with 148px visible nav width and 264px scroll width. All five primary navigation destinations were reachable by horizontal scrolling and each route opened correctly. Compact labels were unclipped in both Chinese and English, and the full accessible names remained present. Document width remained 390px; desktop and tablet document widths also matched their viewport widths. The visible database-backed Dashboard summary values were unchanged. One unrelated stale TestRun status changed during startup recovery; no pixel-diff or broader redesign delta is claimed.

**UI before/after evidence gate: PASS — scoped to the mobile navigation readability refinement.** This does not erase the broader audit’s limitations: the pre-existing main redesign was already present at audit entry, and these screenshots do not serve as a pre-redesign baseline.

## Interaction findings

- **Passed:** direct legacy route resolution, project-scoped context, responsive layout, Dashboard data load, Workspace result/status rendering, real AI/Jev settings flow, recorder browser frame, and a successful debugger test run.
- **No browser console/page errors** were observed in the targeted runtime flows. The broad route sweep recorded only expected aborted run-event streams when navigating away; no HTTP 4xx/5xx was observed there.
- **Confirmed and fixed P2 readability issue:** at 390×844, mobile navigation labels were 8px in 42px items. Updated to localized 9px labels and 52px items; all five primary destinations remain horizontally reachable in both locales, with full accessible names and no page overflow. The exact before/after screenshots are linked above.
- No browser console/page errors or HTTP/API response failures occurred during post-fix checks. All 16 core Workspace Requirement/Cases/Run Result/Failure screenshots were recaptured after the change; every route returned HTTP 200 and no viewport had document overflow. Eight active-run SSE requests were cancelled during the final screenshot sweep as pages changed; these expected client aborts were not server failures.
- This was a contained navigation refinement, not a redesign of the Workspace or broader shell; the full accessibility audit and all touch/keyboard combinations remain unperformed.

## Out of scope / still limited

- No full WCAG/accessibility audit, screen-reader pass, or cross-browser matrix.
- Golden Demo tablet direct-refresh behavior remains unverified.
- Human rejection and retry-failure workflow branches are not accepted as passed.
- PostgreSQL was unavailable; only local SQLite behavior was checked.
