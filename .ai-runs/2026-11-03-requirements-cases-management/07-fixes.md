# 07 — Fixes applied during verification

Six defects were found by the checks, not by inspection. Each was fixed in the shared code, not worked around in the test.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `验收标准已保存` flashed and disappeared | Reset effect depended on `detailCriteria`, so the criteria change cleared its own feedback | Effect depends on `detailRequirementId` only; current text read via `detailCriteriaRef` |
| 2 | React warning: two children with the same key | Criteria list keyed by text; duplicate criteria lines are legal | Key `` `${index}-${item}` `` |
| 3 | Count/chip row rendered below the table (off-screen) | Summary block left at the old footnote position | Moved directly under the filter hint, above the results |
| 4 | Cases table: 7 headers vs 6 body cells (independent reviewers' B1) | Cases row merged 编号+名称 in one cell (pre-existing template) | ID cell + name cell, matching the other two tabs |
| 5 | Cases table 454px wider than its wrapper at 1280; 编号 column 799px | `.management-matrix-table th/td:first-child{white-space:nowrap}` prevented the identity cell from wrapping | `white-space:nowrap` restricted to `.management-trace-table` (where the first column really is a 32px toggle) |
| 6 | Cases filter row wrapped into an orphan line at 1440 | 所属需求 select sized to its longest option text | `.project-management-filter{max-width:200px}` |

Plus the design-review should-fixes listed in `05-ui-review.md` (chips padding, duplicate 清除筛选, duplicate drawer labels, chip focus token, facts layout, focus return).

All six were re-verified in the browser after the fix; `typecheck`, `lint`, 318 unit tests, `build` and `i18n_check` were re-run afterwards.
