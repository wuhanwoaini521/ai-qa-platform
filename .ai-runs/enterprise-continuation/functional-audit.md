# Functional Audit — 核心业务能力逐项核对

方式：以「实现存在 + 有真实测试 + 已在本机跑通」三档判定，不做「有页面即算完成」的推断。
`✅` = 本轮实际执行通过；`🔶` = 实现存在且单元/集成测试通过，但未做真实外层链路复验；`⛔` = 未执行。

## 需求分析

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 需求、验收标准、规则建模 | ✅ | 链路 A 创建需求 → AI 分析 → 场景；`req_golden_shop_v1` 含 AC-001… |
| 真实 AI 分析（provider 非 fake） | ✅ | 链路 A 断言 `history.provider not in {"", "fake"}`，实测 `openai-compatible` / `mimo-v2.6-flash` |
| 风险识别 | ✅ | Jev `requirement_risk_priority` 决策 `RISK-001`，confidence 1.0，`fallback_used: false` |
| 关系图 / 知识图 | ✅ | 链路 A 断言 Knowledge Graph 含 run / case 节点 |

## 质量发现（Quality Discovery）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 真实浏览器探索 | ✅ | 链路 C：`REAL_BROWSER_DISCOVERY` 真实 Chromium 探索本地站点，`states: 2, actions: 1` |
| 功能发现与 AI 归纳 | ✅ | `features: 3`，AI 调用 1 次（1017 in / 208 out tokens） |
| Jev 参与 | ✅ | 1 次决策，`fallbacks: 0` |
| 站点 / 项目作用域隔离 | ✅ | `test_real_local_discovery_preserves_target_and_project_scope` 通过 |
| 终态前 Quality Map 投影已持久化 | ✅ | `test_quality_discovery.py` 62 passed；真实浏览器终态读取含 `quality_map` / `coverage` / `workspace_test_scan`，修复了终态早于 projection 的 race |

## 测试用例

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 场景生成（AI + Jev） | ✅ | Jev `requirement_scenario_priority` → `SCN-002` |
| 用例创建并绑定到需求 | ✅ | 链路 A：`tc_721d2de77564` 关联 `req_b9d0d8438d20` |
| 用例 → 工作区 nodeid 绑定 | ✅ | 链路 A 断言绑定后 Run 可定位到具体 nodeid |
| Golden Demo 资产（需求/设计/用例） | ✅ | `proj_golden_shop_v1` 含 `req_golden_shop_v1`、`des_golden_009` 等真实数据 |

## 自动化工作台（Studio）

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| Monaco 编辑 / 工作区文件保存 | 🔶 | `/projects/{id}/studio` 真实加载（截图 + 0 控制台错误）；保存写回由 `test_live_locator_repair_acceptance.py` 的 `WorkspaceService.read_file` 断言覆盖 |
| 生产构建可用 | ✅ | `pnpm --filter web build` 成功（修复 OOM 后） |
| 断点 / 调试 / Live Browser | 🔶 | 单元与集成测试覆盖（`test_debug_session_service.py`），未做真实浏览器逐步验收 |
| AI 修复与运行同一上下文 | 🔶 | 失败修复 UI 链路已用真实浏览器跑通（见下） |

## 执行系统

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| pytest 执行 + Run/TestResult/Step/Evidence | ✅ | 链路 A `run_e44164a41992` → `status PASSED`，`evidence_count: 1` |
| Playwright 浏览器执行 | ✅ | 链路 A 生成并运行真实 Playwright 测试；链路 C 真实探索 |
| 执行隔离（工作区边界 nodeid） | ✅ | 全量后端测试含 `test_runner_failure_isolation.py` 通过 |
| Worker 分布式执行 | ⛔ | NOT RUN，无远程集群；`worker` 组件为 `LOCAL_EXECUTION_AVAILABLE`，`remote_workers: 0` |

## 失败修复

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 真实失败 → 证据 | ✅ | 链路 B 使用真实 Playwright 失败（目标 locator `#purchase-now` 不存在） |
| AI 诊断 | ✅ | `classification: LOCATOR_CHANGED`，`fallback: false`，latency 17.3 s |
| Jev 决策 | ✅ | `candidate_2`，confidence 0.9，`playwright_verified: true` |
| 人工审批才可写回 | ✅ | UI 链路断言 `"APPLY" not in allowed_actions` 时不写回；`WorkspaceService.read_file` 校验文件未变 |
| 精确复跑验证 | ✅ | 链路 B 选择 `get_by_role("button", name="Complete order", exact=True)` 并实际验证 |
| 低置信度诚实阻断 | ✅ | UI 链路实测 `confidence 0.52 < minimum_confidence 0.7` → `fallback_reason: below_minimum_confidence` → `repair_state: BLOCKED`，UI 显示「Jev 本次置信度为 0.52」且不提供 APPLY |

> 失败修复是本轮验证最充分的链路：既验证了「成功修复」，也验证了「低置信度时诚实阻断且不写回文件」。
> 这是 AI/Jev 不越权的最强证据。

## 覆盖率与质量分析

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 覆盖率口径（仅统计生效绑定 + 终态执行） | ✅ | D5 真实 C 链：发现 → AI/Jev → 人工 Playwright 用例 → ACTIVE binding → 浏览器 TestRun PASSED → 显式 refresh → 同一 feature/case/binding/run `VERIFIED`；API + Playwright UI 点击均实测，见 D5 补充 |
| 风险评分项目隔离 | 🔶 | `test_quality_risk_scoring.py` 通过 |
| 质量页面真实渲染 | ✅ | `/quality` 在真实项目上下文加载成功，0 控制台错误 |

## 真实 AI + Jev 一致性

| 检查 | 结果 |
| --- | --- |
| `/api/ai/status` | `REAL_CONNECTED`，`real_model_available: true`，`fallback_active: false` |
| `/api/decision/runtime-check` | `CONNECTED` / `READY`，`budget_available: true` |
| 是否存在「UI 显示 AVAILABLE 但真实请求静默回退」 | 链路 A/B/C 均断言 `fallback_used == false`，**未观察到静默回退** |
| 是否存在「实际可用但 UI 报不可用」 | **发现并修复**：健康探针预算 15 s < AI 请求超时 30 s，导致顶栏误报「部分能力受限」。见 `implementation-log.md` |

## 未完成清单（承接前任，本轮状态更新）

| 项 | 前任状态 | 本轮 |
| --- | --- | --- |
| 最终提交上的完整回归确认 | 未完成 | D5 commit `6b56261` 在提交前全仓 829 passed / 9 skipped；strict live harness因外部 provider timeout未重跑（见 `test-results.md`） |
| PostgreSQL 集成测试 | BLOCKED | 仍 **BLOCKED**（无 Docker / PostgreSQL） |
| Worker / Jenkins 真实集群 | NOT RUN | 仍 **NOT RUN** |
| Requirement → Coverage 链路独立复验 | 未完成 | 真实需求 → 用例 → Playwright 执行 → POST refresh → `VERIFIED` 已通过；后续跨租户/DB 多进程安全仍未验证 |
| Site Discovery 链路独立复验 | 未完成 | **已完成** ✅（链路 C） |
| Graph / Studio / Result / Discovery UI 最终复验 | 未完成 | Graph / Result / Discovery 已真实加载 ✅；Studio 深度交互为 🔶 |

## Round 2 supplement — Discovery terminal result readiness

- Confirmed a lifecycle race: Discovery exposed `COMPLETED` and `run.completed` before persisting the derived Quality Map; the real acceptance test could observe terminal state and cancel map work. Since the frontend stops polling on terminal state, users could see incomplete coverage.
- Fix committed in `02210de`: `QualityDiscoveryService._finish()` persists map before terminal status/event, marks unexpected projection failure `FAILED`, and maps with the intended terminal status. Per-run finalization lock serializes stop/pause/resume; a stop accepted before finalization yields `STOPPED`, while stop during finalization is rejected with HTTP 409. Execution cancellation marks STOPPED and a shielded finalizer survives repeated cancellation.
- Validation: `apps/api/tests/test_quality_discovery.py` → 62 passed; real local Playwright Discovery with AI `openai-compatible` / `mimo-v2.6-flash` (1 call, 1,017 input / 279 output tokens) and Jev `jev-1.13.0` (1 decision, no fallback) → 1 passed; terminal response includes persisted `quality_map`, coverage, and workspace-scan status. Log: `.ai-runs/enterprise-continuation/round-2/logs/live-discovery-finalization.log`.
- Workspace scan errors intentionally preserve the run with explicit `UNAVAILABLE` and automation coverage `NOT_VERIFIED`; they do not claim missing automation or PASS. Existing regression: `test_workspace_test_scan_failure_marks_automation_coverage_unverified`.
- Follow-up D5 committed in `6b56261`: downstream real chain passes: actual site discovery → real AI requirement/test generation → human-authored active Playwright binding → real browser TestRun PASSED → explicit coverage refresh → feature/case/binding/run all linked, `VERIFIED`. The real web UI button was clicked once and showed success; see test-results addendum for one green historical run plus the later stricter harness/provider block.
- Refresh uses a per-run same-process lock and requester/admin ownership boundary; latest execution is chosen by timestamp within the newest-first repository run list. Platform lacks project/team authorization: projects have no owner/team relation and RBAC roles are global; this endpoint boundary is not a substitute for system-wide project isolation. Multi-process/PostgreSQL locking/access behavior remains unverified.
