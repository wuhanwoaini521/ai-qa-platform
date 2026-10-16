# Agent Guidelines for AI QA Platform

必须遵守 docs/ROADMAP.md 第 0 节不变量：AI 不决定 PASS/FAIL；不经人工批准不改代码；
确定性优先；外部写入先预览；无无人值守循环。不得新增第二套 Runtime/Agent/Provider；
复用现有 DecisionService、Task Runtime、BrowserRuntime。改动前先阅读相关文件，
遇到与文档不符的地方以代码为准并在回复中指出。

## Operational Principles

- **Platform Environment**: This repository runs on macOS, Linux and Windows. Developer tasks are cross-platform Python in `scripts/task.py`; the `scripts/dev|test|lint` files are bash shims over it.
- **Path Integrity**: Use the current repository path. Do not guess filesystem paths. Run `pwd` (`Get-Location` in PowerShell) before changing directories.
- **Runtime Management**: Use `mise`-managed runtimes (`python 3.13`, `node 24`, `uv`, `pnpm`).
- **Python Tooling**: Use `uv` for Python workspace management and dependency resolution.
- **Frontend Tooling**: Use `pnpm` for frontend workspace and package management.
- **Permission Safety**: Do not invoke `sudo` for project dependencies.
- **Git Safety**:
  - Do not force push (`git push --force` or `--force-with-lease`).
  - Do not run `git reset --hard` or `git clean -fd`.
  - Protect existing user changes.
  - Prefer clean, structured, incremental commits.
  - Run relevant tests and linters before committing.
- **Architecture Boundaries**:
  - `apps/web`: React + TypeScript + Vite frontend.
  - `apps/api`: FastAPI domain services & REST endpoints.
  - `apps/worker`: Long-running QA jobs and execution workers.
  - `packages/qa-core`: Core testing contracts, fake test runners, diagnostic interfaces.
  - `packages/project-model`: Shared domain models and schemas.
  - `packages/integrations`: Connectors and integrations (future TestRail, GitHub, etc.).
  - `runtime/`: Editable workspaces, projects, and runtime artifacts (never commit runtime data).

## Playwright Version

- Playwright-based tests must use Playwright 1.62.0. Do not install or run Playwright 1.63.0 or newer.

## **长期 Agent 开发交接规则**

- 任何超过单次简单修改的开发任务，必须在仓库中维护 `docs/agent-handoff.md`，并在每个可验证里程碑完成后更新。
- 必须记录当前 Git Commit、实际完成内容、测试证据、未解决问题、阻断因素和下一步执行命令。
- 任务中断或模型上下文即将耗尽时，优先保存交接状态。
- 后续 Agent 必须先阅读该文件并核对 Git 与真实测试结果，再继续开发。
- 禁止把聊天记录或未跟踪的临时日志作为唯一的进度来源。
