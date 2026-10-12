# overall product UI redesign

- run-date: 2026-10-11
- task-type: ui-redesign
- scale: standard

## Product context
- React + TypeScript + Vite frontend (`apps/web`); shared application shell, navigation, tokens and components in `apps/web/src/index.css` plus app/components; workflow pages and Workspace feature styles build on them.
- Existing product has project-scoped Workspace stages (Requirement → Discovery → Cases → Automation → Results), primary Dashboard/Projects/Runs/Quality routes, settings, recorder, debugger and failure analysis. Preserve the consolidated context and existing navigation entry points.
- Existing global UI is already coherent and intentionally close to the supplied references (neutral surfaces, hairline borders, soft rounded cards, light/dark theme). This is a refinement, not a replacement of the architecture or a blank-slate visual reskin.

## Reference-derived design principles
1. Neutral, low-chrome canvas; white/near-white panels in light mode; dark slate surfaces in dark mode.
2. Narrow, grouped navigation with a quiet but immediately legible selected state; minimal shadows and thin separators.
3. High information density in dashboards/lists: metrics, trend, work queue and operational links remain visible without stacking excessive framing.
4. Semantic color reserved for status/actions; small toned icon tiles may aid scanning. Keep primary actions unmistakable.
5. Decision dialogs stay centered, compact and clearly structured; dim the background, state the consequence, and preserve secondary-cancel/primary-confirm order.
6. Retain keyboard focus, responsive behavior, translations and route/business behavior.

## Baseline observations
- Ran `git status --short`; the worktree had many pre-existing modifications. No changes were cleaned, staged or reverted.
- Read the existing product UX audit, feature inventory and acceptance evidence; these establish broad route/responsive coverage but are not a pre-redesign baseline. Prior audit covered Dashboard, Workspace, Projects, Runs, Quality, settings, recorder, debugger and related routes.
- Inspected authenticated current Dashboard at 1440×900 and 390×844, then loaded dark Dashboard at 1440×900. No browser errors, missing data placeholders, or document-level overflow after data settled.
- Current dashboard aligns with the reference hierarchy, but its four operational KPI cards consume roughly 206px vertically each on desktop, with three nested bands competing for the metric; selected desktop navigation is neutral gray rather than the reference’s pale accent state. Shared skeleton placeholders hard-code light gray, so they do not follow the dark palette during loading.
- Current sidebar uses 286px at desktop and heavy 20px radius; shared cards/controls and content rhythm can be made slightly more compact while preserving the current structure.
- Two supplied screenshot references are retained as visual direction only; no business concepts or text should be copied from them.

## Risk classification
- UI/UX: medium-high — global tokens affect many pages and themes; use a representative-surface review before extending.
- Technical: medium — styling-only work, but CSS is large and has legacy aliases/selectors. Keep selectors constrained and avoid behavior changes.
- Data: low — no data writes or operation launches permitted.

## Goals and acceptance criteria
- One coherent, compact visual language across the shell and shared primitives, visibly closer to the references without changing information architecture.
- Improve main content width, active navigation affordance and dashboard metric hierarchy/density; modal treatment should remain focused and readable.
- Light and dark themes must both use token-driven surfaces and retain readable contrast, including loading placeholders.
- Preserve routes, controls, labels, keyboard focus, responsive nav and existing content; no document-level horizontal overflow at 1440, 768 and 390 widths on representative pages.
- No new console/page errors or failed requests in browser checks; targeted tests, lint, typecheck and production build pass.
- Review changes in a real browser at desktop and mobile and inspect an alternate dark-mode page before acceptance.
