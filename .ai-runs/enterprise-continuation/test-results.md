# 测试结果 / Test Results

所有结果均为在本机 WSL 上**实际执行**的输出，命令与日志路径一并记录，便于复核。
未执行的项目明确标记 **BLOCKED** / **NOT RUN**，不以旧报告代替。

## 1. 后端测试

| 范围 | 命令 | 结果 | 日志 |
| --- | --- | --- | --- |
| 基线复验（前任提交 `d8a2eef`） | `uv run --no-sync pytest apps/api/tests -q` | **819 passed / 0 failed / 9 skipped**（588.76 s） | 见 `recovery-audit.md` |
| apps/api 单目录（本轮修复后） | `uv run --no-sync pytest apps/api/tests -q --no-header` | **668 passed / 0 failed / 9 skipped**（718.37 s） | `logs/backend-regression.log` |
| 全仓最终回归（旧提交 `02210de`，早于 D5） | `uv run --no-sync pytest -q --no-header` | **820 passed / 0 failed / 9 skipped**（653.58 s，0:10:53） | `logs/backend-final-regression.log` |

> 说明：`apps/api/tests` 单目录收集 678 个用例；全仓 `testpaths` 还包含
> `packages/qa-core/tests`、`packages/integrations/tests`、`apps/worker/tests`，因此全量基线为 828 个用例。
> 最终回归 820 + 9 = 829 = 基线 828 + 本轮新增的 1 条后端回归测试，用例数对得上。

仓库 lint（不作为 pytest 的一部分）：`python scripts/task.py lint` → **All linters passed!**
（ruff check / ruff format --check 426 files / i18n 一致性 25 namespace · 3022 keys / OpenAPI 契约最新 / eslint 无问题）

## 2. 真实 AI + Jev 验收（非 Mock）

环境：`.ai-runs/enterprise-continuation/logs/live-chain-*.log`

| 链路 | 测试 | 结果 |
| --- | --- | --- |
| A 需求 → 执行 → 证据 | `test_live_enterprise_journey.py::test_real_requirement_to_execution_and_evidence` | **PASSED** |
| C 真实浏览器发现 | `test_live_enterprise_journey.py::test_real_local_discovery_preserves_target_and_project_scope` | **PASSED** |
| B 失败 → AI 诊断 → Jev → 审批 → 精确复跑（API 级） | `test_live_locator_repair_acceptance.py::test_live_ai_jev_repair_requires_approval_and_exact_rerun` | **PASSED** |
| B 失败修复真实浏览器 UI 链路 | `test_live_locator_repair_acceptance.py::test_live_ai_jev_failure_repair_through_browser_ui` | **PASSED**（诚实 BLOCKED 分支，见 §5） |

### 链路 A 证据（真实 provider + 真实 Jev，零 fallback）

```json
{"provider": "openai-compatible", "model": "mimo-v2.6-flash", "status": "PASSED", "evidence_count": 1,
 "decisions": [
   {"name": "requirement_risk_priority",  "provider": "jev", "model": "jev-1.13.0", "choice": "RISK-001", "confidence": 1.0, "fallback_used": false},
   {"name": "requirement_scenario_priority", "provider": "jev", "model": "jev-1.13.0", "choice": "SCN-002",  "confidence": 1.0, "fallback_used": false}]}
```

断言链：需求创建 → AI 分析 `history.status == SUCCESS` → `history.provider not in {"", "fake"}` →
存在 `provider == "jev" and not fallback_used` 的决策 → 生成 positive 场景 → 采纳为用例 →
绑定工作区 nodeid → 触发 Run → `run.status == PASSED` → 存在 browser session 与 external artifact →
Knowledge Graph 含 run / case 节点 → 重新打开需求后历史未被覆盖。

### 链路 C 证据

```json
{"status": "COMPLETED", "progress": {"states": 2, "actions": 1, "features": 3},
 "ai":  {"provider": "openai-compatible", "model": "mimo-v2.6-flash", "calls": 1, "input_tokens": 1017, "output_tokens": 208},
 "jev": {"provider": "jev", "model": "jev-1.13.0", "decisions": 1, "fallbacks": 0}}
```

### 链路 B 证据

```json
{"ai":  {"classification": "LOCATOR_CHANGED", "provider": "openai-compatible", "model": "mimo-v2.6-flash", "fallback": false, "latency_ms": 17287.8},
 "jev": {"decision": "candidate_2", "provider": "jev", "model": "jev-1.13.0", "confidence": 0.9, "fallback": false,
         "locator": "get_by_role(\"button\", name=\"Complete order\", exact=True)", "playwright_verified": true}}
```

## 3. 健康检查（真实调用）

| 端点 | 结果 |
| --- | --- |
| `GET /api/ai/status` | `REAL_CONNECTED`，`real_model_available: true`，`fallback_active: false`，model `mimo-v2.6-flash` |
| `POST /api/decision/runtime-check` | `CONNECTED` / `READY`，model `jev-1.13.0`，`budget_available: true` |
| `GET /api/ai/system-health?refresh=true` | 修复后 **overall healthy**，8/8 组件 `ok`（见 §5） |

## 4. 前端

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| Typecheck | `pnpm --filter web typecheck` | **0 errors** |
| Lint | `pnpm --filter web lint` | **0 problems** |
| 单元测试 | `pnpm --filter web test` | **157 passed / 0 failed / 0 skipped**（修复前 153，本轮新增 4 条） |
| 生产构建 | `pnpm --filter web build` | **成功**，43.4 s（修复前 OOM 崩溃，见 §5） |

构建产物提示 `MonacoEditorPane` chunk 4.03 MB（gzip 1.04 MB）超过 500 kB 阈值 —— 记录为技术债，非阻断。

## 5. 本轮修复对应的验证

| 缺陷 | 修复前 | 修复后 |
| --- | --- | --- |
| 验收夹具写死 `channel="chrome"` | 链路 A `1 failed, 1 passed`，报 `Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome` | 链路 A `2 passed` |
| Web 生产构建 Node 堆溢出 | `FATAL ERROR: Ineffective mark-compacts near heap limit … JavaScript heap out of memory`，exit 134 | `pnpm --filter web build` 成功 |
| AI 健康探针预算小于 AI 请求超时 | `ai` 组件 `warning` / `PROBE_TIMEOUT (15010 ms)`，总状态 `degraded`，顶栏 3/3 页显示「部分能力受限」 | `ai` 组件 `ok` / `READY (3474 ms)`，总状态 `healthy`，顶栏 **0/3** 页显示 |

## 6. 浏览器 / UI 验收

- 12 个主页面在真实项目上下文（Golden Demo `proj_golden_shop_v1`）下全部加载成功
- 控制台错误 **0**，`pageerror` **0**
- 1440 / 768 / 360 px 三档均无横向溢出
- 截图：`screenshots/*-1440.png`、`screenshots/failure-ui/{desktop,tablet,mobile}.png`

## 7. 未执行

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| PostgreSQL 集成测试 | **BLOCKED** | 本机无 Docker 与 PostgreSQL（见 `environment-audit.md`） |
| Worker / Jenkins 真实集群测试 | **NOT RUN** | 无可用集群；`worker` 组件当前为 `LOCAL_EXECUTION_AVAILABLE`，远程 worker 数 0 |
| 多分辨率/移动端截图 | **已完成**（1440/768/360） | — |

## 8. D5 continuation — Discovery → Coverage refresh (2026-10-16)

> 以下是当前 D5 未提交代码的真实验证；上方全仓 `820 passed` 早于 D5，不能替代本次最终回归。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| Discovery API/service regression | `uv run --no-sync pytest apps/api/tests/test_quality_discovery.py -q` | **64 passed / 0 failed** (32.19 s) |
| Frontend unit tests | `pnpm --filter @ai-qa/web test` | **160 passed / 0 failed** |
| Frontend typecheck | `pnpm --filter @ai-qa/web typecheck` | **PASS** |
| Frontend lint | `pnpm --filter @ai-qa/web lint` | **PASS** |
| Production build | `pnpm --filter @ai-qa/web build` | **PASS**, 3,405 modules; Monaco chunk 4,031.76 kB (1,043.99 kB gzip) warning remains |
| Real AI/Jev + browser Discovery→Coverage | `AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 QA_AI_TIMEOUT_SECONDS=60 QA_AI_MAX_RETRIES=1 uv run --no-sync pytest apps/api/tests/test_live_enterprise_journey.py::test_real_local_discovery_preserves_target_and_project_scope -q -s` | **1 passed / 63.29 s** |

Live chain evidence: run `qd_d8decd8513c540af`, local target `127.0.0.1:44269`, real AI `openai-compatible` / `mimo-v2.6-flash`, requirement `req_58d66c817ba4`, generated case `tc_f52bf659a447`, active binding `bind_cb07903a81e8`, actual pytest `run_f588b51d68fb` PASSED, refresh returned feature coverage `VERIFIED`; AI case generation `fallback_used=false`; Jev `jev-1.13.0`, one decision, zero fallback. No secrets or external sites were used.

The default 20-second AI timeout failed once with a real provider timeout; the successful retry used test-command-only `QA_AI_TIMEOUT_SECONDS=60 QA_AI_MAX_RETRIES=1`. Preserve as provider latency/stability risk, not a mocked pass.

Reviewer fixes: latest matching execution chosen by execution timestamp; concurrent refresh regression observes max projection concurrency 1; refresh endpoint tests requester/admin boundary and OpenAPI 403/404/409; UI clears refresh feedback when switching runs. The refresh button has not yet been clicked in a real app UI browser. Project-level ACL remains incomplete: RBAC is global and projects have no owner/team mapping. PostgreSQL, multi-process locking, worker/Jenkins and full final backend regression remain BLOCKED/NOT RUN.
