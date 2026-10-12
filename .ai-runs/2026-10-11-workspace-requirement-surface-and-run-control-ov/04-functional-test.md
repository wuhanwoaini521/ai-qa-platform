# Functional Test

## Automated

- `pnpm --filter @ai-qa/web lint` — PASS (`eslint .`).
- `pnpm --filter @ai-qa/web test` — PASS (113/113 tests).
- `pnpm --filter @ai-qa/web build` — PASS (`tsc -b && vite build`). Existing Monaco chunks exceed the 500 kB warning threshold; no build error.
- `git diff --check` — PASS.

## Browser / Read-only Verification

Using the existing authenticated local workspace and selected requirement `REQ-001`; no run, AI analysis, write, or queue action was triggered.

- Desktop 1488×880: document width 1488; run launcher moved into header (y=89–119); lower rules/constraints content begins at y=852 and no longer intersects it. The requirement is contained in one paper surface.
- Tablet 768×900, phone 390×844, and narrow phone 360×640: `documentElement.scrollWidth` matched the viewport width; header actions remained visible; internal stage/tab rails scroll locally as designed.
- Keyboard: focus launcher → Enter opened the labeled `aria-modal` dialog; Escape closed it and returned focus to the launcher.
- Dark theme: transiently set root `data-theme=dark` for visual check (`--canvas #101318`, `--surface #1c2129`), then restored light without changing persisted preferences.
- Navigated to the Cases stage and back to Requirement to check the shared header; no document overflow or page error.
- Browser page errors and console logs: none observed.

Screenshots: `/tmp/aiqa-workspace-requirement-after-desktop.png`, `/tmp/aiqa-workspace-requirement-after-768.png`, `/tmp/aiqa-workspace-requirement-after-390.png`, `/tmp/aiqa-workspace-requirement-after-360.png`, `/tmp/aiqa-workspace-requirement-after-dark.png`.

The original “page crash” was not reproduced as a JavaScript/browser exception; the visible obstruction was reproduced and fixed.

## Follow-up: Cases Analysis Page

- Verified the supplied 用例分析 view at 1484×880 and 390×844 after the shared workspace CSS fix; the launcher is in the header and `documentWidth` equals the viewport.
- Simulated the conditional “查看进度” toolbar action at 1484, 768, and 390 px; it stayed within the workspace bounds, wrapping to a second row on the phone without horizontal overflow. This was a transient DOM-only layout check; no task/run was started.
- Dark-theme follow-up at 1484×880 also passed with no overflow or page errors. Screenshots: `/tmp/aiqa-workspace-cases-current-1484.png`, `/tmp/aiqa-workspace-cases-current-390.png`, `/tmp/aiqa-workspace-cases-current-dark-1484.png`.
