# AI QA Platform Phase 0–8 Overnight Final Acceptance

**日期：** 2026-10-10
**分支：** `main`
**代码修复提交：** `7108b08` (`fix: reconcile manual repair verification history`)
**结论： `PARTIAL`** — 本地 API/Web 可运行，主要代码与回归门通过，真实 AI + Jev 人工批准修复闭环也通过；PostgreSQL 和对未知旧队列的完整 Worker 验收仍是明确证据缺口，不能据此宣称生产全通过。

## 阶段验收

| 阶段 | 状态 | 证据与边界 |
|---|---|---|
| 0. 基线与安全边界 | **PASS** | 基线记录见 `docs/audits/runtime-hardening-baseline.md`。保留现有数据与凭证；API 正常启动时已将现有 SQLite schema 迁移到 Alembic `0007_quality_discovery_version`，未 reset / 删除数据库。现有 200 个 queued jobs 未被领取。 |
| 1. Provider 配置与健康 | **PASS** | 环境变量优先级高于 YAML 与 schema defaults；AI/Jev 状态与 fallback 来源分离。真实接受测试报告 `openai-compatible` 与 `jev`、均未使用 fallback；未输出凭证。 |
| 2. Worker 并发、取消与恢复 | **PARTIAL** | Worker 生命周期、并发上限、能力声明、取消/关闭、身份与任务所有权等测试包含在完整后端套件中并通过。**未**把 Worker 接到现有数据库，也未执行全 Worker 接受流程：旧队列任务意图未知，执行会有数据/业务风险。 |
| 3. 服务边界与修复状态历史 | **PASS** | 手工修复的终态对账曾可能漏记 `verification.completed`。提交 `7108b08` 增加按 verification run 关联 `verification.started` 的恢复逻辑及回归测试；针对该回归测试通过。 |
| 4. 安全、配置与数据保护 | **PASS** | provider 配置/secret redaction 回归通过；未修改/轮换凭证，未在日志或报告记录 secret；现有本地数据未重置。 |
| 5. 真实 AI + Jev 失败修复 | **PASS** | 真实 provider 的修复候选经人工批准后应用，原 locator 被替换；对原失败的**精确测试节点**执行真实 pytest 验证，结果 `PASSED`，workflow 为 `VERIFIED`。没有用 Fake Provider 代替实时验收。 |
| 6. API / 浏览器 UI 旅程 | **PASS** | `GET /api/health/live`、`/api/health/ready` 与 Web `/` 均为 HTTP 200。真实浏览器 UI 接受使用系统 Chrome，覆盖桌面/平板/手机布局、Jev 候选、Apply 与 Verify 操作、修复后源码变化和终态 UI。另有真实低置信度 abstention 分支：安全阻断、无补丁、无验证运行，并向用户说明原因。截图在 `docs/audits/overnight-evidence-2026-10-10/`。 |
| 7. 完整本地回归 | **PASS** | 后端/core/integrations/Worker 单测、前端单测、lint、类型检查、i18n 与 production build 均通过；具体数据见下节。 |
| 8. 跨数据库、Worker 与跨平台最终验收 | **PARTIAL / BLOCKED** | 本机没有可用 PostgreSQL/Docker；Windows/Linux CI 未在 macOS 主机本地运行；完整 Worker 接受因旧队列安全约束不执行。详见阻碍。 |

## 真实修复闭环证据

命令：

```bash
AI_QA_FAILURE_UI_SCREENSHOT_DIR=docs/audits/overnight-evidence-2026-10-10/failure-ui-assisted \
AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1 \
QA_AI_BASE_URL=https://api.deepseek.com \
uv run pytest -q -s --tb=short \
  apps/api/tests/test_live_locator_repair_acceptance.py::test_live_ai_jev_failure_repair_through_browser_ui
```

结果：**1 passed**。真实运行输出记录了 Jev confidence `0.79`、provider `jev`、`fallback_used=false`、proposal 存在；随后 UI 人工批准并应用补丁，真实精确节点复测状态为 `PASSED`，最终 workflow `VERIFIED`，AI/Jev 均无 fallback。测试还检查原 locator 已移除、提案 locator 写入源码、修复事件历史完整以及成功 UI 状态。
真实低置信度分支也实际返回过 `BLOCKED`；这属于设计要求的安全拒绝，不作为修复闭环通过证据。此前一次低置信度响应曾让测试安全阻断；之后通过的 `.79` 实际修复运行才是闭环 PASS 证据。

截图为 UI 状态证据，不替代测试断言或真实 pytest 执行；`verification-in-progress.png` 是验证阶段的中间截图，不代表终态截图。

## 回归与构建结果

- `uv run pytest -q` — **659 passed, 7 skipped, 44 warnings**（约 4 分 39 秒）。警告为既有 pytest collection、运行时 fixture / SQLAlchemy 连接及 sandbox `SyntaxWarning`，未导致失败。PostgreSQL 专用 lane 未连到 live PostgreSQL 执行。
- `pnpm --filter @ai-qa/web test` — **104 passed**。
- `pnpm lint` — **PASS**：Ruff、Ruff format（391 files）、i18n parity（25 namespaces / 2 languages / 2,850 keys）、ESLint。
- `pnpm --filter @ai-qa/web typecheck` — **PASS**。
- `pnpm --filter @ai-qa/web build` — **PASS**；保留 Monaco / worker 大 chunk 警告（TypeScript worker 约 7 MB，Monaco pane 约 4 MB）。
- `git diff --check` — **PASS**；最终改动已按独立 commit `7108b08` 提交。
- 活跃 API/Web runner 的健康探测：live、ready、Web root 均 HTTP 200。先前浏览了 17 个主要路由及空闲请求，未观察到 HTTP 错误。

## 代码审查

对最终服务逻辑、回归测试和真实 UI acceptance diff 做了聚焦审阅；新回归测试先复现缺少 `verification.completed`，再在修复后通过。该环境没有独立审查代理可用，因此这里是协调者代码审阅，不伪称第二位审查者的独立批准。未发现本次审阅范围内新的已确认 P0/P1 问题。

## 阻碍与遗留风险

1. **PostgreSQL/Docker：BLOCKED / NOT RUN。** 本机无 PostgreSQL/Docker 服务或可用测试 URL；不要把 SQLite 结果等同于 PostgreSQL 集成通过。
2. **完整 Worker 接受：BLOCKED / 有意不运行。** `runtime/ai_qa_platform.db` 中已有 200 个意图未知的 queued jobs。未启动 Worker、未领取或改动这些任务。要补测，必须先准备隔离数据库和仅用于测试的队列数据。
3. **Playwright bundled Chromium：BLOCKED。** 当前 macOS 12 不支持所需的 bundled Chromium 安装；浏览器接受使用已安装的系统 Chrome，未用它替代真实 Provider。
4. **Python language-server：SKIPPED / BLOCKED。** `basedpyright` / locked Node binary 依赖无法在该主机安装；language-server 集成未验证。
5. Windows/Linux 远程 CI lane 本地未执行。构建仍有大型 Monaco worker chunk 警告。
6. 现有 API/Web development runner 保持运行；不要因本次交付而重启 Worker 或消费旧队列。

## 明早建议的安全续验

1. 确认本地 API/Web：`GET http://127.0.0.1:8000/api/health/live`、`/api/health/ready`、`http://127.0.0.1:5173/`。
2. 准备**全新隔离**的 PostgreSQL 或 SQLite 测试数据库与独立 workspace，先执行迁移和仅测试用 seed，再在该隔离环境运行 Worker 并验证并发、取消、崩溃恢复及失败隔离；不要配置 `runtime/ai_qa_platform.db` 作为 Worker DB。
3. 可选地重跑实时 UI 接受（使用既有安全 Provider 配置；不要打印环境或凭证），确认 AI/Jev 状态与 exact-node rerun 结果。
4. 在 CI 执行 PostgreSQL、Linux、Windows lanes，并记录原始状态为 `PASS` / `BLOCKED`，不把未运行的 lane 记作通过。

## 仓库与数据状态

- 实现基线：`6721b96`（baseline audit）、`e6e0d6f`（runtime reliability hardening）；本次补充修复：`7108b08`。
- 分支 `main`；本报告与截图为本轮接受记录。未 push。
- 历史 `.ai-runs/` 目录保持未跟踪、未提交且未改写；未将其内容混入交付提交。
- 未启动 Worker；旧队列保持 untouched；未重置本地数据库，未记录 Provider 凭证。
