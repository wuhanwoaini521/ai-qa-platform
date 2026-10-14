# Implementation and acceptance plan

1. Extend the existing embedded Studio run path to carry the workspace run config into ordinary test-run creation; retries continue reusing the original run config. Preserve the current explicit test / selected-case / active-file target precedence. Present target-specific labels so the Play button accurately describes the selected-case binding or active file.
2. Hide only the embedded Studio's project selector; the app shell remains the project-selection control. Preserve standalone Studio behavior.
3. At tablet widths, allow the five journey stages to shrink into available width. At narrow widths, use a compact five-step rail that shows every stage without horizontal scrolling while retaining full accessible labels and status.
4. Add/extend a small run-target/config unit test where useful, then run the frontend suite, lint/typecheck/build, and real-browser interaction checks with pinned Playwright 1.62.0.
5. Capture after screenshots and interaction/layout evidence at 1440, 768, and 360px. Traverse a read-only real demo test through persisted run results, logs/browser evidence, and existing failure/debug/repair UI without invoking AI/Jev or applying a repair.
6. Review the scoped diff and commit only product source as one feature commit, then commit only this subfolder's UX report/evidence separately. Leave inherited changes unstaged. Report blocked independent review/platform lanes honestly; do not claim them passed.

## Acceptance seams

- UI seam: real authenticated workspace in `Northstar · Golden Demo Shop`.
- Execution seam: real `POST /api/runs` from the embedded Studio, with request payload captured and actual `tests/test_shop.py::test_search` result verified.
- Layout seam: viewport metrics and keyboard-visible stage navigation at 1440×1000, 768×1024, and 360×800.
- Repair safety seam: inspect an existing failure and enter debugger/AI Repair context, but do not call AI/Jev or execute Apply.
