# Flow canvas — P0 read-only (2026-11-01)

Entry: `/flows?projectId=<id>&requirementId=<id>[&scenarioId=]`; also linked from the requirement
「场景设计」tab ("在画板中查看").

## What it does

Expands a requirement scenario into four columns on one canvas, from real data only:

`验收标准（coverage.criterion_ids） → 场景 → 动作（actions[]） → 期望（expected_outcomes[]）`

- Pure layout function `buildScenarioFlow` (no React), covered by 4 node tests.
- Read-only: no writes, no execution, no new API.
- Fit-to-width scaling so the last column is never clipped at 1280/1440.
- Scenario switcher writes `scenarioId` through the router (no history hacks).

## Files

- `apps/web/src/features/flow-canvas/flowGraph.ts` — layout + edge routing
- `apps/web/src/features/flow-canvas/FlowCanvas.tsx` — SVG connectors + node cards
- `apps/web/src/pages/FlowCanvasPage.tsx` — data loading, scenario switch, empty/error states
- `apps/web/src/app/routes.tsx` — `/flows` route
- `apps/web/src/i18n/locales/{zh-CN,en}/flowCanvas.json` — 27th namespace

## Verified

`tsc`, ESLint, frontend tests **238 passed** (4 new), `vite build`, i18n 3,558 keys.
Screenshots: `evidence/flow-canvas-1440x900.png`, `evidence/flow-canvas-1280x800.png` (8 nodes, no
horizontal page overflow).

## Next (P1, not built)

Editable canvas: node palette + drag/connect, `flow_to_steps()` compiling to the existing
`RecorderStep[]` → `generate_python_case`, preview diff, human save, then the existing run/evidence
path. No new execution engine.
