# Regression

## Coverage

- Workspace run presentation model: terminal outcomes, active statuses, missing Failure record, existing Failure/AI evidence, cancelled and not-yet-started states.
- Workspace Run result route: PASSED and FAILED render states; desktop, tablet, mobile and narrow-mobile layouts; long activity list at tablet width.
- Frontend regression: all web tests, TypeScript typecheck, ESLint, production build, translation parity, and `git diff --check`.

## Results

- All automated frontend checks passed; web suite: 107 passed, 0 failed.
- Playwright mock-API UI matrix passed at 1536×864, 820×1024, 390×844, and 360×800, with both PASSED and FAILED desktop cases. The 24-row tablet activity stress case remains in page flow.
- No horizontal overflow, internally scrolling result panels/activity list, browser console errors, or regression found.
- No API/database changes were made. Live backend integration was not rerun because this change is confined to frontend presentation; browser responses were deterministic mocks to avoid modifying stored data. Python/backend suites were not rerun for this scoped frontend change.
- Build completed with the existing large-chunk advisory for Monaco; no build failure.