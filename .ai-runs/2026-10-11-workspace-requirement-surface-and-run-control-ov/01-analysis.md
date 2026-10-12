# Analysis

## Architecture / Evidence

- `WorkspacePage.tsx` renders the workspace header, stages, embedded `RequirementsPage`, and `WorkspaceRunDock`.
- `RequirementsPage.tsx` embeds `RequirementLifecyclePanel`; `workspace.css` and `lifecycle.css` own the page presentation.
- The local requirement route rendered successfully at 1488×880. Browser page errors were empty; `documentWidth === viewportWidth` (1488), so a React crash or horizontal document overflow was not reproduced.
- Confirmed user-visible defect: `.workspace-run-launcher` is `position: fixed` at viewport bottom-right. In the repro, it occupied y=826–866 and overlapped the visible “业务规则 / 约束与依赖” headings at y=852–873. The inner content scrolls independently (`clientHeight=650`, `scrollHeight=864`), so the fixed launcher obscures live content.

## Design Direction / Scope

Use the existing cool-mist canvas, paper surface, slate ink, QA blue, and pass green tokens. Keep Plus Jakarta Sans; use JetBrains Mono only for traceable IDs. Treat the acceptance-criteria list as the primary evidence ledger, inside one continuous paper work surface; retain the existing stage sequence and split rules/constraints below. Do not add generic KPI cards or copy unrelated reference content.

Move only the persistent run-control trigger into the header action flow; keep its modal, handlers, safety, and keyboard behavior intact. Add a single requirement work surface and responsive action wrapping. No business logic or API changes.

## Risk

MEDIUM: user-visible workspace shell/component layout and responsive behavior; no persistence or domain behavior changes. Main regression surface is the workspace requirement route and other workspace stages that share the launcher.
