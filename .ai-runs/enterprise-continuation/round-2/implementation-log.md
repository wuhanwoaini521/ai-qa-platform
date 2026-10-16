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

### 已完成：真实 AI + Jev 失败修复闭环（API + 真实浏览器）

- API live acceptance：1 passed；真实 AI `openai-compatible` / `mimo-v2.6-flash`，真实 Jev `jev` / `jev-1.13.0`；confidence 1.0，两个 fallback 均 false。
- 真实浏览器流程：AI 诊断 → Jev 候选 → 人工 Apply → 写入 → 精确 Playwright node rerun `PASSED` → 人工 rollback → 原文件字节一致恢复；UI 状态 `VERIFIED` → `ROLLED_BACK`。
- 真实截图 1440/768/360 + patch-ready / verification-in-progress / rollback；安装 user-local Noto CJK 后截图中文可读。
- 测试竞态修复：只在 analysis status terminal 且 workflow state settled 后离开轮询，并在 180s 末明确失败；此前会在 `BLOCKED` + `RUNNING` 的暂态错误退出。
- 另一次低 confidence `0.6` 被 fail-closed，原始文件未变。后续 real-provider rerun `AI provider unavailable` 也安全阻断，无写入。一次带干扰控件页面曾被真实 AI 分类成 `TEST_DATA_ERROR`，此项仍为模型稳定性风险。
- 详情和每次结果（包括 provider unavailable rerun）见 `round-2/ai-jev-live-acceptance.md`；独立 coverage map `round-2/failure-repair-matrix.md`。

### 已修复并提交：并发重复 Apply / 中断恢复竞态

- 提交：`919cfcd fix(repair): make concurrent apply and recovery idempotent`（父 `8508210`）；当前工作分支 `agent/wsl-continuation`，无推送。
- 新增 `LocatorRepairRepository.transition_if_current`，用 `UPDATE ... WHERE state = expected_state` 原子占用 `PATCH_READY → APPLYING`；成功/失败回写也检查预期状态。只有一个并发请求能成功执行受源码哈希保护的写操作。
- 兼容历史数据缺少 `LocatorRepairORM` 的 `PATCH_READY` analysis，在 Apply 前幂等创建状态行；unique `analysis_id` 防止重复创建。
- 两个独立 service/session 并发 Apply，断言且验证只有一个 guarded source write 成功；重复请求根据时序可返回状态冲突或同一已应用结果，持久 `PATCH_APPLIED` / history / proposal 一致；顺序重复 Apply 仍拒绝且文件与事件不变。`PATCH_READY` 参数化场景做了 20 个独立 pytest 进程重复运行，无失败。
- 同一验收覆盖提案审批后的外部文件编辑（`Source changed after repair candidates were generated`、编辑 bytes 不覆盖、状态恢复 `PATCH_READY` 并记录 `PATCH_APPLY_FAILED`），以及注入 `OSError("synthetic workspace write failure")`：源文件保持原字节、proposal `applied=false`、审计记录失败；修复状态不保留非终态 block reason。
- 模拟进程中断后持久化窗口：源码与 failure proposal 已持久化，但 LocatorRepair 仍为 `APPLYING` 或 `PATCH_READY`、analysis/history 未记 `PATCH_APPLIED`。显式 Verify/Rollback 会验证 candidate 与 proposal 后用 CAS 补齐状态；恢复结果经持久状态重读确认。陈旧/已回滚 analysis 状态不会追加虚假的 recovery 事件，迟到的原 Apply completion 不会重复追加事件；无后台无人值守恢复循环。该场景是数据库状态模拟，不是 kill/restart 进程验收。
- 源文件在审批后被外部编辑时，测试要求错误 `Source changed after repair candidates were generated`、编辑 bytes 保留、状态恢复 PATCH_READY 且只在 analysis history 记 `PATCH_APPLY_FAILED`。
- 最新验证：完整 `test_failure_workflow.py` **46 passed / 1 warning**；参数化 recovery `2 passed`；`PATCH_READY` concurrency test 独立进程 **20/20 passed**；`python scripts/task.py lint` 全过。独立 reviewer 复查 CAS/history guard 无发现，确认 CAS 与事件写入在同一 repository transaction；尚无 PostgreSQL 实际并发证据。全后端 823-pass checkpoint 仍早于 CAS 代码，必须在最后代码上重跑。

### 尚待验收：修复审批安全矩阵

现有 integration 覆盖 mocked human reject/approve、低置信度、rollback、exact-run record、analysis interrupt；真实高置信度 UI/API 链已通过。低层 patch 写入异常/stale-source 现有 SQLite 回归覆盖。新增 `test_jev_upstream_outage_blocks_auto_repair_before_diagnosis_or_write` 用真实 `JevDecisionProvider`/`DecisionService` 对 loopback 503 发送 HTTP 请求，收到 `upstream_error` 后在 AI diagnosis/patch 前阻断；AI readiness 被 stub，仅隔离 Jev provider path，不接真实 Jev 远端。
缺口：远程 Jev outage 未诱发、源码/提案持久化前 interruption、verification worker restart；另外加强含干扰控件场景的真实 AI 分类稳定性。逐项映射见 `round-2/failure-repair-matrix.md`。

## 里程碑 3 — Discovery → Coverage 闭环独立复验（部分完成）

### 修复：终态早于 Quality Map 持久化

- 复现：`QualityDiscoveryService._finish()` 先写入 `COMPLETED`/`run.completed`，后生成 Quality Map；真实 API poller 可读到终态后停止轮询，而 map 仍未写入。早期 live test teardown 也会在此窗口取消后台 map 任务。
- 修复：终态由 `_finish()` 统一完成：先投影并提交 Quality Map，再写 terminal status/event；投影异常将该 run 明确置为 `FAILED`。投影器接收预期终态，使 `REQUIRED_NOT_FOUND` 等派生判断仍基于最终状态。
- Stop/pause/resume 与每 run 终结化使用 weak per-run lock 串行化；finalization 期间 stop API 返回 HTTP 409，不会假装接受后又完成。无活跃 task 的 stop 会在释放锁前登记 finalization reservation，防止 resume 先启动新 task；`_finish_locked` 的外层 `finally` 总会清除 reservation，即使 run lookup 抛错。
- 任务取消会进入 STOPPED 收尾，`_finish()` 通过受跟踪的 shielded task 完成持久化。BrowserRuntime session cleanup 也使用保留引用的 shielded task 循环抵御重复 cancellation；测试在 projection 和 close 两段分别重复 cancel，并确认 session 关闭。
- Workspace 扫描本身失败仍允许 Discovery 生命周期正常结束，但 map 明确记 `workspace_test_scan=UNAVAILABLE`、automation coverage `NOT_VERIFIED`，不推断 AUTOMATION_MISSING 或 PASS；对应既有测试保持通过。
- 真实 live Discovery：浏览器只访问本地 loopback 页面；AI `openai-compatible` / `mimo-v2.6-flash` 1 call（1017 input / 279 output tokens），Jev `jev-1.13.0` 1 decision、0 fallback；终态 GET 含已持久化 `quality_map` / `coverage` / `workspace_test_scan`，测试 **1 passed in 11.09s**。完整详情及日志路径见 `functional-audit.md` 与 `logs/live-discovery-finalization.log`。
- 回归：最新 `apps/api/tests/test_quality_discovery.py` **62 passed in 32.04s**；重复 cancellation/no-worker stop/projection failure 定向测试通过。第一次重跑发现两个 fixture tests 只 stub `DecisionService.choose` 却漏了 `ask_score`，意外触发真实 Jev 网络等待；现已加入确定性测试 stub（断言未放宽），相关两测 **2 passed in 3.94s**。最新 `python scripts/task.py lint` / `git diff --check` 均通过：Ruff、426 文件格式、i18n 25 namespaces/2 locales/3022 keys、OpenAPI、ESLint。
- 独立 Reviewer 复查无正确性发现；指出 close-session 自身异常会直接传播（不会挂死），保留现有异常语义。限制：最终化锁与运行 task 是进程内状态；无多进程/PostgreSQL 证据。

### D5 — Discovery → Coverage refresh（已实现；严格实时 UI harness 待一次绿跑）

- 加入 terminal-only `POST /api/discovery/runs/{run_id}/coverage/refresh`，要求 `RUN_EXECUTE`，非 requester/Admin 隐藏为 404；活动 run 返回 409；OpenAPI 描述 403/404/409。service 重新投影 feature/case/binding/TestRun 链，终态 UI 按钮刷新结果并在 run 切换后清除旧反馈。
- `_latest_execution` 按 execution 时间戳选取 newest-first run 中最新匹配尝试；`TestRunRepository.list_runs` 按 `created_at DESC` 返回。refresh 并发在同进程由 per-run lock 串行化；未验证多 worker/PostgreSQL 锁。
- 真实 C 链曾完整通过：本地浏览器探索 → real AI/Jev → AI 需求/用例 → 人工编写 Playwright 脚本 → ACTIVE binding → TestRun PASSED → refresh → feature/case/binding/run `VERIFIED`。真实 web UI 按钮也曾实际点击并显示 success / VERIFIED；截图见 `round-2/screenshots/discovery-coverage-{before-refresh,after-refresh,tablet,mobile}.png`。
- Reviewer 建议已加强：repo-root、per-run screenshots；捕获 refresh POST 并要求 200、无 API errors。严格 harness 尚未最终跑绿：后续两次真实 AI provider 尝试在 UI 前遇到 20s timeout；遵照夜间额度规则暂停重试。标记 **NOT VERIFIED（strict harness）**，不冒充 PASS。
- 架构限制：全平台项目 ACL 尚不存在（Project 无 owner/team，RBAC 为全局角色）。本 endpoint 只加 requester/Admin 边界；这不解决跨项目隔离，需系统级权限设计。

### D5 仍需处理

- Provider 可用后最多执行一次 strict opt-in UI acceptance（`AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 QA_AI_TIMEOUT_SECONDS=60 QA_AI_MAX_RETRIES=1`），核验 direct POST/status、responsive screenshots、无 console/API errors；若再次 20s timeout，记录 BLOCKED，不循环重试。
- PostgreSQL/多进程并发和远程 Worker/Jenkins 仍未验证。

## 里程碑 4 — PostgreSQL / Worker

待办：评估在当前 WSL 中安全运行轻量 PostgreSQL 的可行路径；不可行则记录 BLOCKED 与原因。
Worker 用本地真实进程做集成验收（提交/状态/回传/超时/取消/异常恢复/并发），**不得冒充集群测试**。

## 里程碑 5 — 全站交互式 UI 验收 + P2 UI/UX 优化

待办：逐页真实交互（按钮、输入、保存、Tab、持久化、刷新、错误反馈、空态、加载、异常恢复、导航上下文），
关系图真实数据量下的布局/重叠/搜索/聚焦/性能，Studio 工作上下文连续性，Result 页成功/失败信息分层，
before/after 多分辨率截图。

## 里程碑 6 — D5 全量回归（当前功能单元门禁完成）

本 D5 代码单元回归：后端 **829 passed / 9 skipped / 55 warnings**，前端 **160 passed**、typecheck / ESLint / production build PASS，`scripts/task.py lint` PASS；完整结果及日志见 `test-results.md` 与 `logs/backend-d5-final.log`。后续代码单元仍需重新回归。
真实 API C 链及一次真实 UI 点击曾通过；加强后的 strict UI harness 尚未最终通过，最近因真实 AI Provider 20s timeout 在 UI 前退出；不再盲目消耗额度。
Monaco 主 chunk 仍 4.03 MB。PostgreSQL BLOCKED；远程 Worker/Jenkins NOT RUN；项目级 ACL 架构缺口未解决。

下一步：最终独立 reviewer 已复查当前 diff 且未发现 blocker；本地提交 D5 后继续项目级授权方案与其他未完成的 QA/UX/企业验证。每个后续功能单元都要重跑受影响测试；**不得把本阶段回归冒充整项接管任务的最终回归。**
