# Functional Test

## Automated

- `.venv/bin/pytest apps/api/tests/test_browser_runtime.py -q` — 8 passed.
- `.venv/bin/pytest apps/api/tests/test_quality_discovery.py apps/api/tests/test_browser_agent_e2e.py apps/api/tests/test_agent_tasks.py -q` — 126 passed.
- `.venv/bin/ruff check apps/api/app/adapters/playwright/browser_runtime.py apps/api/tests/test_browser_runtime.py` — passed.
- `git diff --check -- apps/api/app/adapters/playwright/browser_runtime.py apps/api/tests/test_browser_runtime.py` — passed.

## Real navigation

Using the actual project `PlaywrightBrowserRuntime` with its default headless configuration, `https://www.uniqlo.com.hk/zh_HK/` now returns HTTP 200 and stays on the requested URL. The page title is `女裝,男裝,童裝&嬰幼兒服飾&配件 - UNIQLO香港及澳門`; body text is present.

## Tooling note

`uv run --package api pytest ...` was attempted first but dependency resolution tried to build the existing `nodejs-wheel-binaries` / `basedpyright` dependency and failed with the known macOS C++ `std::vector` build errors. No dependency or lockfile was changed. Tests and lint were run with the already-installed repository `.venv` instead.
