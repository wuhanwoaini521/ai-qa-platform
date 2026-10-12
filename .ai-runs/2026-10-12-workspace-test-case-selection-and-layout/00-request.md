# Workspace Test Case Selection and Layout

- run-date: 2026-10-12
- task-type: ui-feature
- scale: standard
## Original Request
用户反馈用例页面格式异常，而且不能切换到其他 Case、只能看到当前 Case，并附了 Workspace 用例页截图。

## Resolved Scope
修复 Workspace「用例」阶段只显示当前用例、无可见切换入口的问题；整理该阶段的当前用例工具栏，使当前用例身份、切换控制与新建操作有清晰层级。保留现有详情、自动化绑定、用例创建、工作区/非工作区路由和上下文语义。

## Repository / Branch / Initial Git Status
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Branch: `main` (tracking `origin/main`)
- Initial tracked changes already present before this task: `RequirementsPage.tsx`, `workspace.css`, and English / Simplified Chinese `requirements.json` from the previous requirement-visibility task.
- Pre-existing untracked content: `.ai-runs/`, `apps/web/src/features/requirements/requirementSelectionModel.ts`, `apps/web/tests/requirement-selection-model.test.mjs`, `docs/audits/full-product-evidence/`, audit Markdown files under `docs/audits/`, and `runtime/runtime/`.
- No changes from the previous task were staged, overwritten, or included in this task's code scope.
