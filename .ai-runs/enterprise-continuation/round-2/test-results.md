# Round 2 test results

Run date: 2026-10-16 · WSL2 Ubuntu 22.04 · project root `/home/hans/self-github/ai-qa-platform`

## Round 2 regression checkpoint

Current code commit: `02210de fix(discovery): persist quality map before terminal status` on `agent/wsl-continuation` (not pushed); Jev outage regression was committed separately at `81550e6`. The 823-pass full-suite result below predates both duplicate-Apply CAS and Discovery finalization changes; a final full regression remains required after remaining work.

| Scope | Command | Result |
|---|---|---|
| Full backend | `uv run --no-sync pytest -q --no-header -p no:cacheprovider` | **823 passed, 9 skipped, 55 warnings, 574.83s**. Log: `logs/backend-round2-baseline.log`. Warnings include existing Pytest collection warnings for `Test*` models/ORMs, Python sqlite datetime adapter deprecation, and a generated fixture `SyntaxWarning`. |
| Focused failure repair | `uv run --no-sync pytest apps/api/tests/test_failure_workflow.py apps/api/tests/test_runs_and_failures.py apps/api/tests/test_live_locator_repair_acceptance.py -q --no-header -p no:cacheprovider` | **102 passed, 3 skipped, 5 warnings, 103.23s**. |
| D8 disabled-provider regression | `uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider` | **20 passed**; Ruff check and format check pass. |
| Repository lint/contracts | `python scripts/task.py lint` | **PASS**: Ruff check, format, i18n 25 namespaces / 2 locales / 3022 keys, OpenAPI check, ESLint. |
| Web unit tests | `pnpm --filter @ai-qa/web test` | **160 passed, 0 failed**. |
| Web typecheck | `pnpm --filter @ai-qa/web typecheck` | **PASS**, no errors. |
| Web production build | `pnpm --filter @ai-qa/web build` | **PASS**, Vite built in 38.35s. Existing warning: `MonacoEditorPane` JS chunk 4,031.76 kB (1,043.98 kB gzip); do not claim bundle optimization complete. |

## Latest focused regression after duplicate-Apply CAS and recovery fixes

- Latest `uv run --no-sync pytest apps/api/tests/test_failure_workflow.py -q --no-header -p no:cacheprovider` → **47 passed, 1 warning in 59.51s**. Earlier equivalent run log: `logs/failure-workflow-jev-outage.log` (68.28s).
- Parameterized crash-state/recovery/stale-history/late-completion test → **2 passed** (`APPLYING`, `PATCH_READY`). It verifies stale `ROLLED_BACK` analysis state records no recovery event, then successful explicit recovery records one event, and late original completion cannot duplicate it; rollback restores original bytes.
- Concurrent duplicate-Apply case: exactly one guarded workspace write succeeds. The duplicate response may be a state conflict or idempotent `applied` response. `PATCH_READY` case passed **20/20** fresh pytest-process repetitions; subsequent stale-history guard change passed the 2-case parameterized test and full workflow suite.
- Injected `OSError("synthetic workspace write failure")` leaves source bytes and proposal `applied=false`, records `PATCH_APPLY_FAILED`, and keeps repair state `PATCH_READY`.
- `test_jev_upstream_outage_blocks_auto_repair_before_diagnosis_or_write` → **1 passed**: real `JevDecisionProvider`/`DecisionService` HTTP request to loopback 503 produces `upstream_error`; automatic failure repair is blocked before diagnosis/write. AI readiness is stubbed solely to isolate Jev; no real credentials/external network.
- `python scripts/task.py lint` → **PASS**: Ruff check/format (426 files), i18n parity (25 namespaces, 2 locales, 3022 keys), OpenAPI contract, ESLint. `git diff --check` passes.
- Independent review found a potential false-history race; code now refuses expected-state transitions if analysis source is missing/unknown/stale and does not append an event after a lost CAS. Final reviewer found no remaining issue and confirmed state CAS + event append share one repository transaction. PostgreSQL runtime unavailable; no real PG concurrency evidence.

## Latest Discovery finalization regression

- Latest `uv run --no-sync pytest apps/api/tests/test_quality_discovery.py -q --no-header -p no:cacheprovider` → **62 passed in 32.04s** after finalization ordering, stop/cancellation shielding, projection-error handling, no-worker stop/resume reservation, and deterministic test-only `DecisionService.ask_score` stubbing.
- Latest targeted repeat-cancellation/no-worker-stop/projection-failure tests → **2 passed**; fixture Jev fallback pair → **2 passed in 3.94s**. An earlier whole-file attempt failed two fixture tests because `ask_score` still contacted real Jev; inspection confirmed the fixture patched `choose` only. Added deterministic `ask_score` fixture so unit/integration tests do not depend on network; assertions unchanged; rerun passed 62/62.
- Latest `python scripts/task.py lint` and `git diff --check` both PASS on the current diff: Ruff check, 426 files format, i18n parity (25 namespaces/2 locales/3022 keys), OpenAPI sync, ESLint.
- Real local-browser Discovery with real providers: `AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 uv run --no-sync pytest apps/api/tests/test_live_enterprise_journey.py::test_real_local_discovery_preserves_target_and_project_scope -v --no-header -s -p no:cacheprovider -o addopts=` → **1 passed in 11.09s**. Browser target was `127.0.0.1`; run `qd_977825b54a5b44a9` / project `proj_983fdbbf552c`; status `COMPLETED`, 2 states / 1 action / 3 features. Real AI `openai-compatible` / `mimo-v2.6-flash` (1,017 input / 279 output tokens); Jev `jev-1.13.0` (1 decision, 0 fallback). Test asserts terminal response includes persisted quality map, coverage, and explicit workspace scan status. Log: `logs/live-discovery-finalization.log`.
- Independent re-review: no correctness finding in repeated-cancellation close handling, finalizer reservation cleanup, no-worker stop/resume race, or deterministic Jev fixture isolation. Reviewer notes close-session exceptions propagate promptly (do not hang); retained existing error propagation. Limit: locks/coordination are process-local; PostgreSQL/multi-process concurrency untested. This validates exploration → Quality Map, not gap → generated cases → binding → execution → coverage refresh.

## Real AI/Jev

- Real API high-confidence acceptance: `test_live_ai_jev_repair_requires_approval_and_exact_rerun` → **1 passed in 36.30s**. AI provider and Jev both real, no fallback; human approval, exact pytest node rerun passes. Full evidence and parameters: `ai-jev-live-acceptance.md`.
- Real browser high-confidence acceptance: `test_live_ai_jev_failure_repair_through_browser_ui` → **1 passed in 46.51s**. Actual React UI, explicit human approval, real patch, exact verification PASSED, rollback restores original source. Screenshots in `screenshots/failure-ui/`.
- Low confidence `0.6` observation: safely blocked, no write. A separate latest live rerun after changing screenshot capture timing was also safely blocked because the real AI provider returned `AI provider unavailable`; it made no proposal/write. Do not treat that blocked attempt as full-chain success.
- The full successful browser run happened immediately before the screenshot-capture timing-only test edit; the final test version was then rerun and fail-closed on provider outage. The provider outage is an upstream reliability risk.

## Disabled provider / environment

- With `QA_AI_ENABLED=false JEV_ENABLED=false`, real API sweep of 43 OpenAPI GET routes returned 0 HTTP 5xx; the disabled Jev runtime check reports DISABLED, not connected. AI analysis remains explicit HTTP 502 rather than silent fallback. See `ai-disabled-provider.md`.
- WSL has no Docker/PostgreSQL (`docker`, `psql`, `pg_isready` missing); PostgreSQL integration lane **BLOCKED**. Remote Worker/Jenkins cluster **NOT RUN**.
- Playwright 1.62.0 bundled Chromium works. CJK Noto font installed only under user-local `~/.local/share/fonts/` for screenshot legibility.

## Not yet verified

- Remaining: remote Jev outage, interruption before source/proposal commit and verification-worker restart; PostgreSQL integration; remote Worker/Jenkins; Windows lane; broader page-by-page UI interaction and graph visual-density review.

## D5 final regression and browser evidence (2026-10-16)

- `uv run --no-sync python scripts/task.py test` on the current D5 tree: backend **829 passed, 9 skipped, 55 warnings in 431.17s** (captured in `logs/backend-d5-final.log`); the complete scripted task took about 461s with frontend checks. The 9 skips include opt-in live-provider/browser tests and PostgreSQL tests. Frontend: **160 passed**, typecheck, ESLint, production build PASS (3,405 modules; existing Monaco chunk 4,031.76 kB / 1,043.99 kB gzip). PostgreSQL lane was explicitly skipped because no `AI_QA_TEST_DATABASE_URL` PostgreSQL server was available.
- `uv run --no-sync python scripts/task.py lint`: **PASS**; Ruff check, 426 files formatted, i18n 25 namespaces / 2 languages / 3,025 keys, OpenAPI contract current, ESLint.
- Real C-chain API acceptance succeeded with real `openai-compatible` AI (`mimo-v2.6-flash`), real Jev (`jev-1.13.0`), local browser discovery, AI-generated requirement/case, human-authored Playwright test, active binding, actual browser `TestRun` PASSED and refresh coverage VERIFIED. Latest successful evidence is printed in `logs/live-discovery-coverage-retry.log`; one run used test-process timeout 60s/retries 1. Default 20s timed out on an earlier attempt.
- Real web UI Playwright action also succeeded once: the Refresh Coverage button was clicked, success feedback shown and feature remained VERIFIED; desktop/tablet/mobile screenshots are `screenshots/discovery-coverage-{before-refresh,after-refresh,tablet,mobile}.png`. Mobile coverage table is internally horizontally scrollable with no document overflow. This successful run preceded the latest stricter response/status assertions in the opt-in test harness.
- Do not retry real AI tonight: two later opt-in attempts failed before the UI phase with `AIProviderError: AI Provider 在 20 秒内未返回结果（已重试 0 次）。` despite one shell attempt setting 60s. `get_config().ai.timeout_seconds` outside pytest reported 60.0; cause of the effective 20s failure remains unresolved. Latest combined test harness now asserts POST refresh HTTP 200/no API errors and uses repo-root per-run screenshot paths, but that strengthened harness was not rerun after the upstream failures; treat as **NOT VERIFIED**, not as a green test.
- Independent reviewer findings on the combined test harness were addressed: repository-root/per-run screenshot destination and direct refresh-response assertion. `TestRunRepository.list_runs` orders `created_at DESC`, which justifies selecting the first matching run; selection is timestamp-newest within that run. Project/team ACL remains a platform-wide gap; this endpoint restricts refresh to requester or ADMIN only. Final independent reviewer re-check found no blockers; provider outages remain an explicit external limitation.
