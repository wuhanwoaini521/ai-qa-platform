# Analysis

## Product and Golden Journey

AI QA Platform unifies requirements, test design/cases, automation authoring, execution, failure evidence, AI/Jev-assisted repair, and exact-case verification. The representative journey is: select project/context → author or select a case → execute → inspect actual failure evidence → review/apply a repair proposal → verify by real test execution.

## Reference Direction

The supplied image is a run-monitor/“用例分析” desktop screen. Its defining patterns are:

- A compact, full-width project bar at the top; workflow navigation is a separate left rail below it.
- A clear page title and contextual actions above a horizontal, stateful workflow timeline.
- A dense but scannable three-column work area: failure summary/next step, live workflow progress, and current task/event log.
- Evidence, source code, and execution metrics are visible as complementary lower panels.
- White and cool blue-gray surfaces, thin blue-gray borders, restrained corner radii, strong blue primary/active states, and green/red status semantics.
- The design principle is “make real QA work observable and actionable”: show evidence and actual states, preserve context, and never invent AI or execution progress.

## Current Implementation Evidence

- Shared shell: `apps/web/src/app/AppLayout.tsx`, `apps/web/src/components/Header.tsx`, `apps/web/src/components/Navigation.tsx`, and `apps/web/src/index.css`.
- Workspace stage/result: `apps/web/src/features/workspace/WorkspacePage.tsx`, `WorkspaceRunResult.tsx`, and `workspace.css`.
- Current shell has an inset/rounded app frame, sidebar beginning at the top edge of that frame, and a header confined to the main content column. The project selector is on the header's right; active nav is a white bordered item with a small blue marker.
- At 1440×1000, the workspace already has a horizontal stage strip and the run result already organizes failure summary, AI/Jev repair workflow, and current task/log into three columns. Evidence is collapsed by default. Existing colors are already light and tokenized, but shell hierarchy and active states differ from the reference.
- Real browser inspection used the running local API/Web with system Chrome. Health/readiness and Web root returned HTTP 200. Dashboard, workspace, and run routes rendered without page errors. The selected local run was an ERROR without a linked `TestExecution` or `Failure`; the UI correctly displayed unavailable evidence instead of fabricated failure statistics. A couple of aborted event-stream requests occurred on route changes, not persistent application errors.
- Browser data was inspected read-only; no test run, workspace write, project mutation, or database reset was performed.

## Scope and Risk

- Apply the reference system through shared shell and existing design tokens, then tune the Workspace run/result surface as the representative page.
- Preserve all route destinations, project selection semantics, action availability, loading/error/empty/success states, dark theme preference, and localization. Keep business behavior/API contracts unchanged.
- Do not redesign every domain page into the same grid; carry common shell, spacing, typography, color, and component treatment across them.
- Risk is HIGH because the shared shell and navigation affect many routes and responsive breakpoints, despite the work being frontend-only.
- No dedicated visual-design skill (e.g. ui-ux-pro-max) is installed; use the supplied image, current product tokens, and the UI/UX review workflow.
- `scripts/init_run_log.py` referenced in the project-delivery guide is absent in this checkout. A unique run directory was created manually after verifying no same-date name existed; prior `.ai-runs` content was not touched.

## Acceptance Criteria

1. Desktop shell has the reference hierarchy: full-width project bar, distinct navigation rail, unframed workspace canvas; active navigation and primary actions use the reference blue treatment.
2. Workspace stage/result retains actual state and existing actions, with the reference's title → progress → three-column summary/progress/log hierarchy and accessible evidence/code/metrics disclosure.
3. Shared token changes improve consistency without breaking dark mode, existing feature surfaces, route navigation, or user preferences.
4. At 1440px, 768px, and 390px, the shell and representative workspace/result pages have no page-level horizontal overflow; navigation and primary actions remain reachable.
5. Browser verification covers representative routes and real interactions (project selector/navigation, stage selection, result disclosure) without backend mutations.
6. Frontend tests, typecheck, lint, and production build pass. No assertion or runtime behavior is weakened to achieve a visual pass.
