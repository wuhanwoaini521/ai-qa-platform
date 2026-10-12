# Regression

- `pnpm --filter @ai-qa/web test`: **107 passed, 0 failed**.
- `pnpm lint`: **passed** (Python Ruff/format, i18n parity, frontend ESLint).
- `pnpm typecheck`: **passed**.
- `pnpm build`: **passed**; existing Monaco chunk-size advisory remains.
- Real-browser regression: passed the existing Workspace results view with PASSED and FAILED states, manual-analysis/run-details/rerun controls still present, event filtering, activity scroll/reachability, and 1440/1024/820/390/360 responsive surfaces. No code contract or API behavior changed.
- Database/runtime: API service was not started, no Worker was started, and browser API calls were deterministic mocks; no database or runtime data was written.
- `git diff --check`: passed. No files staged, committed, or pushed. Pre-existing unrelated worktree changes were preserved.
- Not run: backend test suites (the change is CSS-only and has no API/data impact), cross-platform CI, and PostgreSQL. Browser-based responsive behavior was verified locally in Chrome.