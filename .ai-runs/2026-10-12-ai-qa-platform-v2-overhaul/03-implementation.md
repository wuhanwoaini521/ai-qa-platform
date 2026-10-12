# AI QA Platform V2 overhaul — implementation

## Delivered changes

- Added `apps/web/src/app/projectSelectionModel.ts` and its test. Duplicate project names now receive deterministic short ID suffixes; collisions expand the suffix. Unique names and persisted project data are unchanged. Applied the shared labels to navigation, Studio, project list, run/task/settings selectors, requirement/case forms, and Workspace context.
- Added `workspaceRunDockState` to `apps/web/src/features/workspace/workspaceRunModel.ts`. Persisted TestRun state takes precedence; AI/workflow task completion, failure, blocked, and cancellation remain distinct. A task-only completion explicitly says no TestRun was created. Added fallback from empty case display ID to a stable case ID suffix.
- Added responsive project-table scrolling in `ProjectsPage.tsx`, with a labelled/focusable region, localized keyboard description, ArrowLeft/ArrowRight/Home/End support, and a mobile swipe hint. At narrow viewports the table scrolls inside its card instead of widening the page.
- Added English and Chinese strings for the project-table hint and task-specific Run Dock states; adjusted Run Dock status spacing/colors.
- Added model tests for duplicate labels, task-vs-run precedence, task terminal states, and empty display-ID fallback.

## Deliberately unchanged

- No API endpoint, persisted schema, project name, AI/Jev setting, confidence threshold, or existing test script changed.
- Dashboard remains a measured loading candidate; the stats request is slow but the full visual delay was not isolated.
- Python LSP source was not changed. Active environment lacks the declared runtime modules, and a scoped `uv sync` dry-run showed unrelated shared packages would be removed. No dependency sync was run.
- Sandbox data was retained; no cleanup is claimed.

## Live workflow evidence

Sandbox `proj_ec58fd0e508e` used real configured OpenAI-compatible `deepseek-flash` and Jev analysis (3 risks, 4 scenario drafts, no fallback). Case `tc_5cfd067c80a0` is bound to `tests/test_login.py::test_login_invalid_password`; real TestRun `run_f99148bf55de` persisted 1/1 passed.
