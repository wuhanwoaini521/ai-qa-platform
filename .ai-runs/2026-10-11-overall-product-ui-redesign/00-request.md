# overall product UI redesign

- run-date: 2026-10-11
- task-type: ui-redesign
- scale: standard
## Original Request
根据提供的产品设计图，整体调整 AI QA Platform 的 UI；助手作为总设计师和前端开发工程师，以参考产品为对标进行改造。

## Resolved Scope
- 全产品视觉系统与核心页面的轻量级整体改造，保留现有路由、交互、工作区信息架构、浅色/深色主题及已有响应式行为。
- 以参考图提炼风格，不复刻其他产品的业务结构：轻量分组导航、细线分隔、紧凑数据卡与克制色彩；强调执行决策时的居中聚焦弹窗；深色主题保留为开发/分析工作流可用外观。
- 改动优先落在共享 design tokens、壳层与共享卡片/对话框，再验证 Dashboard、Workspace、列表/质量/设置等代表页并扩展至关键路由。
- 不触发任务、执行用例、AI/供应商操作或修改业务数据；不动依赖定义和锁文件。

## Repository / Branch / Initial Git Status
- Repository: `/Users/hans/Code/github/ai-qa-platform` (current workspace path; branch and commit not independently reset).
- Worktree already contained extensive unrelated user changes from prior tasks. Preserve them; do not stage, commit, clean, or revert.
- Existing worktree includes prior workspace layout, automation editor, AI classification and test changes. Those are outside this task unless a style change touches the same shared file; make only scoped edits.
- Application was already running at `127.0.0.1:5173` and API `127.0.0.1:8000`; use only for read-only visual inspection.
