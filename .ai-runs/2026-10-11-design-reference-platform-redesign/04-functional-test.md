# Functional Test

## Automated

- `pnpm --filter @ai-qa/web test` — **PASS**, 105 passed, 0 failed.
- `pnpm --filter @ai-qa/web typecheck` — **PASS**.
- `pnpm lint` — **PASS**: Ruff, Python formatting, i18n parity, and frontend ESLint all passed; i18n check found 25 namespaces / 2 languages / 2,857 keys.
- `pnpm --filter @ai-qa/web build` — **PASS**. Vite emitted a size warning for the 4 MB Monaco editor chunk (>500 kB); build completed successfully.
- `git diff --check` — **PASS**.

## Browser / Functional

Used the running local Web/API with system Chrome via Playwright; readiness and page navigation succeeded. Authenticated with the existing seeded local account (credentials intentionally omitted from this log). Browser actions were read-only except for ephemeral browser-local preference/session state.

- Inspected Dashboard, Projects, Settings, Workspace requirements, and an existing Workspace run result.
- Run result selected for verification was a real `ERROR` without a linked `TestExecution`/`Failure`; the UI continued to report unavailable evidence and zero saved per-case results honestly. No test was run and no evidence was fabricated.
- Confirmed project switching navigates to the chosen Workspace project and clears stale run/query context. Confirmed the all-project option remains available on global routes and is absent on project-scoped Workspace routes.
- Clicked a Workspace stage and observed the stage-specific heading update; opened and collapsed the result evidence disclosure.
- Confirmed the desktop result panels are scrollable and the last repair stage becomes reachable after scrolling.
- Browser page-error count: **0**.

## Evidence / Viewports

- 1440×1000: `/tmp/aiqa-redesign-accepted-desktop.png`, `/tmp/aiqa-redesign-dashboard-loaded.png`.
- 768×1024: `/tmp/aiqa-redesign-accepted-tablet.png`.
- 390×844: `/tmp/aiqa-redesign-accepted-mobile.png`.
- Dark theme: `/tmp/aiqa-redesign-dark.png`.
- Workspace requirement view: `/tmp/aiqa-redesign-requirement.png`.
- Document width matched viewport at all three sizes; no page-level horizontal overflow.
- Dark theme token rendering was inspected in the actual browser. API/Web remained read-only; no Provider calls, Worker startup, project changes, or database reset.
