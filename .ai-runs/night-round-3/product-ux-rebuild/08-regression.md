# Regression summary

## Passed

- Web unit suite: 147/147.
- Web TypeScript typecheck, ESLint, English/Chinese locale-key parity, and production build.
- Playwright 1.62.0 live run from Studio: selected node and shared Run Controls configuration reached the real API; 1/1 `test_search` execution passed.
- Real results, raw run log, runtime Browser events/frame, existing failure/repair inspection, and paused-debugger workflow.
- 768px and 360px stage navigation: five buttons present, stage rail does not scroll, page does not overflow; keyboard Tab moves focus to the next stage.
- 1440px paused debugger toolbar: 44px minimum control width and no button intersections.
- Demo source SHA-256 unchanged; no AI/Jev call and no Apply action.
- `git diff --check` on scoped source changes; separate trailing-whitespace scan on all 14 continuation text files.

## Not run / limits

- No backend test suite was run because this continuation changes only frontend code; the real API-backed run is included above.
- No axe automated audit or cross-browser/platform CI lane was run. Orca independent review is blocked as recorded separately.
- This is a focused Golden Demo Shop workflow, not a full-project regression; the pre-existing Python language-service warning and demo `favicon.ico` 404 remain.
- The build passes but retains the pre-existing large Monaco chunk warning.

**Scoped implementation state: functionally passing. Overall acceptance: PARTIAL** until the independent review gate is available.
