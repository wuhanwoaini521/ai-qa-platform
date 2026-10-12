# AI QA Platform V2 overhaul — functional tests

## Automated checks

- `pnpm --filter @ai-qa/web test` — **137 passed, 0 failed**.
- `pnpm --filter @ai-qa/web lint` — passed.
- `pnpm --filter @ai-qa/web typecheck` — passed.
- `pnpm --filter @ai-qa/web build` — passed; existing Monaco worker bundle warning remains (>500KB).
- `uv run --no-sync pytest -q` — **669 passed, 7 skipped**, 44 warnings, 284.72s. `AI_QA_TEST_DATABASE_URL` was unset; PostgreSQL-only tests skipped. Tests use the suite's isolated per-test SQLite databases.
- `uv run --no-sync ruff check .` — passed.
- `uv run --no-sync ruff format --check .` — passed (403 files).
- `git diff --check` and JSON parsing of changed English/Chinese project/workspace locales — passed.

## Real browser workflow

- Real AI + Jev requirement analysis completed in sandbox `proj_ec58fd0e508e`; provider/model and result are visible in the saved task output.
- Bound case `tc_5cfd067c80a0` to `tests/test_login.py::test_login_invalid_password`; executed real TestRun `run_f99148bf55de`. Result `PASSED`, 1/1 case result persisted, 0 failed. Do not infer test success from the separate AI analysis task.
- Re-opened task-only Workspace context and verified status says task complete, case suffix `7C80A0`, and that no TestRun was created; English and Chinese copy checked.
- Project name/table and Run Dock exercised with real system Chrome through CDP. Screenshots are under `reports/v2/product-audit/screenshots/`.
- Projects and Workspace mobile pages each had 0 axe violations. Axe left color-contrast checks incomplete where transparent/pseudo backgrounds prevented automatic inference; sampled actual computed text/background pairs were manually checked and exceed 4.5:1.

## Environment notes

- `agent-browser` bundled Chrome cannot launch on macOS 12.7.6 because of a missing VideoToolbox symbol; an existing authenticated session using system Chrome via CDP port 9247 was used instead.
- Browser video recording unavailable: `ffmpeg` is not installed.
- A temporary locale syntax error (missing comma) during iteration was caught by Vite, corrected, JSON-validated, and followed by passing lint/typecheck/build/tests.
