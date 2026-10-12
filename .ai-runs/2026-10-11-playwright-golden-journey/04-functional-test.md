# Functional Test

## Environment and data safety
- API `127.0.0.1:8000` and Vite `127.0.0.1:5173` were used. API readiness reported SQLite and storage healthy. Docker/PostgreSQL were unavailable.
- Initial inspection found 200 queued jobs of unknown intent and no registered Worker. An empty-scope claim probe returned no job. A Golden Demo-only Worker was used; after testing it was stopped and its registry state is `OFFLINE`. All 200 unrelated queued jobs remain untouched.
- Golden Demo project `proj_golden_shop_v1` and requirement `req_golden_shop_v1` were seeded once without resetting data. There are 11 cases after real lifecycle adoption.

## Real provider lifecycle
- Configured AI was `openai-compatible/deepseek-flash`; Jev was `jev-1.13.0`. Runtime readiness and persisted provider/decision records were inspected; no credential values were displayed.
- Two real AI lifecycle failures were retained: one incomplete structured response at 6,000 output tokens (`INVALID_STRUCTURED_OUTPUT`) and a second 10,000-token cap correctly recorded as `output_limit`. The output-limit classification, duplicate-context size and DeepSeek reasoning mode were corrected; both original records remain.
- Successful real analysis: `6afe7c795b164e3b96f60b2f363b791b`, 11 scenarios, fallback false. Jev selected `RISK-001` (confidence 0.73) and `SCN-004` (0.81), both without fallback. Successful AI usage was 5,999 input / 2,792 output tokens.
- Adopted the 11 designs and two new scenarios (`SCN-010`, `SCN-011`) while preserving existing cases. Human-reviewed and activated automation binding `bind_900a33d481f9`. Workspace validation was clean; pytest collection found 10 tests without errors.

## Worker execution and repair
- Project-scoped generated-test run `run_1b850d74579d` passed.
- Full automated Golden Demo suite run `run_92a613c81881` passed **10/10**. The Worker was stopped afterward. No unrelated queued job was claimed.
- Locator failure `fail_16d594548ce0` was retained. Initial Worker evidence lacked page evidence; a local rerun supplied it. Real diagnosis proposed an exact `pages/shop.py` Page Object locator change; Jev selection and Playwright verification succeeded. Human approval applied the patch, and exact-case run `run_eb4ccaf35252f5440324e6f938cbeb7d` passed with workflow state `VERIFIED`.
- Wrong-oracle failure `fail_703a5695edf1` was diagnosed as an incorrect test oracle; repair state was `NOT_APPLICABLE` and the business assertion was not weakened. A controlled catalog-price mismatch was diagnosed under `fail_cbf1a3980f8e`; the catalog was restored byte-for-byte and `test_add_to_cart` passed.

## Real browser-agent evidence
- Strong no-results journey `c9fc99b1d89f49af93c418c57c22f114` submitted `qa-empty-state-20261011` and verified “No products found. Try another search.” Two real Jev decisions were recorded without fallback.
- An earlier blocked task remains retained. A separate task that stopped after one action is weaker evidence and is not counted as successful search submission.

## UI and regression
- Chrome review covered dashboard, project, Workspace run/failure, and settings pages. Workspace run/failure layouts were checked at desktop, tablet and mobile sizes. Screenshots are in `runtime/artifacts/2026-10-11-golden-demo-platform-ui/`.
- `examples/demo-shop/tests/test_shop.py` passed **8/8** in system Chrome because bundled Chromium was absent; screenshots/DOM/traces are under `runtime/artifacts/2026-10-11-golden-demo-local/`. The checked-in `test_known_locator.py` deliberately retains its stale locator as the pre-repair failure fixture, so this is not a claim that the unmodified local demo suite is all green. Its project-workspace counterpart passed after approved repair in the 10/10 Worker suite.
- Full Python suite: **666 passed, 7 skipped**. Frontend tests, lint, typecheck and build passed. Python Ruff check/format passed for all 21 changed Python files. `git diff --check` passed.

## Incomplete / blocked branches
- Human rejection is not exposed by the inspected failure-workflow UI/API; that branch was not exercised.
- Retry-failure coverage remains incomplete.
- PostgreSQL validation was not run because Docker/PostgreSQL were unavailable. A tablet direct-refresh-specific check was not independently established.
