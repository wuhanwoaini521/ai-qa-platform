# M1 基线快照（只读盘点）

状态：**已完成**（无产品代码改动）
基线 commit：`d66c531` · 分支 `main` · 盘点日期 2026-10-29
对应路线：[05-refactor-roadmap.md](05-refactor-roadmap.md) M1

---

## 1. 三域状态枚举 → 展示类别

### 1.1 原始枚举

| 域 | 枚举 | 取值 |
|---|---|---|
| Task | `TaskStatus`（`packages/project-model/project_model/task_models.py:28-42`） | PENDING, PLANNING, RUNNING, WAITING, VERIFYING, RETRYING, REPLANNING, PAUSING, PAUSED, RESUMING, COMPLETED, FAILED, BLOCKED, CANCELLED |
| TaskStep | `TaskStepStatus`（同文件 `:45-52`） | PENDING, RUNNING, WAITING_FOR_APPROVAL, COMPLETED, FAILED, SKIPPED, CANCELLED |
| TestRun | `RunStatus`（`project_model/models.py:58-65`） | QUEUED, RUNNING, PASSED, FAILED, SKIPPED, ERROR, CANCELLED |
| 单条执行 | `TestExecutionStatus`（`packages/qa-core/qa_core/execution/models.py:14-18`） | PASSED, FAILED, SKIPPED, ERROR |
| Discovery | `DiscoveryStatus`（`apps/api/app/services/quality_discovery_models.py:17-25`） | QUEUED, RUNNING, PAUSED, COMPLETED, BLOCKED, FAILED, STOPPED, BUDGET_EXHAUSTED |

### 1.2 → 展示类别映射（只读投影草案）

展示类别固定 7 个：`RUNNING` / `WAITING_HUMAN` / `SUCCEEDED` / `FAILED` / `STOPPED` / `BLOCKED` / `UNKNOWN`。

| 展示类别 | Task | TestRun | Discovery |
|---|---|---|---|
| RUNNING | PENDING, PLANNING, RUNNING, VERIFYING, RETRYING, REPLANNING, RESUMING | QUEUED, RUNNING | QUEUED, RUNNING |
| WAITING_HUMAN | WAITING, PAUSING, PAUSED | — | PAUSED |
| SUCCEEDED | COMPLETED | PASSED | COMPLETED |
| FAILED | FAILED | FAILED, ERROR | FAILED |
| STOPPED | CANCELLED | CANCELLED | STOPPED, BUDGET_EXHAUSTED |
| BLOCKED | BLOCKED | — | BLOCKED |
| UNKNOWN | 未列出值 | SKIPPED（见备注） | 未列出值 |

备注与判断依据：

- `SKIPPED` 是**单个 run 的集合级结论**（全部用例跳过），语义上不是成功也不是失败。映射为 `UNKNOWN` 会掩盖「没有执行任何用例」；映射为 `SUCCEEDED` 会造成假通过。**当前选择 `UNKNOWN` 并在 UI 标注「无有效执行」**，这是本轮唯一需要人工确认的映射。
- `BUDGET_EXHAUSTED` 归 `STOPPED` 而非 `FAILED`：预算终止不是产品判定失败。
- `TaskStepStatus` 不进展示投影，只在步骤视图内使用。
- Discovery 的 `STOPPED` 与 Task 的 `CANCELLED` 展示一致（都表示用户主动停止）。

---

## 2. 事件语义

| 域 | 存储 | 可寻址 | 重启后可读 | 当前位置 |
|---|---|---|---|---|
| Task | `agent_task_events` 表，自增 `id` 游标 | 是（`task_id`+`step_id`+`id` 索引） | 是 | `models.py:1048-1057` |
| TestRun | 无持久事件表；`log_output` 文本 + 进程内 `event_bus`（SSE） | 否 | 否（SSE 丢失） | `test_run_service.py:817,862` |
| Discovery | `result["events"]` 有界 JSON 数组 + `DiscoveryLiveHub`（进程内） | 否（只能按序读） | 部分是（DB 里的 JSON），live hub 丢失 | `quality_discovery_service.py:928-944,47-53` |

结论：

- 只有 Task 具备「提交后仍可重放」的事件能力。
- TestRun 的终态即使 SSE 丢失也能从 `test_runs` 行恢复（状态 + 计数 + `log_output`），**不需要新增事件表**。
- Discovery 的持久事件是有界数组，超限会丢最早的事件；这是设计选择，不是缺陷，但 UI 不能假设全量。

---

## 3. 注册工具清单与副作用类别草案

来源：`task_execution_orchestrator.py:598-636` 的 `dispatch` 字典，共 **39** 个工具。

| 类别 | 工具 | 说明 |
|---|---|---|
| `READ_ONLY` | `goal.coverage`, `goal.summary`, `goal.review_project`, `browser.inspect`, `discovery.collect_gaps`, `discovery.analyze_gaps`, `discovery.grade_gaps`, `discovery.summarize_gaps`, `decision.select_candidate`, `source.inspect`, `source.review`, `source.review_report`, `source.validate_generated`, `source.validate_workspace`, `failure.classify`, `failure.diagnose`, `failure.classify_run`, `source.inspect_failure`, `tests.compare` | 只读取/分析/校验，不改变工作区或外部系统 |
| `IDEMPOTENT_WRITE` | `requirement.analyze`, `goal.materialize_cases`, `tests.generate`, `failure.prepare_repair`, `source.generate_refactor` | 写入的是 DB 内任务输出/证据，按 step 键可覆盖；**LLM 调用的成本不是幂等性问题，但重复重试会放大费用** |
| `EFFECTFUL` | `browser.act`, `browser.agent`, `browser.verify`, `discovery.run`, `task.request_approval`, `source.write_generated`, `source.apply_repair`, `tests.run_generated`, `tests.run_regression`, `tests.run_target`, `tests.verify`, `tests.register_case`, `tests.resolve`, `tests.resolve_requirement` | 浏览器点击/导航、文件写入、子进程、外部注册；重复执行的副作用不可自动撤销 |

分类原则：**拿不准时归 `EFFECTFUL`**（保守）。其中 `browser.verify` 与 `tests.verify` 是否只做只读断言，取决于实现细节，M3 需逐一核实后再决定是否降级；在核实前不得默认重试。

与现状的差异：当前重试白名单包含 11 个工具（`task_execution_orchestrator.py:374-392`）：

`browser.inspect`, `source.inspect`, `source.validate_generated`, `source.validate_workspace`, `browser.verify`, `requirement.analyze`, `goal.coverage`, `goal.materialize_cases`, `tests.generate`, `failure.diagnose`, `tests.resolve_requirement`

对照草案的**风险点**：

- 白名单里的 `browser.verify`、`tests.resolve_requirement` 属于 `EFFECTFUL` / 边界工具，按草案不应默认重试。
- 白名单外的 `tests.run_generated`、`source.apply_repair` 等确实未被重试，方向正确。
- `tests.generate`、`goal.materialize_cases`、`requirement.analyze` 在 `IDEMPOTENT_WRITE`，重试可保留，但需要幂等键与费用上限；单纯靠工具名没有这层保护。

**本节是 M3 的输入，不在 M2 修改。**

---

## 4. 测试文件 → 里程碑矩阵

| 测试文件 | 覆盖 | 对应里程碑 |
|---|---|---|
| `apps/api/tests/test_task_lease.py` | claim / heartbeat / fenced finish / 恢复 | M2 对照、M7 |
| `apps/api/tests/test_task_cancel_fencing.py` | 取消与迟到写入 | M2 对照、M7 |
| `apps/api/tests/test_discovery_task_runtime.py` | Discovery 启动恢复、暂停/恢复、终态事件 | **M2 主入口** |
| `apps/api/tests/test_runs_and_failures.py` | TestRun 状态迁移、失败记录 | M2（TestRun 侧）、M5 |
| `apps/api/tests/test_job_reliability.py` | 分布式 job 回收 | M5 |
| `apps/api/tests/test_distributed_execution.py` | worker claim | M5、M7 |
| `apps/api/tests/test_worker_process_integration.py` | 真子进程、取消传播 | M5、M7 |
| `apps/api/tests/test_browser_runtime.py` | 会话空闲回收 | M7（重启场景） |
| `apps/api/tests/test_quality_discovery.py` | Discovery 主流程 | M2、M4 |
| `apps/api/tests/test_workflow_execution.py` | 已发布工作流执行 | 回归 |
| `apps/api/tests/test_architecture_boundaries.py` | 分层边界 | 全里程碑回归 |

---

## 5. 数据库基线

| 通道 | 命令 | 结果 |
|---|---|---|
| SQLite（默认） | `uv run pytest apps/api/tests/test_discovery_task_runtime.py -q` | 见 M2 验收记录 |
| OpenAPI 契约 | `uv run python scripts/export_openapi.py --check` | **PASS**（`OpenAPI contract is current`，exit 0） |
| PostgreSQL 16 | 需 `docker run postgres:16` + `AI_QA_TEST_DATABASE_URL` | **BLOCKED**：当前环境 `docker: command not found`，无本地 `postgres`/`psql`，无 5432 监听 |

> 环境变化说明：上一轮在 macOS + Docker 上取得的 PG16 定向结果（19 passed）**不能**在当前 WSL2 环境复现，也不能替代本环境的证据。按 `docs/QUALITY_GATES.md` §5.5 记为 BLOCKED。

---

## 6. M1 结论

| 项 | 判定 | 依据 |
|---|---|---|
| 状态映射表 | PASS | 枚举逐条来自源码 |
| 事件语义表 | PASS | 表结构 + 代码路径 |
| 工具清单与副作用草案 | PASS（草案） | 39 个工具全部分类，风险点已标 |
| 测试→里程碑矩阵 | PASS | 11 个测试文件 |
| OpenAPI 基线 | PASS | exit 0 |
| PG16 基线 | **BLOCKED** | 环境无容器运行时与 PG 二进制 |

M1 完成，可进入 M2。PG16 通道保持 BLOCKED，M2 的双库验收中 PG 侧将同样记为 BLOCKED，不得写成通过。
