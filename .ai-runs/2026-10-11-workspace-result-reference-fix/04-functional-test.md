# Functional Testing

## Automated checks

- `pnpm --filter @ai-qa/web test` — **PASS**, 107 tests / 0 failures. Includes terminal-state and repair-notice model coverage.
- `pnpm --filter @ai-qa/web typecheck` — **PASS**.
- `pnpm --filter @ai-qa/web lint` — **PASS**.
- `pnpm --filter @ai-qa/web build` — **PASS**. Vite emitted the existing large-chunk advisory for Monaco; build completed successfully.
- `uv run python scripts/i18n_check.py` — **PASS**, 25 namespaces, 2 languages, 2,860 keys.
- `git diff --check` — **PASS**.

## Browser functional verification

Ran the application UI in Vite with Playwright and deterministic mocked API responses (no live API/database writes). Verified the actual Workspace result route:

- PASSED displays localized `运行通过` and the neutral “no repair needed” message; it is not labeled blocked.
- FAILED displays localized `运行失败` and preserves the missing-Failure repair blocker.
- Desktop 1536px, tablet 820px, mobile 390px, and narrow mobile 360px: no horizontal overflow; result panels and activity list have no nested vertical scrolling; no browser console errors. Tablet stress fixture with 24 activity rows flowed to 1,445px without a max-height constraint or overlap.
- Saved screenshots under `/tmp/aiqa-workspace-result-{desktop,desktop-failed,tablet,mobile-390,mobile-360}.png` during verification.

An initial expanded browser assertion still expected PASSED for the failed-state fixture; the UI correctly returned FAILED. The temporary test harness assertion was made status-aware, then the complete browser matrix passed. No product-code defect was found in that assertion failure.