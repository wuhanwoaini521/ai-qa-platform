# Functional Tests — Per-Case Run Results Visibility

## Automated
- `node --experimental-strip-types --test apps/web/tests/test-execution-results-model.test.mjs`: **5 passed** (unique match, unmatched fallback, ambiguous mapping, multiple failure/execution/run associations, empty results).
- `pnpm --filter @ai-qa/web test`: **127 passed, 0 failed**.
- `pnpm --filter @ai-qa/web lint`: passed.
- `pnpm --filter @ai-qa/web typecheck`: passed.
- `pnpm --filter @ai-qa/web build`: passed.
- `git diff --check`: passed.

## Browser
- Reproduced real Golden Demo Run `run_1a8bf6d5a021`: all 8 saved executions display; 7 exact case bindings show Case ID/title and the one historical binding mismatch safely displays its pytest node name and full nodeid. The real failed `TC-002` shows its own error and Failure action.
- From Workspace, “Run details” opened the Results tab with the same eight rows. The global Runs page selected this Run and opened on Results. Existing Flow remains selectable and truthfully shows that this standalone Run has no TaskStep DAG.
- In an isolated local-browser network mock only (no backend writes), changed a passing execution into a second failed case. Workspace and Runtime displayed both errors separately under `TC-002` and `TC-004`; the mock was removed and the page reloaded. The underlying Run returned to the real 7-passed/1-failed result.
- Checked 1524×900, 768×1024, 390×844 and 360×800. All tested pages had `documentElement.scrollWidth === clientWidth`. Light/dark and English/Chinese labels were checked.
- axe-core 4.12.1 on `.run-execution-results` and `.rt-run-results`: **0 violations, 0 incomplete items**. Browser console error check was empty.

Screenshots are temporary local evidence: `/tmp/per-case-results-workspace-1524.png`, `/tmp/per-case-runtime-1524.png`, `/tmp/per-case-runtime-768-two-failures.png`, `/tmp/per-case-runtime-390-two-failures.png`, `/tmp/per-case-workspace-360-two-failures.png`, `/tmp/per-case-workspace-1524-dark-two-failures.png`, `/tmp/per-case-runs-page-1524-actual.png`, `/tmp/per-case-runs-page-390-actual.png`.
