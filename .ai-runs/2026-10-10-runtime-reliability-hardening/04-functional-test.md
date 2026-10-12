# Functional Test Log

## Baseline, 2026-10-10

- `pnpm install --frozen-lockfile`: PASS (pnpm 12.5.1).
- `uv sync --all-packages --locked`: FAIL in this host while building `nodejs-wheel-binaries==24.19.0` (transitive from basedpyright); compiler failure in bundled Node/ncrypto. No repo dependency files changed.
- `uv sync --all-packages --locked --offline --no-install-package basedpyright --no-install-package nodejs-wheel-binaries`: PASS for remaining workspace packages; basedpyright intentionally unavailable.
- `pnpm test`: FAIL, 630 passed / 17 failed / 6 skipped (360.09 sec); detail and triage in baseline audit.
- `pnpm --filter @ai-qa/web test`: PASS, 104 passed.
- `pnpm lint`: FAIL, 9 Ruff errors.
- `pnpm build`: PASS, Monaco ~4 MB chunk warning.
- `GET /api/health/live`, `GET /api/health/ready`, Web `/`: PASS on locally started documented dev servers.
- Authenticated live `/api/ai/status`: PASS, real AI streaming health; no fallback.
- Authenticated live `/api/decision/runtime-check`: PASS, real Jev CONNECTED/READY.
- Safe endpoint override reproduction: FAIL as expected; environment host overrides were ignored by literal YAML URLs.
- PostgreSQL, real browser binary, Windows/Linux remote CI: NOT AVAILABLE / NOT RUN at baseline.

## Final Verification, 2026-10-10

- `uv run pytest -q`: **PASS**, 658 passed, 7 skipped, 44 warnings (279.60s). Warnings were non-fatal collection/runtime fixture/sandbox warnings. PostgreSQL-only checks were not run against a live PostgreSQL service.
- `pnpm lint`: **PASS** — Ruff, Ruff format check (391 files), i18n parity (25 namespaces / 2 languages / 2,850 keys), ESLint.
- `pnpm --filter @ai-qa/web test`: **PASS**, 104 passed.
- `pnpm --filter @ai-qa/web typecheck`: **PASS**.
- `pnpm --filter @ai-qa/web build`: **PASS**; existing Monaco bundle-size warning remains.
- Real AI + Jev locator-repair acceptance `test_live_ai_jev_locator_auto_repair_and_exact_rerun`: **PASS** (real-provider acceptance; actual exact-node rerun required for success).
- Real browser/UI acceptance `AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1 QA_AI_BASE_URL=https://api.deepseek.com uv run pytest -q -s --tb=short apps/api/tests/test_live_locator_repair_acceptance.py::test_live_ai_jev_failure_repair_through_browser_ui`: **PASS**. It exercised real AI and Jev in system Chrome, checked desktop/tablet/mobile horizontal overflow, and validated safe UI states. A low-confidence Jev response was blocked without patching/rerunning and the UI displayed the threshold reason; another real run selected a Jev candidate and entered verification. The acceptance also verifies the terminal outcome and rollback/verified messaging.
- `git diff --check`: **PASS**.
- PostgreSQL/Docker lane: **BLOCKED / NOT RUN** (local Docker/PostgreSQL unavailable).
- Full Worker acceptance against the existing runtime DB: **BLOCKED / intentionally not run**; its 200 queued jobs remain untouched. Worker unit/concurrency/lifecycle tests ran in the full suite.
- Bundled Playwright Chromium installation: **BLOCKED** on macOS 12 (unsupported by Playwright); UI/browser acceptance used installed system Chrome.
- Python language-server integration: **SKIPPED / BLOCKED** because basedpyright/Node dependencies were unavailable from the failed locked Node binary build.
- Existing API/Web development runner remains active. No Worker was started; existing data and credentials were preserved.
