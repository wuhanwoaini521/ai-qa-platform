# Plan

1. Apply a focused CSS fix in `workspace.css`: make result-panel headings sticky only at the breakpoint where panels are internally scrollable, and allow event titles to wrap inside their constrained grid cell.
2. Run the existing web tests, lint, and production build; run `git diff --check`.
3. Review the changed CSS as a second-pass reviewer, then inspect the real Workspace result in system Chrome at desktop and narrow widths, including a scrolled panel state if browser interaction allows.
4. Record actual checks and any limitations. Preserve all existing uncommitted files and user/browser/runtime state; do not commit or push.
