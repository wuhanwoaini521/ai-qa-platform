# dashboard-surface-layout

- run-date: 2026-11-06
- task-type: bug-fix
- scale: standard
## Original Request

修复总览页浏览器批注的六处问题：标题和项目背景、执行信号悬浮表面、最近执行记录错位和宽度、工作流对齐、项目工作区间距；修复后继续检查本页。

## Resolved Scope

Dashboard 展示与入口导航回归；复用已安装的 self-ui-style v0.9.0。额外修复同一 991px 视口下被旧 rail 断点挤压的项目选择器，以及多行行动按钮高度。无数据、业务判断、API、权限或执行行为改动。

## Repository / Branch / Initial Git Status

- 当前工作区：D:/code/self-github/ai-qa-platform，main。
- 既有改动：apps/web/package.json、pnpm-lock.yaml、pnpm-workspace.yaml 为此前用户确认的组件库升级；10 个既有 .ai-runs 未跟踪目录全部保留。
- 本次未提交、推送或管理用户的开发服务。
