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
| 本轮提交 | 分支 `agent/wsl-continuation` 顶端（`git log -1`）：`fix: make acceptance, web build and AI health consistent on Linux` ｜ 其后所有审计文档同属该分支 |
| 当前工作分支 | `agent/wsl-continuation`（未推送） |
| 远程 main | 未修改、未合并 |
| 远程 | 已 fetch，无本地领先/落后意外差异（工作分支为新增本地骨架） |

## 3. 当前开发阶段

阶段 7：真实 AI + Jev 验收与跨平台缺陷修复。

## 4. 环境基线（WSL / Linux）

- 仓库路径：`/home/hans/self-github/ai-qa-platform`（WSL 原生文件系统，非 `/mnt/c`）
- Python 3.13 + `uv`；Node 24 + `pnpm`；`.venv` 与 `node_modules` 已按锁文件在 Linux 下重建
- Playwright **1.62.0**（`apps/api` 与 `apps/web` 均为该版本；1.63.0 被显式禁止）
- 浏览器：`playwright install chromium` 已安装，bundled Chromium 可正常启动
- 服务：API `http://127.0.0.1:8000`、Web `http://127.0.0.1:5173`，SQLite `runtime/ai_qa_platform.db`
- 详见 `.ai-runs/enterprise-continuation/environment-audit.md`

## 5. 已完成并验证

| 项目 | 证据 |
| --- | --- |
| 仓库/环境恢复，无 Windows 路径残留导致的功能缺失 | `environment-audit.md` |
| 后端测试基线（真实运行，非沿用旧报告） | `test-results.md` / `.ai-runs/enterprise-continuation/logs/` |
| 前端 typecheck / lint / build | `test-results.md` |
| 链路 A：需求 → AI 分析 → Jev 决策 → 场景 → 用例 → 自动化 → 执行 → 结果 → Knowledge Graph | `logs/live-chain-a.log`（真实 provider + 真实 Jev，无 fallback） |
| 链路 B：失败 → 证据 → AI 诊断 → Jev 决策 → 修复提案 → 人工审批 → 写回 → 精确复跑 | `logs/live-chain-ab.log` |
| 真实 AI provider 健康检查（`REAL_CONNECTED`，`fallback_active=false`） | `/api/ai/status` |
| 真实 Jev 运行时健康检查（`CONNECTED` / `READY`） | `/api/decision/runtime-check` |
| UI 12 个主页面渲染 + 无控制台错误 + 截图 | `screenshots/*.png`、`ui-ux-audit.md` |

## 6. 本次修复的缺陷

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

- [ ] 链路 C 的覆盖率独立外层复验（需求 → 用例 → 执行 → 结果 → 知识图已复验）
- [ ] Studio 深度交互验收（Monaco 编辑 → 运行 → 调试 → 证据 → AI 修复闭环）；页面加载与截图已完成
- [ ] Studio 的 Monaco 全量导入（`MonacoEditorPane` chunk 4.03 MB）按需拆分，需配套浏览器回归
- [ ] PostgreSQL 集成测试：BLOCKED（本机无 PostgreSQL / Docker）
- [ ] Worker / Jenkins 真实集群测试：NOT RUN（无集群可用）
- [ ] 暗色主题验收
- [ ] 图谱连线与节点布局的视觉密度人工评估（功能与单测已覆盖）

> RBAC 与审计日志**已经存在真实后端实现**（`apps/api/app/api/authz.py` 中央策略表 +
> `apps/api/app/api/audit.py` + `apps/api/app/repositories/security_audit_repo.py`），
> 后续不要新建第二套，应扩展已有策略表与审计表。

## 8. 已知 Bug / 阻断

- 无 P0 阻断。数据库此时为空库（0 projects），UI 里 `/requirements`、`/test-cases`、`/recorder`
  在未选项目时会回到项目页，这是设计行为而非缺陷。

## 9. 最后执行的测试

见 `.ai-runs/enterprise-continuation/test-results.md`（含命令、真实输出摘要与日志路径）。

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
# 环境
cd ~/self-github/ai-qa-platform
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

1. 端到端复验链路 C，并把结果写入 `.ai-runs/enterprise-continuation/test-results.md`。
2. 对 Studio 做真实浏览器交互验收（编辑 → 运行 → 调试 → 证据 → AI 修复），产出前后截图。
3. 补齐多分辨率与移动端截图。
4. 从企业级能力清单中选一条最小可交付完整链路实现（建议：审计日志或 RBAC），不得只加 UI 不加后端。
5. 每完成一轮：更新本文件 → 保存真实测试输出 → commit（不 push main）。
