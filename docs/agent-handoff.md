# Agent 交接文档 / Agent Handoff

> 规则：每个可验证里程碑完成后更新本文件。后续 Agent 必须先阅读本文件、核对 Git 状态与真实测试结果，再继续开发。
> 禁止把聊天记录或未跟踪的临时日志作为唯一进度来源。

## 1. 当前任务目标

当前优先完成 Automation Studio 真实浏览器验收（用户任务 m04803）：确认 Monaco 编辑/保存、真实 debugpy 断点与 DAP stepping、暂停/停止/重复运行、失败证据及多分辨率 UI。此后继续原接管任务（m00001、m00628）：验证并完善「需求 → AI/Jev → 场景 → 用例 → 自动化 → 执行 → 结果 → 失败修复 → 验证」真实全链路，不重写已有正确功能。

## 2. Git 状态

| 项 | 值 |
| --- | --- |
| 基线提交（前任） | `d8a2eef` |
| 更早基准 | `02c5f3c` |
| D5 实现提交 | `6b56261 feat(discovery): refresh coverage after test execution` |
| Round-2 D5 final-report/handoff commit | `7cac0be`（历史基线；详见 `git log`） |
| Project-ACL architecture-audit commit | `7ca6e19 docs: record project ACL blocker and next stage` |
| Studio 本轮基点 HEAD | `7cac0be55118992b551c72ad184cb236dbe29699` |
| Studio 源码/测试提交 | `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5` (`fix(studio): restore responsive debug workspace`) |
| 最近 AI Disabled 修复提交 | `1720bf3 fix(ai): keep read APIs available when provider is disabled`，父提交 `1ffbaf6` |
| 当前工作分支 | `agent/wsl-continuation`（未推送；`main` 与远程 main 未修改） |
| 当前工作树 | Studio 源码/测试提交 `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5`；本文件是其后的 handoff-only 文档更新。`.ai-runs/night-continuation/` 是本地证据，不提交大型日志/截图。 |
| 本轮 Studio evidence | `.ai-runs/night-continuation/round-1/attempt-19/`（真实 Chromium/debugpy acceptance、响应式截图与日志） |
| 远程 main | 未修改、未合并 |
| 远程 | 已 fetch，无本地领先/落后意外差异（工作分支为新增本地骨架） |

## 3. 当前开发阶段

当前阶段：Round-1 Automation Studio 核心真实浏览器验收 attempt 19、全仓回归/lint、最终独立复审均通过；Round-1 报告已更新，源码/测试已本地提交 `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5`，未推送。旧 Round-2 的 17 个主流程 + 14 个失败/幂等检查仍是历史证据，不能代替本轮。

本轮修复/完善：
- `apps/api/tests/conftest.py` 的 client fixture 使用 teardown 恢复 workspace path；opt-in UI test 的 AI/Jev health probes 在测试期显式 disabled，并在 `finally` 恢复全局 config/runtime，避免外部请求和测试污染。
- `apps/web/src/index.css` 与 `apps/web/src/features/workspace/workspace.css` 修复 debug 页面 flex sizing；Monaco 编辑器从 5px 高恢复为桌面 161px、平板/手机至少 140px。
- `DebugPanel` 在手机改为纵向可滚动详情；桌面/平板保留三栏。测试覆盖手机滚动到调试控制台且无 document 横向溢出。
- 新增 `apps/api/tests/test_studio_debug_ui_live.py`：真实 Vite/Uvicorn/Chromium/Playwright 1.62.0 和 debugpy DAP，无 DAP mock。真实编辑/保存、断点、Step In/Over/Out、Continue、重复会话、Pause/Stop 和真实失败 Run 均验收通过。

最新 opt-in acceptance attempt 19：**2 passed / 32.10s**；3 个 debug sessions 均 `CLOSED`，合成 Playwright 失败 Run 为 `FAILED` 且 trace 保留，API/console errors 为空。真实 Python 语义：Step Out 停在 `calculate:11` 时 assignment 尚未存入 `intermediate`；再 Step Over 后才断言 `intermediate == 41`。Before/after、断点、桌面/平板/手机、手机 console 截图位于 `.ai-runs/night-continuation/round-1/attempt-19/screenshots/`。

Reviewer 发现的 config/workspace teardown、手机布局和 document-width assertion 均已修复；attempt 19 与最终全仓回归通过。最终复审确认无其他 finding；Round-1 reports 已更新，本地 commit 待完成。历史 D5/ACL/Docker/PostgreSQL/Worker 状态见 `.ai-runs/enterprise-continuation/round-2/`。

## 4. 环境基线（WSL / Linux）

- 仓库路径：`/home/hans/self-github/ai-qa-platform`（WSL 原生文件系统，非 `/mnt/c`）
- Python 3.13 + `uv`；Node 24 + `pnpm`；`.venv` 与 `node_modules` 已按锁文件在 Linux 下重建
- Playwright **1.62.0**（`apps/api` 与 `apps/web` 均为该版本；1.63.0 被显式禁止）
- 浏览器：`playwright install chromium` 已安装，bundled Chromium 可正常启动
- 服务状态：最近检查 `127.0.0.1:8000` API 与 `:5173` Web 均不可达；本次测试由隔离 TestClient/临时 Uvicorn/Vite 按需启动并清理。项目 SQLite 路径为 `runtime/ai_qa_platform.db`；PostgreSQL/Docker 不可用。
- 详见 `.ai-runs/enterprise-continuation/environment-audit.md`；无系统级改动，Playwright 截图所需 Noto Sans CJK 安装于 `~/.local/share/fonts/`

## 5. 已完成并验证

| 项目 | 证据 |
| --- | --- |
| **Studio 真实调试全流程（历史第二轮）** | `round-2/studio-debug-acceptance.md`（31 项声称 PASS；当前 Round-1 必须重新实测） |
| **真实 AI + Jev 失败修复（API + UI）** | `round-2/ai-jev-live-acceptance.md`（真实 provider/Jev、信心 1.0、人工审批、精确 pytest 复验、回滚；screenshots 在 `round-2/screenshots/failure-ui/`） |
| **D8 AI Disabled 可靠性** | `round-2/ai-disabled-provider.md`（43 GET 路由无 5xx；真实 AI 操作明确 502） |
| **失败修复矩阵映射** | `round-2/failure-repair-matrix.md`（包含 duplicate apply SQLite 回归、Jev loopback 503 与剩余远端 outage/进程中断边界） |
| **Discovery → Coverage 下游闭环** | `round-2/test-results.md` D5：真实 local browser + real AI/Jev requirement/case，人工 Playwright ACTIVE binding，browser TestRun PASSED，显式 refresh 后 coverage VERIFIED；真实 UI 按钮点击成功过一次，strict harness 待 provider 恢复后复跑 |
| 仓库/环境恢复，无 Windows 路径残留导致的功能缺失 | `environment-audit.md` |
| 后端测试基线（真实运行，非沿用旧报告） | `test-results.md` / `.ai-runs/enterprise-continuation/logs/` |
| 前端 typecheck / lint / build | `test-results.md` |
| 链路 A：需求 → AI 分析 → Jev 决策 → 场景 → 用例 → 自动化 → 执行 → 结果 → Knowledge Graph | `logs/live-chain-a.log`（真实 provider + 真实 Jev，无 fallback） |
| 链路 B：失败 → 证据 → AI 诊断 → Jev 决策 → 修复提案 → 人工审批 → 写回 → 精确复跑 | `logs/live-chain-ab.log` |
| 真实 AI provider 健康检查（`REAL_CONNECTED`，`fallback_active=false`） | `/api/ai/status` |
| 真实 Jev 运行时健康检查（`CONNECTED` / `READY`） | `/api/decision/runtime-check` |
| UI 13 个主页面渲染 + 无控制台错误 + 截图 | `screenshots/*.png`、`ui-ux-audit.md` |

## 6. 本次修复的缺陷

### P1（第二轮 D7）— Studio 深链会静默打开另一个文件

- 现象：`/projects/<id>/studio/file/tests/test_known_locator.py` 最终把 URL 的 `file=` 改成
  `tests/test_shop.py`，编辑器、断点与调试目标全部落到另一个文件；用户以为在给 A 设断点，实际调试 B。
- 根因：`WorkspacePage.tsx` 的上下文归一化用「第一条绑定用例的文件」覆盖显式 `file=`；
  `initialOpenFilePath` 只要选中用例就优先绑定文件。
- 修复：`workspaceContext.ts` 新增 `resolveCanonicalFile()`（显式 file > 失败调试上下文 > 绑定文件），
  归一化与 `initialOpenFilePath` 都改用它；新增 3 个前端回归用例。
- 回归：`pnpm --filter @ai-qa/web test` → 160 passed；真实浏览器复验断点落在 `test_known_locator.py:12`。

### P2（第二轮 D6）— `DELETE /api/debug/sessions/{id}` 对已关闭会话返回 404

- 现象：DAP `terminated` 后前端调用关闭接口，浏览器控制台出现 404 报错。
- 修复：DELETE 改为幂等（已关闭 → 200 `{"closed": false}`），未知/他人会话仍 404；
  新增 `test_debug_close_is_idempotent_for_already_closed_sessions`。

### P1（第二轮 D8）— AI/Jev Disabled 时只读 API 500

- 现象：在 `QA_AI_ENABLED=false JEV_ENABLED=false` 下，`GET /api/ai/status`、`/api/runs`、`/api/failures`
  因 Provider 初始化异常返回 500；健康探针本身则能报告 disabled。
- 根因：`ProductionQAOrchestrator.__init__` eager 构造 Provider，导致任何依赖该服务的读取端点在 handler 执行前失败。
- 修复：`packages/qa-core/qa_core/orchestrator/orchestrator.py` 延迟到首次真实 Provider 使用时解析 Provider；
  只读 API 正常可用，AI 写操作仍失败为明确 502，不会静默回退。
- 验证：真实禁用配置扫查 43 个无参数 GET 路由，0 个 5xx；隔离测试覆盖 status/runs/failures + AI 分析失败语义；
  相关测试 20 passed。详情 `.ai-runs/enterprise-continuation/round-2/ai-disabled-provider.md`。

### P1 — Discovery 暴露终态早于 Quality Map 持久化（已在 `02210de` 修复）

- 现象：`_finish()` 先写 `COMPLETED`，再写 Quality Map；API poller / UI 可能读到终态后停止轮询，覆盖率仍空；原 live test teardown 也可在该窗口取消 map task。
- 修复：先构建/持久化 map，再写 terminal status/event；投影异常转为明确 `FAILED`。stop/pause/resume 与 finalization 以 per-run lock 线性化；finalization 已开始时 stop 返回 HTTP 409，不会假装接收。运行 task cancel 会请求 STOPPED；shielded finalizer 支持重复 cancellation 后继续完成持久化。
- 验证：`apps/api/tests/test_quality_discovery.py` 62 passed in 32.04s；真实 local-browser Discovery 用 `openai-compatible` / `mimo-v2.6-flash` 与 Jev `jev-1.13.0` 执行，1 passed，terminal response 已包含 quality map/coverage/workspace scan。全仓 lint/OpenAPI/i18n 与 `git diff --check` PASS；独立 review 无 correctness finding。日志 `.ai-runs/enterprise-continuation/round-2/logs/live-discovery-finalization.log`；详情见 round-2 `test-results.md`。
- 限制：finalization/refresh lock 为单进程状态，未验证多 API worker/PostgreSQL 并发；D5 的 Discovery→gap→case→binding→execution→coverage refresh 已有真实 API 链，真实 UI 按钮曾点击成功，但最新 strict harness尚未因 Provider timeout完成最终绿跑。

### 第二轮真实修复闭环（已通过但矩阵未闭合）

- 真实 AI：`openai-compatible` / `mimo-v2.6-flash`；真实 Jev：`jev` / `jev-1.13.0`，confidence 1.0；fallback 均为 false。
- 真实浏览器 UI：人工审批 → 修复写入 → 精确测试节点通过 → 人工回滚恢复原始字节；1 passed，证据和 screenshots 见 `round-2/ai-jev-live-acceptance.md`。
- 风险：同一 live workflow 后续因真实 AI 返回 `AI provider unavailable` 安全阻断；另一条带干扰控件的输入被 AI 分类为 `TEST_DATA_ERROR`。不可宣称 provider 稳定或模糊页面分类已验收。
- 矩阵剩余远程 Jev outage 未诱发、源码/提案持久化前中断、verification worker restart，详见 `round-2/failure-repair-matrix.md`；真实 Jev 客户端对 loopback HTTP 503 fail-closed 已测试；duplicate Apply 和 stale-source 已有 SQLite 回归。

### P1 — 验收夹具把浏览器 channel 写死为系统 Chrome（跨平台缺陷）

- 现象：链路 A 第一次真实运行失败，日志为
  `BrowserType.launch: Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome`
  （发生在被测工作区里生成的 `tests/test_verification_panel.py`）。
- 根因：`apps/api/tests/test_live_enterprise_journey.py` 与
  `apps/api/tests/test_live_locator_repair_acceptance.py` 生成的测试源码中硬编码 `channel="chrome"`
  （Windows/macOS 开发期为了绕开 bundled Chromium 的问题）。
- 修复：改为环境变量 `AI_QA_ACCEPTANCE_BROWSER_CHANNEL`，默认 `None`（使用 Playwright bundled Chromium，
  在 Linux/WSL/CI 上可直接运行）；仅在不支持的宿主上用 `AI_QA_ACCEPTANCE_BROWSER_CHANNEL=chrome` 覆盖。
- 回归：链路 A 由 `1 failed / 1 passed` 变为 `2 passed`。

### P1 — Web 生产构建 Node 堆溢出（交付阻断）

- 现象：`pnpm --filter web build`（CI 同一命令）报
  `FATAL ERROR: Ineffective mark-compacts near heap limit … JavaScript heap out of memory`，exit 134。
- 根因：Vite/Rollup 转换阶段超过 Node 默认 2 GB old-space 上限（本机 WSL 共 7.9 GB，非宿主内存不足）。
- 修复：`apps/web/package.json` 的 build 脚本改为
  `tsc -b && node --max-old-space-size=4096 node_modules/vite/bin/vite.js build`
  （不用 `NODE_OPTIONS=` 前缀是因为 Windows `cmd.exe` 下不生效）。
- 遗留：`MonacoEditorPane` chunk 4.03 MB，见 `implementation-log.md` D2。

### P1 — 健康探针预算小于 AI 请求超时，UI 误报「部分能力受限」

- 现象：`/library`、`/recorder`、`/settings` 顶栏长期显示「部分能力受限：常规 AI 运行健康」，
  但同一时刻真实 AI 验收通过；`/api/ai/system-health` 报 `PROBE_TIMEOUT` 而 `/api/ai/status` 报 `REAL_CONNECTED`。
- 根因：`platform_health_service` 给 `ai` 探针固定 15 s 预算，而配置的 AI 请求超时是 30 s，
  且该探针实际发出两次 provider 调用（`check_health` + 合成 `stream_complete`）。
- 修复：后端探针预算改为 `max(15, 2 × config.timeout)`；前端把「探针超时」与「能力受限」区分开
  （`apps/web/src/components/readinessNoticeModel.ts`）。
- 回归：`/api/ai/system-health` 由 `degraded` → `healthy`；顶栏在 3 个页面由「显示」→「不显示」。

## 7. 未完成 / 待办

（第二轮，按优先级）

- [ ] AI + Jev 修复审批安全决策矩阵：真实高置信度 UI/API 成功及低置信度 fail-closed、SQLite duplicate Apply/stale-source/持久化后恢复和真实 Jev 客户端 loopback 503 fail-closed 已验证；尚缺远程 Jev outage、源码/提案持久化前 interruption、verification worker restart 和 PostgreSQL 并发证据。已覆盖 mocked human reject、AI/Jev readiness block、rollback；逐项证据见 `round-2/failure-repair-matrix.md`。
- [ ] AI 诊断需加强对存在其他控件时的分类稳定性；一次真实页面干扰控件试验把 locator 错误分类成 `TEST_DATA_ERROR`，当前 clean fixture full chain 通过，见 `round-2/ai-jev-live-acceptance.md`。
- [x] Discovery → Coverage API/integration 闭环：真实探索 → AI requirement/case generation → 人工编写 active Playwright binding → browser execution → explicit refresh → VERIFIED；D5 evidence in `round-2/test-results.md`.
- [x] Discover 的 Refresh Coverage 按钮已在真实浏览器点击并显示成功 / VERIFIED；历史 run-switch feedback reset 有实现和确定性覆盖。
- [ ] 最新 strict D5 live UI harness 要求 HTTP 200 / 无 API errors / per-run screenshots，Provider 恢复后最多再跑一次；系统性 project/team ACL 仍缺失（本端点仅 requester/admin scoped）。
- [x] Studio 核心真实浏览器 acceptance：attempt 19 通过编辑/保存、真实 debugpy 断点与 stepping/continue、Pause/Stop、重复会话、失败证据及 desktop/tablet/mobile；证据 `.ai-runs/night-continuation/round-1/attempt-19/`。
- [x] 最终全仓 regression、Python/Web lint、typecheck、build、document-width viewport assertion。
- [x] Round-1 reports 更新、最终独立 reviewer 无 actionable finding。
- [x] 本地 semantic commit `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5`（no push）。
- [ ] PostgreSQL 集成测试：BLOCKED（本机无 PostgreSQL / Docker）
- [ ] Worker / Jenkins 真实集群测试：NOT RUN（无集群可用）
- [ ] Studio 的 Monaco 全量导入（`MonacoEditorPane` chunk 4.03 MB）按需拆分，需配套浏览器回归
- [ ] 构建峰值内存与新 Bundle 体积证据（第二轮性能小节）
- [ ] 暗色主题验收（低优先级，不得抢占核心功能时间）

> RBAC 与审计日志**已经存在真实后端实现**（`apps/api/app/api/authz.py` 中央策略表 +
> `apps/api/app/api/audit.py` + `apps/api/app/repositories/security_audit_repo.py`），
> 后续不要新建第二套，应扩展已有策略表与审计表。

## 8. 已知 Bug / 阻断

- 已确认的企业安全 blocker：全平台项目级授权模型缺失（Project 无 owner/team 关系；不能用单路由 ACL 代替系统级隔离）。
- Studio locale-tolerant selectors、debug-view flex sizing、phone DebugPanel layout 已修复并在 attempt 19 实测；编辑器 161px desktop / ≥140px tablet-mobile，mobile details 纵向滚动可读，documentWidth 在 1440/768/390px 均不超过 viewport。
- Discovery 最终化修复已提交：终态必须等 Quality Map 写入后才暴露；finalization 期间 stop/pause/resume 返回冲突，重复 task cancellation 下 shielded finalizer 与 BrowserRuntime cleanup 均收敛。D5 refresh endpoint uses terminal guard and per-run lock; double-refresh regression observes serialization in one process. No multi-process/PostgreSQL evidence.
- 项目权限仍是 P0/P3 架构风险：`ProjectORM` 没有 owner/team 关系，RBAC roles 全局；本次只限制非管理员刷新自己发起的 run，不能据此宣称系统级 project isolation 已完成。
- 已提交 CAS/recovery/stale-history 修复（`919cfcd`）；Jev loopback 503 fail-closed 集成测试后，`test_failure_workflow.py` **47 passed / 1 warning**。参数化恢复 **2/2 passed**，PATCH_READY 并发场景 20/20 次通过；stale `ROLLED_BACK` source 不会追加 recovery event。Round-2 历史后端回归为 829 passed / 9 skipped，已由 Round-1 最终全仓 830 passed / 10 skipped / 55 warnings supersede，详见 §9。
- 真实 AI 曾把带干扰控件的 locator 失败分类为 `TEST_DATA_ERROR`，暂不证明模糊页面分类稳定。
- 数据库此时为空库（0 projects），UI 里 `/requirements`、`/test-cases`、`/recorder`
  在未选项目时会回到项目页，这是设计行为而非缺陷。

## 9. 最后执行的测试

第二轮结果汇总于 `.ai-runs/enterprise-continuation/round-2/test-results.md`。

- 最新 Studio opt-in acceptance attempt 19：**2 passed / 32.10s**，真实 Chromium + debugpy；3 sessions CLOSED、synthetic failure Run 为 FAILED 且保留 trace，API/console errors 为空。1440/768/390px `documentWidth <= viewport`。全套截图、metrics、log：`.ai-runs/night-continuation/round-1/attempt-19/`。
- Studio attempts 1–18 为排障历史；attempt 19 为当前事实。早期 locale selector、Monaco 5px flex collapse、breakpoint verification locator、Step Out 停点等问题已通过修正 harness/布局后解决；最终结果不得引用这些旧失败代替 attempt 19。
- D5 real API C chain 成功：真实 AI/Jev/本地浏览器、AI 需求/用例、人工 ACTIVE Playwright binding、Run PASSED、刷新后 coverage `VERIFIED`；一次真实 Web UI 点击也显示成功。D5 strict live retries 曾被 provider timeout 阻断；本轮 Studio acceptance 不调用真实 AI/Jev，测试 fixture 明确禁用 health probes 并在 teardown 恢复，不能把这项结果说成 AI/Jev 验收。
- D5 OpenAPI 403/404/409、requester/Admin endpoint boundary、run-switch UI stale-feedback 和 timestamp latest-execution均修复；`TestRunRepository.list_runs` newest-first。一次独立 review 发现 strict harness路径/status断言问题，已改；最终 reviewer 复查当前 diff：无剩余 blocker。
- 本轮最终全仓回归（attempt 19 后）：**830 passed / 10 skipped / 55 warnings / 453.15s**；PostgreSQL lane skipped（`AI_QA_TEST_DATABASE_URL` 未设置）。Frontend **160 passed**，typecheck/ESLint/build 通过；`python scripts/task.py lint` 通过 Ruff、427-file format、i18n（25 namespaces/3025 keys）、OpenAPI 与 ESLint。日志 `.ai-runs/night-continuation/round-1/logs/full-regression-final.log`、`lint-final.log`。Vite 6.4.3 警告大型 chunk（Monaco JS 4,031.76KB）。
- Failure workflow CAS/recovery + Jev 503 suite：**47 passed / 1 warning**；duplicate Apply 20/20 重复、exactly one workspace write。Monaco chunk 4.03 MB；PostgreSQL blocked；remote Worker/Jenkins not run。
- 系统级项目隔离仍未解决：Project 无 owner/team ACL，RBAC 角色为全局；D5 仅 requester/Admin 可刷新其 run，不代表其他 API 已隔离。

```bash
# 全仓后端回归（本轮最终代码）
python scripts/task.py test                    # → .ai-runs/night-continuation/round-1/logs/full-regression-final.log
# 仓库 lint（ruff + format + i18n 一致性 + OpenAPI 契约 + eslint）
python scripts/task.py lint                     # → All linters passed!
# 前端
pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web test && pnpm --filter web build
```

## 10. 下一步具体命令

```bash
# 核对现场
cd /home/hans/self-github/ai-qa-platform
git status --short && git log -1 --oneline
# 当前 Studio acceptance（使用新的 attempt 目录，避免覆盖既有证据）
# 若后续代码修改需要重验，先创建全新 attempt-20 目录；当前通过证据为 attempt-19。
mkdir -p .ai-runs/night-continuation/round-1/attempt-20/logs
AI_QA_STUDIO_EVIDENCE_DIR=.ai-runs/night-continuation/round-1/attempt-20/screenshots \\
AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1 uv run --no-sync pytest apps/api/tests/test_studio_debug_ui_live.py -q -s 2>&1 | tee .ai-runs/night-continuation/round-1/attempt-20/logs/studio-ui-acceptance.log
# 修复确认的 UI bug 后运行 Studio 相关回归，再运行全仓回归
uv run --no-sync pytest apps/api/tests/test_studio_debug_ui_live.py apps/api/tests/test_debug_session_service.py -q --no-header
python scripts/task.py lint
git diff --check
# latest failure repair security regression
uv run --no-sync pytest apps/api/tests/test_failure_workflow.py -q --no-header -p no:cacheprovider
# D8 disabled-provider targeted regression
uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider
# 环境（仅依赖确实缺失且 lockfile 无变更时恢复；不要为验证无条件重装）
# uv sync --locked && pnpm install --frozen-lockfile

# 启动服务
uv run --no-sync python -m app.main --reload        # apps/api, :8000
pnpm --filter web dev                               # :5173

# Strict D5 live UI (仅 Provider 恢复后执行一次；60s/1 retry；若仍超时则 BLOCKED，不循环重试)
AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 QA_AI_TIMEOUT_SECONDS=60 QA_AI_MAX_RETRIES=1 \
uv run --no-sync pytest apps/api/tests/test_live_enterprise_journey.py::test_real_local_discovery_preserves_target_and_project_scope -v -s

# 真实浏览器验收
AI_QA_LIVE_BROWSER_E2E=1 uv run --no-sync pytest apps/api/tests/test_browser_agent_live_e2e.py -v -s

# 回归
uv run --no-sync pytest apps/api/tests -q
pnpm -r typecheck && pnpm -r lint
```

## 11. 下一个 Agent 应当继续的工作

1. 核对本 handoff、`git status` 与 `git diff --check`；当前 attempt 19、全回归、lint 和 reviewer 均有证据，除非代码发生变化不要重复运行。
2. 核对本地提交 `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5` 与随后的 handoff-only commit；不得 push。
3. Studio Round-1 后继续 m00001/m00628 企业接管：完整 Project owner/team ACL 模型与迁移、repair matrix 剩余边界、PostgreSQL/Worker-Jenkins 环境、未验收业务链路/UI。

旧 `/tmp` Studio scripts 不存在；真实 debugpy opt-in test 位于 `apps/api/tests/test_studio_debug_ui_live.py`，通过 `AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1` 启动。
