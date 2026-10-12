# Functional Test — Workspace Test Case Selection and Layout

## Automated checks
- `pnpm --filter @ai-qa/web test` — **passed: 122 tests, 0 failures**. Includes five selection-model tests for selected-single, multiple cases, unselected-single, external/fallback IDs, and empty data, plus existing Workspace context/runtime tests.
- `pnpm --filter @ai-qa/web lint` — **passed**.
- `pnpm --filter @ai-qa/web typecheck` — **passed** (`tsc --noEmit`).
- `pnpm --filter @ai-qa/web build` — **passed** (`tsc -b && vite build`). Existing large Monaco chunk warning remains; largest Monaco editor chunk is approximately 4 MB minified.
- `git diff --check` — **passed**.

## Browser checks (real Golden Demo project data, read-only)
- On the collapsed-context Workspace case page, the selector exposed all **11** project cases, including cases beyond the context rail's 10-item limit.
- Changed selection from `case_golden_002` to `case_golden_001`: detail changed from `商品详情可操作` to `搜索匹配商品`; URL changed `caseId`, `testDesignId` (`des_golden_002` → `des_golden_001`) and `bindingId` (`bind_golden_002` → `bind_golden_001`). The requirement ID remained the same because the available demo cases share that requirement. Restored `case_golden_002` afterward.
- Direct legacy link `/projects/proj_golden_shop_v1/test-cases/case_golden_001` redirected to Workspace with that case selected and matching detail.
- No server-side case data was changed; browser console/error check was empty.

## Evidence
- `/tmp/test-cases-after-1524.png` — light desktop after implementation.
- `/tmp/test-cases-after-768.png` — tablet.
- `/tmp/test-cases-after-390.png` and `/tmp/test-cases-after-360.png` — phone.
- `/tmp/test-cases-after-dark-1524.png` — dark desktop.
- `/tmp/test-cases-focus-1524.png` — visible keyboard focus on the native selector.
- `/tmp/test-cases-final-1524.png` — restored light desktop state.

The live project has multiple cases but no one-case or empty-case fixture; those boundary states were exercised by the selection-model unit tests rather than by switching live project data.
