# Functional and regression checks

## Automated checks (current run)

- `pnpm --filter @ai-qa/web test` — **147 passed, 0 failed**.
- `pnpm --filter @ai-qa/web typecheck` — **PASS**.
- `pnpm --filter @ai-qa/web lint` — **PASS**.
- English/Chinese `studioShell` key parity — **109 keys match**.
- `pnpm --filter @ai-qa/web build` — **PASS**. Existing advisory remains: Monaco language/editor chunks exceed Vite's 500 kB warning threshold.
- Scoped `git diff --check` — **PASS**.
- Backend test suite not rerun: no API/backend code or contract changed.

## Real browser workflow

Replayed `.ai-runs/night-round-3/product-ux-rebuild/verify_workflow.py` with the real authenticated app/API, pinned **Playwright 1.62.0**, system Chrome, and Northstar's local demo project. The script asserts the request payload and final run result, navigates the actual results/runtime/failure/debug screens, hashes the demo test source before/after, and saves screenshots plus JSON.

- Embedded Studio has **0** project dropdowns and **1** labeled Quick Open; toolbar labels the selected target as **运行用例** and its title as **运行所选用例**.
- Opened Run Controls and read its selected config: `staging / JP / chromium / 1 worker`.
- Clicked the Studio Run Case button. Captured `POST /api/runs` carried `nodeids=[tests/test_shop.py::test_search]`, `browser=chromium`, `environment={QA_ENVIRONMENT:staging, QA_REGION:JP}`, and `parallel_workers=1`.
- Latest acceptance Run: `run_0fee81b19f0c` — **PASSED**, 1/1 saved execution, `test_search` passed. The workspace results stage, run log/events, and Runtime **浏览器** tab all opened successfully; the captured local browser frame and two passed browser actions are visible.
- Browser event timestamps with empty values now render `—`, not `Invalid Date`.
- Opened the existing `fail_16d594548ce0` failure (`LOCATOR_CHANGED`; historical repair state `VERIFIED`), entered Debug through the failure Run Controls, reached the paused frame at `pages/shop.py:35`, then stopped the debug session. AI/Jev was **not** called and Apply was **not** clicked.
- Paused-debug toolbar: minimum button width **44px**, **0 intersections** at 1440px.
- Source hash was identical before/after. No requirement/case edits or repair writes were made.

## Responsive and keyboard interaction

Measured with the stage rail and Studio open at 1440×1000, 768×1024, and 360×800. At 1440px the stage nav is 1160/1160px with five 229px buttons; at 768px it is 660/660px with five 129px buttons; at 360px it is 324/324px with five 62px buttons. No page-width or stage-rail overflow; Tab from stage 1 moves to stage 2 at all three widths. Measurements are in `evidence/after/interaction-results.json` and `stage-navigation-1440.json`; screenshots are under `evidence/after/`.

## Test data and observed error

The iterative live workflow left **7 ordinary passed TestRun records** for the read-only `test_search` case in Northstar (including the final acceptance Run); they were not deleted. The demo shop uses an ephemeral local server and its source file hash remained unchanged. A browser console 404 was reproducible on this demo page as `GET /favicon.ico` (the static demo has no favicon); it is not a platform API failure, and the user's demo source was not edited.
