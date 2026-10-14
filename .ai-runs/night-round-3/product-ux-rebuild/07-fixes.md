# Review follow-up

- Replaced the Run Case/File tooltips with target-only wording so the same Studio component does not claim the Run Controls configuration when used without a workspace `runConfig` (standalone mode).
- Kept debugger action padding intact by excluding `.studio-tool` from the global icon-only zero-padding selector; final browser geometry reports 44px minimum and zero overlaps.
- Re-ran the full browser acceptance after these final changes; the configured test passed and final screenshots/JSON were refreshed.
- No additional code change was justified by the second-pass review. The Python language-service message, demo favicon 404, and independent-review gate remain documented rather than hidden or worked around.
