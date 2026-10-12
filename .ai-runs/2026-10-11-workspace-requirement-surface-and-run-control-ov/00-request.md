# Workspace requirement surface and run-control overlap

- run-date: 2026-10-11
- task-type: ui-feature (with a root-cause UI bug fix)
- scale: standard

## Original Request

“这一页崩溃了 修改一下，融合一下设计图，然后改一下我们的项目。” Supplied screenshot: QA Workspace requirement analysis, 1488×880.

## Resolved Scope

Fix the demonstrated Workspace requirement page obstruction, and refine its visual surface using the established cool QA-workbench direction. Preserve routes, data, translations, labels, and all existing controls/dialog behavior. Do not invoke AI, execute runs, or mutate business data.

## Repository / Branch / Initial Git Status

- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Branch: `main`
- Initial worktree had extensive modified and untracked files from prior work; preserve all existing changes. No staged changes observed.
- Target route: `/workspace/:projectId?stage=requirement&view=requirement`.
