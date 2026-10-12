# Per-Case Run Results Visibility

- run-date: 2026-10-12
- task-type: ui-feature
- scale: standard
- risk: MEDIUM

## Original Request
用户反馈：一组八条 Case 在结果页和运行详情中无法区分；如果以后出现多条报错，也无法判断每条错误属于哪个 Case。

## Resolved Scope
在 Workspace Run 结果页及 Runtime 运行详情中逐条展示执行结果，并把每条结果与正确用例身份和错误证据关联。保持现有 Run 汇总、失败修复流程、运行事件和其他 Runtime 视图不变。仅修改 Web 展示/映射，不更改 API、数据模型、后端执行或持久化记录。

## Acceptance Criteria
1. Run 结果页显示所有已保存的 TestExecution；可唯一匹配时显示 Case 编号和标题，同时保留 pytest nodeid 作为准确技术身份。
2. 每条失败/错误的状态、错误信息和对应 Failure 入口与该 execution 关联，不把多条失败合并成一个无法归属的摘要。
3. Runtime 运行详情提供清晰的逐条结果视图；从 Workspace 结果页打开详情时直达该视图。
4. 未匹配或多重匹配时不猜测归属，明确展示 nodeid/映射歧义；无逐条结果时显示诚实的空态。
5. 结果列表在桌面、平板和约 360px 手机宽度下可读且无文档级横向溢出；中英文标签可用。
6. 相关模型/错误关联测试通过，现有结果与 Runtime 行为回归通过。

## Repository / Branch / Initial Git Status
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Branch: `main` tracking `origin/main`
- Initial status: `apps/web/src/features/requirements/RequirementsPage.tsx`, `TestCasesPage.tsx`, `WorkspacePage.tsx`, `workspace.css`, English and Simplified Chinese requirement/test-case locale files were modified; case/requirement selection models and tests, `.ai-runs/`, audit documents/evidence, and `runtime/runtime/` were untracked.
- These pre-existing changes and runtime/audit data are protected; do not stage, overwrite, clean, or include them in this task.
- No commit or push was requested.
