# Functional Tests

## Automated

- `pnpm --filter @ai-qa/web test`: **107 passed, 0 failed**.
- `pnpm lint`: **passed** — Ruff, Python format check, i18n parity (2,865 keys), and ESLint.
- `pnpm typecheck`: **passed**.
- `pnpm build`: **passed**. Existing Monaco large-chunk advisory remains.

## Real-browser interaction/layout

- Ran the real Vite app in system Chrome with deterministic API responses intercepted in Playwright. The API service was not started; no backend/runtime/database writes occurred.
- Verified PASSED and FAILED run result UI at 1440×900. Both displayed the three target columns; actual status color remained green for pass and red for failure.
- Viewport and computed grid results: 1440×900 (surface 1062px: 3 × 346px columns); 1024×900 (864px: 2 × 426px, activity full-width below); 820×1024 (666px: 2 × 327px, activity full-width below); 390×844 (336px: 1 column); 360×800 (306px: 1 column).
- Tablet stress fixture rendered 24 event rows; Browser filter narrowed to 22 and All restored all 24. Activity panel was reachable by page scrolling.
- Every profile had document width equal to viewport width, no internal result-panel/event-list overflow, and no page or console errors. Long test identifier uses two metadata columns in the narrow desktop activity panel instead of four cramped subcolumns.
- Screenshots: `artifacts/desktop-passed.png`, `desktop-failed.png`, `intermediate.png`, `tablet-stress.png`, `tablet-stress-activity.png`, `mobile-390.png`, and `mobile-360-activity.png`.
