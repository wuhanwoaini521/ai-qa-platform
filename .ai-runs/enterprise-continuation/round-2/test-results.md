# Round 2 test results

Run date: 2026-10-16 · WSL2 Ubuntu 22.04 · project root `/home/hans/self-github/ai-qa-platform`

## Round 2 regression checkpoint

Current safety fix commit: `919cfcd fix(repair): make concurrent apply and recovery idempotent` on `agent/wsl-continuation` (not pushed). The full-suite results below predate the later duplicate-Apply CAS code change; the affected workflow suite was rerun after that change (see “Latest focused regression”). A final full regression remains required after the round's remaining work.

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

- Latest `uv run --no-sync pytest apps/api/tests/test_failure_workflow.py -q --no-header -p no:cacheprovider` → **46 passed, 1 warning in 64.41s**. Log: `logs/duplicate-apply-workflow-final.log`.
- Parameterized crash-state/recovery/stale-history/late-completion test → **2 passed** (`APPLYING`, `PATCH_READY`). It verifies stale `ROLLED_BACK` analysis state records no recovery event, then successful explicit recovery records one event, and late original completion cannot duplicate it; rollback restores original bytes.
- Concurrent duplicate-Apply case: exactly one guarded workspace write succeeds. The duplicate response may be a state conflict or idempotent `applied` response. `PATCH_READY` case passed **20/20** fresh pytest-process repetitions; subsequent stale-history guard change passed the 2-case parameterized test and full workflow suite.
- Injected `OSError("synthetic workspace write failure")` leaves source bytes and proposal `applied=false`, records `PATCH_APPLY_FAILED`, and keeps repair state `PATCH_READY`.
- `python scripts/task.py lint` → **PASS**: Ruff check/format (426 files), i18n parity (25 namespaces, 2 locales, 3022 keys), OpenAPI contract, ESLint. `git diff --check` passes.
- Independent review found a potential false-history race; code now refuses expected-state transitions if analysis source is missing/unknown/stale and does not append an event after a lost CAS. Final reviewer found no remaining issue and confirmed state CAS + event append share one repository transaction. PostgreSQL runtime unavailable; no real PG concurrency evidence.

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

- Full chain A and Discovery→Coverage on this round's final code; all-page interactive UI acceptance; end-to-end E2E suite beyond scoped real browser repair and Studio tests; actual Jev outage; interruption before source/proposal commit and verification-worker restart; PostgreSQL integration; remote Worker/Jenkins; Windows lane; final post-milestone full regression after any further modifications.
