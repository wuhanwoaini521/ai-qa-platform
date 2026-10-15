# Playwright Golden Journey — Acceptance Report

**Assessment date:** 2026-10-11

**Overall status: PARTIAL** — the core real-provider, scoped Worker, failure-repair, browser-agent and UI journey passed. Full acceptance remains incomplete because human rejection is not supported, retry-failure coverage is incomplete, and PostgreSQL validation was unavailable.

## Acceptance summary

| Area | Status | Evidence / limitation |
|---|---|---|
| Golden Demo data and queue safety | **PASS** | Reused project `proj_golden_shop_v1` / requirement `req_golden_shop_v1`; no DB reset. Worker claims were scoped to this project. All 200 unrelated queued jobs remained queued. Worker stopped; registry is `OFFLINE`. |
| Real AI analysis and Jev decisions | **PASS** | Analysis `6afe7c795b164e3b96f60b2f363b791b` produced 11 scenarios. Jev selected `RISK-001` (0.73) and `SCN-004` (0.81), without fallback. Two failed real attempts remain preserved. |
| Case adoption and AI automation | **PASS** | Adopted 11 designs, including new `SCN-010` and `SCN-011`, while preserving existing cases. Human-reviewed and activated binding `bind_900a33d481f9`; workspace validation and pytest collection were clean. |
| Scoped Worker execution | **PASS** | Generated case run `run_1b850d74579d` passed; complete automated Golden Demo suite `run_92a613c81881` passed **10/10**. |
| Locator failure → diagnosis → approval → repair → retest | **PASS** | Failure `fail_16d594548ce0` retained. Jev selected a source-backed `pages/shop.py` locator repair verified against Playwright evidence; human approval applied it. Exact-case run `run_eb4ccaf35252f5440324e6f938cbeb7d` passed; workflow state `VERIFIED`. Initial Worker evidence lacked page evidence; a local rerun supplied it, and both records were retained. |
| Wrong-oracle diagnosis | **PASS** | `fail_703a5695edf1` was identified as a wrong test oracle; repair state `NOT_APPLICABLE`. Assertions were not weakened. Controlled catalog mismatch `fail_cbf1a3980f8e` was diagnosed, catalog restored byte-for-byte, and `test_add_to_cart` passed. |
| Real browser-agent journey | **PASS** | `c9fc99b1d89f49af93c418c57c22f114` submitted `qa-empty-state-20261011` and verified “No products found. Try another search.” with two real Jev decisions and no fallback. Earlier blocked/weak tasks remain retained and are not counted as successful search submission. |
| Platform UI review | **PASS (focused)** | Chrome review covered dashboard, project, Workspace run/failure and settings. Workspace run/failure views were reviewed at desktop, tablet and mobile. Not a complete accessibility or viewport audit. |
| Human rejection branch | **BLOCKED** | Rejection is not exposed by the inspected failure workflow UI/API; this branch was not exercised. |
| Retry-failure branch | **PARTIAL** | Coverage remains incomplete; no pass is claimed. |
| PostgreSQL and tablet direct refresh | **BLOCKED / UNVERIFIED** | Docker/PostgreSQL unavailable. A tablet direct-refresh-specific check was not independently established. |

## Real-provider and lifecycle evidence

The configured AI runtime was `openai-compatible/deepseek-flash`; Jev was `jev-1.13.0`. Provider readiness and persisted decisions were checked without displaying or changing credentials. Successful analysis recorded fallback false and 5,999 input / 2,792 output tokens.

Two failed AI attempts were deliberately preserved: one ended with incomplete structured output at 6,000 tokens; the next reached the 10,000-token limit and was recorded as `output_limit`. Those outcomes motivated shared streaming output-limit classification, shorter duplicated case context, lifecycle prompt preservation rules and disabling DeepSeek reasoning-token mode for structured lifecycle/browser-planning calls. The failures were not overwritten or represented as successes.

The demo test automation binding was reviewed and activated before Worker execution. The worker received `WORKER_PROJECT_IDS=proj_golden_shop_v1`; other Workers were not started. This is an opt-in safety control: Workers without the setting keep legacy global-claim behavior.

## Shop and platform UI evidence

`examples/demo-shop/tests/test_shop.py` passed **8/8** in real system Chrome. Playwright's bundled Chromium executable was unavailable, so the fixture used its system Chrome fallback. Screenshots, DOM captures and traces are retained in `runtime/artifacts/2026-10-11-golden-demo-local/`.

The checked-in `examples/demo-shop/tests/test_known_locator.py` intentionally retains the stale locator as the pre-repair demonstration. Therefore, the 8/8 result is for `test_shop.py`, not a claim that the unchanged example's entire suite passes. The corresponding project-workspace suite passed after the approved repair.

Platform UI screenshots are in `runtime/artifacts/2026-10-11-golden-demo-platform-ui/`:

- Dashboard and Project: `dashboard-desktop.png`, `project-desktop.png`
- Workspace result: `workspace-run-desktop.png`, `workspace-run-tablet.png`, `workspace-run-mobile.png`
- Failure workflow: `failure-workflow-desktop.png`, `failure-workflow-tablet.png`, `failure-workflow-mobile.png`
- Settings: `settings-desktop.png`

## Regression and review

- Full Python suite: **666 passed, 7 skipped**. Non-failing pytest warnings were emitted and not all independently triaged.
- Frontend unit tests, lint, typecheck and build passed. Vite emitted a large-chunk advisory; build succeeded.
- Ruff check and format check passed for all 21 changed Python files.
- Translation parity check passed: 25 namespaces, 2 languages, 2,859 keys.
- `git diff --check` passed.
- The reviewed Worker runs used the project-scoped claim filter; the unrelated queue count remained 200.
- Complete diff review found no blocking correctness or safety issue. It does not establish PostgreSQL behavior, cross-OS remote-worker traceback path mapping, or complete accessibility conformance.

No data reset, queue cleanup, credential changes, unrelated job processing, staging, commit or push was performed. Changes remain uncommitted.

## Reproduction and retained execution log

Use the existing seeded Demo and lifecycle records; do not reset or reseed destructively. Any temporary demo Worker must be scoped with `WORKER_PROJECT_IDS=proj_golden_shop_v1` and stopped after the intended run. Do not claim unrelated queue jobs.

The detailed request, analysis, plan, implementation, functional evidence, UI review, code review, fixes and regression records are in [`.ai-runs/2026-10-11-playwright-golden-journey/`](../../.ai-runs/2026-10-11-playwright-golden-journey/).
