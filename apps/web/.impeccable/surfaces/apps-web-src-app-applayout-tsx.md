---
version: 1
slug: "apps-web-src-app-applayout-tsx"
primary_target: "apps/web/src/app/AppLayout.tsx"
related_targets: ["apps/web/src/pages/DashboardPage.tsx","apps/web/src/features/workspace/WorkspacePage.tsx"]
---

# Graphite Developer Studio — shared shell and workbench surfaces

## Scope and mode

Operate surfaces: shared app shell plus Dashboard, Workspace Debug/Explore/Requirements/Test Explorer/Write Tests/Results/AI Repair, Projects, and Quality. The user authorized this scoped extension in `.ai-runs/2026-10-27-graphite-fidelity-recovery/00-request.md`; the approved Pencil file has dedicated frames only for Dashboard, Debug, and Explore. For added surfaces, preserve the existing React structure/content/actions and use the established Graphite system—do not invent new page IA. Audience: QA engineers triaging an execution and moving between code, browser evidence, requirements, results, and repair state. Preserve current routes, API-backed records, editor/runtime/recorder controls, project scope, deterministic verdicts, and human approval boundaries. Desktop target: 1440×900; compact 1280×800; large 1920×1080. Mobile-specific work is out of scope.

## Direction contract

**THESIS:** Put the evidence trail at the center of the QA workspace; refuse the generic card-wall dashboard and disconnected page-by-page debugging.

**OWN-WORLD:** Graphite canvas `#111619`, rail `#151C20`, surfaces `#1B2428` / `#222D32`, rules `#344148`, ink `#E7EFEC`, muted ink `#A1B0AC` / `#788985`; mint `#A6D5C1` marks the primary path, amber `#E6AE68` review/paused state, red `#F17D73` failure, blue `#9BBEFF` secondary links. System sans + local mono; compact technical density, square-edged nested panels, thin dividers.

**STORY:** See the project and its current evidence, inspect the relevant code/browser state, then choose a human-controlled next action. Signature interaction: selecting an existing RuntimeTimeline event keeps the same project/run context and selects its related evidence; use the current `stepId` URL state, not a second runtime. No AI verdict is implied; PASS/FAIL text remains sourced from deterministic execution. Motion is limited to 120–180ms state/space transitions; no ambient animation, with reduced motion respected. Fixture screenshots carry a non-live provenance label.

**FIRST VIEWPORT:** Dashboard: 64px tool rail, utility header, one project/run journey strip, then a Projects registry beside recent activity. Debug: test/run explorer at left, code and live-browser evidence in the center, trace companion at right, execution artifacts below. Explore: task and browser occupy the left two-thirds, discovery thread at right, observed journey trace below. All states use real data; empty runtime/session stays explicitly empty.

**FORM:** User-pinned Direction A — Graphite Developer Studio, from `docs/design/visual-reboot-a-graphite-studio.pen`. Operate/code-led; no comp round or new design direction. The seven added page states use the current browser screenshot as layout evidence and inherit the approved shell/tokens only. Seed reference: none (unavailable).

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
