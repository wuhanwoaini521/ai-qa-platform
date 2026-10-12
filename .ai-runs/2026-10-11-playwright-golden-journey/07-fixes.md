# Fixes

## Evidence-driven fixes applied
1. **Structured-analysis output handling:** two real provider attempts established that output limits can arrive with non-empty JSON prefixes and gateway `finish_reason=stop`. The shared streaming executor now classifies output-token exhaustion as `output_limit` before schema validation. Lifecycle context was shortened, output allowance raised within the configured request path, preservation instructions clarified, and DeepSeek reasoning mode disabled for the affected lifecycle/browser-planning calls. Regression tests cover truncated non-empty output.
2. **Page Object repair targeting:** real traceback/evidence showed the failed locator was in `pages/shop.py`, not the pytest node file. Repair generation now searches only policy-allowed traceback candidates, requires one exact AST locator call, and records the actual target path. Apply still requires the reviewed proposal, trusted Jev/Playwright evidence and an unchanged source hash. Targeted tests cover candidate filtering, Page Object selection/application and rejection of no-op patches.
3. **Worker queue isolation:** the pre-existing queue contained 200 jobs of unknown intent. Added project allowlisting end-to-end and used `WORKER_PROJECT_IDS=proj_golden_shop_v1` for the demo Worker; a broader/global Worker was not started.
4. **Demo behavior/browser availability:** added shop filters/cart transitions and system Chrome/Edge fallback when the bundled Playwright executable is missing, without changing external dependencies or bypassing browser tests.

## Review follow-up
- Independent diff review found no additional blocking issue requiring a code change. Unsupported/incomplete branches and environment limits are recorded in the acceptance report; they were not simulated or mislabeled as passed.
