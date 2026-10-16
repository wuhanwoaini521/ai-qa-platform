# Agent 交接文档 / Agent Handoff

> 规则：每个可验证里程碑完成后更新本文件。后续 Agent 必须先阅读本文件、核对 Git 状态与真实测试结果，再继续开发。
> 禁止把聊天记录或未跟踪的临时日志作为唯一进度来源。

## 1. 当前任务目标

在 WSL/Linux 环境接管 `ai-qa-platform`，恢复前任 Agent（commit `d8a2eef`）的成果，重建测试基线，
修复环境与核心缺陷，并验证「需求 → AI/Jev → 场景 → 用例 → 自动化 → 执行 → 结果 → 失败修复 → 验证」全链路真实可用。

## 2. Git 状态

| 项 | 值 |
| --- | --- |
| 基线提交（前任） | `d8a2eef` |
| 更早基准 | `02c5f3c` |
| 最新功能提交 | `1720bf3 fix(ai): keep read APIs available when provider is disabled`，父提交 `1ffbaf6` |
| 当前工作分支 | `agent/wsl-continuation`（未推送；`main` 与远程 main 未修改） |
| 未提交修改 | 实时 AI/Jev acceptance harness、审计证据与 screenshots；提交前核对 `git status --short` |
| 远程 main | 未修改、未合并 |
| 远程 | 已 fetch，无本地领先/落后意外差异（工作分支为新增本地骨架） |

## 3. 当前开发阶段

阶段 8 / 第二轮：里程碑 1（Studio Debug）已完成；里程碑 2 进行中，D8 Disabled 可靠性缺陷已修复；真实 AI/Jev 高置信度 API + 浏览器批准/执行/精确复验/回滚链路已通过，11 类决策矩阵仍有缺口。
本轮顺序：Studio Debug → AI/Jev 安全修复 → Discovery/Coverage → PostgreSQL/Worker → UI/UX → 最终全量回归。
本轮证据目录：`.ai-runs/enterprise-continuation/round-2/`。

## 4. 环境基线（WSL / Linux）

- 仓库路径：`/home/hans/self-github/ai-qa-platform`（WSL 原生文件系统，非 `/mnt/c`）
- Python 3.13 + `uv`；Node 24 + `pnpm`；`.venv` 与 `node_modules` 已按锁文件在 Linux 下重建
- Playwright **1.62.0**（`apps/api` 与 `apps/web` 均为该版本；1.63.0 被显式禁止）
- 浏览器：`playwright install chromium` 已安装，bundled Chromium 可正常启动
- 服务：API `http://127.0.0.1:8000`、Web `http://127.0.0.1:5173`，SQLite `runtime/ai_qa_platform.db`
- 详见 `.ai-runs/enterprise-continuation/environment-audit.md`；无系统级改动，Playwright 截图所需 Noto Sans CJK 安装于 `~/.local/share/fonts/`

## 5. 已完成并验证

| 项目 | 证据 |
| --- | --- |
| **Studio 真实调试全流程（第二轮）** | `round-2/studio-debug-acceptance.md`（两脚本 31 项全 PASS） |
| **真实 AI + Jev 失败修复（API + UI）** | `round-2/ai-jev-live-acceptance.md`（真实 provider/Jev、信心 1.0、人工审批、精确 pytest 复验、回滚；screenshots 在 `round-2/screenshots/failure-ui/`） |
| **D8 AI Disabled 可靠性** | `round-2/ai-disabled-provider.md`（43 GET 路由无 5xx；真实 AI 操作明确 502） |
| **失败修复矩阵映射** | `round-2/failure-repair-matrix.md`（标出 duplicate apply、底层写失败、Jev 真实 outage、apply/verify interruption 缺口） |
| 仓库/环境恢复，无 Windows 路径残留导致的功能缺失 | `environment-audit.md` |
| 后端测试基线（真实运行，非沿用旧报告） | `test-results.md` / `.ai-runs/enterprise-continuation/logs/` |
| 前端 typecheck / lint / build | `test-results.md` |
| 链路 A：需求 → AI 分析 → Jev 决策 → 场景 → 用例 → 自动化 → 执行 → 结果 → Knowledge Graph | `logs/live-chain-a.log`（真实 provider + 真实 Jev，无 fallback） |
| 链路 B：失败 → 证据 → AI 诊断 → Jev 决策 → 修复提案 → 人工审批 → 写回 → 精确复跑 | `logs/live-chain-ab.log` |
| 真实 AI provider 健康检查（`REAL_CONNECTED`，`fallback_active=false`） | `/api/ai/status` |
| 真实 Jev 运行时健康检查（`CONNECTED` / `READY`） | `/api/decision/runtime-check` |
| UI 12 个主页面渲染 + 无控制台错误 + 截图 | `screenshots/*.png`、`ui-ux-audit.md` |

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

### 第二轮真实修复闭环（已通过但矩阵未闭合）

- 真实 AI：`openai-compatible` / `mimo-v2.6-flash`；真实 Jev：`jev` / `jev-1.13.0`，confidence 1.0；fallback 均为 false。
- 真实浏览器 UI：人工审批 → 修复写入 → 精确测试节点通过 → 人工回滚恢复原始字节；1 passed，证据和 screenshots 见 `round-2/ai-jev-live-acceptance.md`。
- 风险：同一 live workflow 后续因真实 AI 返回 `AI provider unavailable` 安全阻断；另一条带干扰控件的输入被 AI 分类为 `TEST_DATA_ERROR`。不可宣称 provider 稳定或模糊页面分类已验收。
- 矩阵仍缺 duplicate apply、底层 patch 写失败/Jev outage 真实 runtime、apply/verification 中断，详见 `round-2/failure-repair-matrix.md`。

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

- [ ] AI + Jev 修复审批安全决策矩阵：真实高置信度 UI/API 成功及低置信度 fail-closed 已验证；尚缺 duplicate apply、低层 patch write failure、Jev 实际 outage、apply/verification interruption。已覆盖 mocked human reject、AI/Jev readiness block、rollback；逐项证据见 `round-2/failure-repair-matrix.md`。
- [ ] AI 诊断需加强对存在其他控件时的分类稳定性；一次真实页面干扰控件试验把 locator 错误分类成 `TEST_DATA_ERROR`，当前 clean fixture full chain 通过，见 `round-2/ai-jev-live-acceptance.md`。
- [ ] Discovery → Coverage 完整闭环独立复验（探索 → 发现 → Quality Map → 缺口 → 场景 → 用例 →
  自动化绑定 → 执行 → 覆盖率更新；项目/网站隔离、真实持久化、Feature 去重、刷新后一致）
- [ ] 逐页真实交互式 UI 验收（不只页面加载）+ P2 UI/UX 优化（关系图布局/Studio 上下文连续性/Result 分层）
- [ ] PostgreSQL 集成测试：BLOCKED（本机无 PostgreSQL / Docker）
- [ ] Worker / Jenkins 真实集群测试：NOT RUN（无集群可用）
- [ ] Studio 的 Monaco 全量导入（`MonacoEditorPane` chunk 4.03 MB）按需拆分，需配套浏览器回归
- [ ] 构建峰值内存与新 Bundle 体积证据（第二轮性能小节）
- [ ] 暗色主题验收（低优先级，不得抢占核心功能时间）

> RBAC 与审计日志**已经存在真实后端实现**（`apps/api/app/api/authz.py` 中央策略表 +
> `apps/api/app/api/audit.py` + `apps/api/app/repositories/security_audit_repo.py`），
> 后续不要新建第二套，应扩展已有策略表与审计表。

## 8. 已知 Bug / 阻断

- 无已确认 P0 阻断。真实 provider 有间歇性 `AI provider unavailable`，latest browser acceptance 安全阻断并未写文件；之前有两条完整高置信度 live acceptance PASS。
- 真实 AI 曾把带干扰控件的 locator 失败分类为 `TEST_DATA_ERROR`，暂不证明模糊页面分类稳定。
- 数据库此时为空库（0 projects），UI 里 `/requirements`、`/test-cases`、`/recorder`
  在未选项目时会回到项目页，这是设计行为而非缺陷。

## 9. 最后执行的测试

第二轮当前代码完整结果汇总于 `.ai-runs/enterprise-continuation/round-2/test-results.md`：

- Full backend: 823 passed / 9 skipped / 55 warnings (574.83s).
- Failure workflow focus: 102 passed / 3 skipped / 5 warnings.
- D8 targeted: 20 passed; repository lint/contracts all PASS; Web 160 tests, typecheck PASS, production build PASS (Monaco chunk 4.03 MB warning).
- Real API and real browser AI/Jev high-confidence chains each previously 1 passed; latest browser rerun safely blocked by upstream provider outage, no writes. PostgreSQL blocked; remote Worker/Jenkins not run.
- These results precede any subsequent code changes; repeat affected/full regression before declaring final.

```bash
# 全仓后端回归（本轮最终代码）
uv run --no-sync pytest -q --no-header          # → logs/backend-final-regression.log
# 仓库 lint（ruff + format + i18n 一致性 + OpenAPI 契约 + eslint）
python scripts/task.py lint                     # → All linters passed!
# 前端
pnpm --filter web typecheck && pnpm --filter web lint && pnpm --filter web test && pnpm --filter web build
```

## 10. 下一步具体命令

```bash
# 核对现场
cd ~/self-github/ai-qa-platform
git status --short && git log -1 --oneline
# 第二轮 D8 targeted 回归
uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider
# 环境（仅缺失时恢复）
uv sync && pnpm install

# 启动服务
uv run --no-sync python -m app.main --reload        # apps/api, :8000
pnpm --filter web dev                               # :5173

# 真实 AI + Jev 链路 A + B（需要真实 provider 与 Jev key）
AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 \
AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1 \
uv run --no-sync pytest apps/api/tests/test_live_enterprise_journey.py \
  apps/api/tests/test_live_locator_repair_acceptance.py -v -s

# 真实浏览器验收
AI_QA_LIVE_BROWSER_E2E=1 uv run --no-sync pytest apps/api/tests/test_browser_agent_live_e2e.py -v -s

# 回归
uv run --no-sync pytest apps/api/tests -q
pnpm -r typecheck && pnpm -r lint
```

## 11. 下一个 Agent 应当继续的工作

1. **第二轮里程碑 2**：补齐 duplicate apply、patch write failure、实际 Jev outage、apply/verify interruption；评估并修正 AI 对干扰控件场景误分类，继续用真实调用验收。
2. **里程碑 3**：Discovery → Coverage 端到端独立复验。
3. **里程碑 4**：评估 WSL 内轻量 PostgreSQL 可行性；本地 Worker 进程集成验收（不得冒充集群）。
4. **里程碑 5**：逐页真实交互 UI 验收 + before/after 多分辨率截图。
5. **里程碑 6**：最终全量回归（后端/前端/typecheck/lint/build/E2E/AI-Jev/Studio），更新 `test-results.md`。
6. 每完成一轮：更新 `docs/agent-handoff.md` 与 `round-2/implementation-log.md` → 保存真实测试输出 → commit（不 push main）。

可复用验收脚本（未入库，在 `/tmp`，必要时按 `round-2/studio-debug-acceptance.md` 重建）：
`studio_debug_accept.py`、`studio_debug_failure_accept.py`、`probe_studio_file.py`。
