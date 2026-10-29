@AGENTS.md

# Claude Code — Project Instructions

本文只包含 Claude Code 专属规则。通用工程规范由 `AGENTS.md` 统一维护，并通过上方导入生效；
本文不复制其内容，避免双份维护。二者冲突时以 `AGENTS.md` 为准；代码与文档冲突时以代码为准，
并在回复中指出冲突，不得静默忽略其中任何不可协商的不变量。

## Startup

- 核对仓库路径、分支、HEAD 与 `git status --short`，并在动手前确认与 `docs/agent-handoff.md` 最新条目一致。
- 阅读 `docs/ROADMAP.md` §0 与 `docs/QUALITY_GATES.md`。
- 保护已存在的未提交与未跟踪内容：不 reset / clean / stash，不自动 commit / push / merge。
- 按任务类型加载对应的项目 Skill（见下）。

## Project Skills

Claude Code 只自动发现 `.claude/skills/`，不会自动加载 `.agents/skills/`。
执行相关任务前先读取对应 `SKILL.md`，并按其流程执行：

- 功能 / 修复 / 重构 / 交付：`.agents/skills/project-delivery/SKILL.md`
- UI/UX 审查与体验改动：`.agents/skills/ui-ux-review/SKILL.md`
- 全项目健康检查与回归：`.agents/skills/full-project-validation/SKILL.md`

## Architecture

- 优先复用现有 `DecisionService`、Task Runtime、`BrowserRuntime`、仓储与 provider 注册表。
- 不新增第二套 Runtime / Agent / Provider，不新建旁路事件流或未持久化的执行循环。
- 架构变更必须来自可复现问题与实测证据，并经独立评审；先研究、再设计、后实施。
- 重大重构、框架引入、跨域事件/证据契约变更需要单独的人工批准。

## Validation

- 以真实执行证据为准：命令、环境与版本、退出码、证据路径。
- 判定只用 `PASS` / `PARTIAL` / `FAIL` / `BLOCKED` / `UNKNOWN`，标准见 `docs/QUALITY_GATES.md`。
- 未执行、被跳过或环境不可用的检查不得记为通过。
- AI 不决定产品 PASS/FAIL；测试判定以 Pytest 退出码为准，AI 只能分类、解释与建议。

## Research Context

架构研究资产不在 `main` 上：`docs/architecture-review/`、`engineering-knowledge/`、`.pi/team/`
位于 `research/autonomous-rd-2026-10-28`。读取方式：

```bash
git show research/autonomous-rd-2026-10-28:<path>
```

该分支是研究参考，不是重构实现分支。
