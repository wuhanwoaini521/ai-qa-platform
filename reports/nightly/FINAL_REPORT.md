# Nightly Platform Improvement — Final Report

**Date:** 2026-10-11
**Branch:** `agent/nightly-platform-improvement`
**Overall acceptance: PARTIAL — not a full-platform pass.** Local regression and sampled browser checks pass, and the two opt-in real AI + Jev repair acceptances passed. PostgreSQL, Python language-service analysis, cross-platform CI, full accessibility coverage, human rejection, and retry-failure remain incomplete or blocked.

## Summary of delivered improvements

- **Browser runtime:** headless Playwright presents a standards-shaped Chrome user agent, avoiding transport workarounds; focused runtime tests cover it.
- **Quality Discovery:** low-confidence candidates are marked skipped and exploration continues. They are not executed and the confidence threshold is unchanged.
- **AI operation traces:** vendor/provider failures are described with provider-neutral status language.
- **Platform UI:** retained the product's routes, bilingual copy, responsive Workspace behavior, and existing redesign; improved shared landmarks, skip navigation, input names, ARIA semantics, heading order, and light-theme contrast tokens. Dark-theme tokens remain separate.
- **Evidence:** desktop screenshots cover Dashboard, Projects, Runs, Quality, Settings, and Workspace requirement/cases/discovery/Studio/results/failure. Workspace Cases and Discovery also have 390×844 evidence; Cases has a dark-theme capture. See [`screenshots/before/`](screenshots/before/) and [`screenshots/after/`](screenshots/after/).

## Verification

| Check | Result | Notes |
|---|---|---|
| `pnpm lint` | **PASS** | Ruff, Ruff format, translation parity (25 namespaces, 2 languages, 2,868 keys), and frontend ESLint. |
| `UV_NO_SYNC=1 pnpm test` | **PASS** | **669 passed, 7 skipped, 44 warnings** in Python; PostgreSQL lane skipped because `AI_QA_TEST_DATABASE_URL` is unset. Frontend: **113 passed**. |
| TypeScript + production build | **PASS** | `tsc -b` and Vite build passed in the test task. Existing Monaco chunk >500 kB advisory remains. |
| `git diff --check` | **PASS** | No whitespace errors in the working diff at validation time. |
| axe-core 4.12.1, Chrome | **PASS — sampled** | 11 representative light-theme route states and Workspace Cases in dark theme had zero confirmed violations after fixing a Workspace Results heading-order finding. See [Accessibility and UX](ACCESSIBILITY_AND_UX.md). Axe-incomplete contrast checks remain for manual review. |
| Responsive browser review | **PASS — sampled** | Workspace Cases and Discovery at 390×844 had no document-level horizontal overflow. Desktop captures at 1480×900. |
| Real AI + Jev locator repair acceptance | **PASS — opt-in** | Earlier in this task, real provider `openai-compatible/deepseek-flash` + `jev-1.13.0` selected and Playwright-verified a locator; exact rerun passed. No fallback. |
| Real AI + Jev browser UI repair acceptance | **PASS — opt-in** | Earlier in this task, browser UI flow completed with run `PASSED` and workflow `VERIFIED`; no fallback. These tests are not part of ordinary `pnpm test`. |

## UX and accessibility disposition

The skip link, one shared main landmark, named primary navigation/select controls, ARIA roles, and Results heading hierarchy were checked in the browser. axe initially identified a heading-order issue in Workspace Results; it was corrected and rescanned with no remaining confirmed violations on the sampled routes. Axe `color-contrast` incomplete nodes still need human review; they are not counted as confirmed failures or as fully passing contrast checks. No complete WCAG, screen-reader, touch, or cross-browser audit is claimed.

## Architecture assessment

The current modular-monolith boundaries are serviceable for scoped changes: UI → API DTOs, API → application services, BrowserRuntime port/adapters, and deterministic pytest results remain distinct. **Architecture disposition: PARTIAL / B.** Main follow-ups are oversized orchestration services, optional Worker project allowlisting, workflow state/persistence coupling, and missing PostgreSQL concurrency acceptance. See [Architecture Audit](ARCHITECTURE_AUDIT.md).

## Blockers and known gaps

- **PostgreSQL:** `AI_QA_TEST_DATABASE_URL` is not configured; the PostgreSQL lane did not run. SQLite does not substitute for PostgreSQL locking/concurrency acceptance.
- **Python language service:** `basedpyright` is unavailable (`uv run` cannot spawn it). The earlier `uv sync --all-packages --locked` attempt was blocked by a macOS `nodejs-wheel-binaries` build failure; it was not repeated during final regression.
- **Workflow coverage:** failure human rejection is not implemented in the inspected workflow; retry-failure acceptance remains incomplete. No new Quality Discovery exploration was started in the final browser pass.
- **Platform coverage:** no Linux/Windows CI or Firefox/WebKit matrix was run.
- **Accessibility coverage:** sampled routes only; axe-incomplete contrast items, screen-reader review, and every modal/error state remain open.
- **Build advisory:** Monaco produces a large Vite chunk; build still succeeds.

## Data and operational safety

No Worker was started and no new Quality Discovery run was created during final visual/a11y review. The existing project/queue data was not reset. Runtime artifacts under `runtime/` are local data and are intentionally excluded from delivery. Real-provider checks were explicit opt-ins; credentials were not included in this report.

## Evidence and continuation

- Screenshots: [`screenshots/before/`](screenshots/before/) and [`screenshots/after/`](screenshots/after/).
- Accessibility detail: [`ACCESSIBILITY_AND_UX.md`](ACCESSIBILITY_AND_UX.md).
- Architecture detail: [`ARCHITECTURE_AUDIT.md`](ARCHITECTURE_AUDIT.md).
- Reproducible handoff and outstanding actions: [`HANDOFF.md`](HANDOFF.md).
