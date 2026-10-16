# Round 2 · 实施日志（持续更新）

> 本轮目标（用户 brief）：把第一轮已验证的能力变成稳定、完整、好用的产品。
> 顺序：Studio Debug → AI/Jev 安全修复 → Discovery/Coverage → PostgreSQL/Worker → UI/UX → 最终全量回归。
> 本文件按里程碑追加，不要只把进度留在聊天上下文里。

## 里程碑 1 — Studio 真实调试能力验收与修复（完成）

**Git**：起点 `ca6bb09`（分支 `agent/wsl-continuation`），本里程碑提交见 `git log -1`。

### 已完成项

- 真实浏览器验收 Studio 调试全流程（打开文件 → 断点 → 命中 → 调用栈 → 局部变量 → 执行行高亮 →
  Step Over/Into/Out → Continue/Pause/Stop → 会话清理 → 可重复调试）。
- 追加失败场景验收（故意失败用例 `tests/test_known_locator.py:12`，断言 Python 异常被定位到源码位置）。
- 追加健壮性验收：连续点击 Debug 不产生多会话、未保存缓冲区在调试前先落盘。
- 修复 D6（debug 会话关闭接口非幂等）与 D7（Studio 深链打开错误文件）。
- 更新 `docs/agent-handoff.md` 与 `docs/ROADMAP.md` 无关内容；未改动远程 main。

### 测试证据

| 测试 | 命令 | 结果 |
| --- | --- | --- |
| Studio 调试主流程（真实浏览器） | `uv run --no-sync python /tmp/studio_debug_accept.py` | PASS 17/17 |
| Studio 调试失败/唯一性场景（真实浏览器） | `uv run --no-sync python /tmp/studio_debug_failure_accept.py` | PASS 14/14 |
| 后端 debug 会话服务 | `uv run --no-sync pytest apps/api/tests/test_debug_session_service.py -q` | 8 passed / 0 failed |
| 前端单测 | `pnpm --filter @ai-qa/web test` | 160 passed / 0 failed |
| 前端类型 | `pnpm --filter @ai-qa/web typecheck` | 0 errors |
| 前端 lint | `pnpm --filter @ai-qa/web lint` | 0 problems |

证据详情：`round-2/studio-debug-acceptance.md`；日志在 `round-2/logs/`（`*.log` 按 `.gitignore` 不入库）。

### 发现并修复的 Bug

- **D6（P2）** `DELETE /api/debug/sessions/{id}` 对已关闭会话返回 404 → 改为幂等，未知/他人会话仍 404。
- **D7（P1）** Studio 深链被上下文归一化覆盖，静默打开另一个文件（两处覆盖点，已修 + 3 个回归用例）。
- 误报澄清：D5（adapter 泄漏）为采样方式错误，非缺陷；Playwright `keyboard.type` 丢字符曾误判「保存失效」。

### 新增测试

- `apps/api/tests/test_debug_session_service.py::test_debug_close_is_idempotent_for_already_closed_sessions`
- `apps/web/tests/workspace-context.test.mjs`：3 个 `resolveCanonicalFile` 用例。

### UI 截图

`round-2/screenshots/`：`studio-debug-paused.png`、`studio-debug-second-run.png`、
`studio-debug-failure-paused.png`、`studio-debug-failure-finished.png`。

### 下一步命令

```bash
cd ~/self-github/ai-qa-platform
# 复跑 Studio 调试验收（需 API :8000 / Web :5173 已启动）
uv run --no-sync python /tmp/studio_debug_accept.py
uv run --no-sync python /tmp/studio_debug_failure_accept.py
```

### 当前阻断项

- PostgreSQL 集成测试：BLOCKED（WSL 无 PostgreSQL / Docker）。
- Worker / Jenkins 真实集群：NOT RUN（无集群）。

## 里程碑 2 — AI + Jev 修复安全闭环（进行中）

### 已验证并修复：AI/Jev Disabled 模式导致只读端点 500（D8，P1）

- 复现：`QA_AI_ENABLED=false JEV_ENABLED=false` 下 `/api/ai/status`、`/api/runs`、`/api/failures`
  均因依赖构造期间立即实例化 Provider 返回 500。
- 根因：`ProductionQAOrchestrator.__init__` 在构造时 eager 调用 `AIProviderRegistry.get_provider()`；
  Provider disabled 时 raise `RuntimeError: AI provider is disabled by the effective AppConfig`。
- 修复：在 `packages/qa-core/qa_core/orchestrator/orchestrator.py` 将 provider 改为首次访问再解析并缓存；
  非 AI 的诊断/服务组合可正常构造，实际 AI 调用仍显式失败，不会回退或伪报成功。
- 测试：真实禁用配置 OpenAPI 无参数 GET 路由扫查 43 条，无 5xx；`POST /api/decision/runtime-check`
  返回 `runtime=DISABLED`；隔离测试验证 status/runs/failures 为 200，实际 AI 分析诚实返回 502。
- 单测：`uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider`
  → 20 passed；ruff check + format 通过；独立 Reviewer 无发现。
- 证据：`round-2/ai-disabled-provider.md`。

### 仍待验收：修复审批安全矩阵

覆盖高/低置信度、AI/Jev 不可用、人工拒绝/批准、补丁应用成功/失败、精确验证成功/失败、
回滚、重复提交审批、会话中断共 11 类；拒绝与阻断场景必须验证正式文件逐字节不变；
批准与回滚场景必须验证文件、审计状态与执行记录一致。

## 里程碑 3 — Discovery → Coverage 闭环独立复验

待办：探索 → 功能发现 → Quality Map → 质量缺口 → 场景建议 → 用例 → 自动化绑定 → 执行 → 覆盖率更新；
检查项目/网站隔离、真实持久化、Feature 去重、刷新后一致性、Run 之间不混数据。

## 里程碑 4 — PostgreSQL / Worker

待办：评估在当前 WSL 中安全运行轻量 PostgreSQL 的可行路径；不可行则记录 BLOCKED 与原因。
Worker 用本地真实进程做集成验收（提交/状态/回传/超时/取消/异常恢复/并发），**不得冒充集群测试**。

## 里程碑 5 — 全站交互式 UI 验收 + P2 UI/UX 优化

待办：逐页真实交互（按钮、输入、保存、Tab、持久化、刷新、错误反馈、空态、加载、异常恢复、导航上下文），
关系图真实数据量下的布局/重叠/搜索/聚焦/性能，Studio 工作上下文连续性，Result 页成功/失败信息分层，
before/after 多分辨率截图。

## 里程碑 6 — 最终全量回归

待办：在最终代码上执行后端全量、前端全量、typecheck、lint、build、真实 Playwright E2E、
AI/Jev 验收、Studio 调试验收、Discovery→Coverage 验收，并更新 `test-results.md` 与 `final-report.md`。
**不得用早期结果代替最终回归。**
