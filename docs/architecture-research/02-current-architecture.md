# 当前架构与缺陷（基于 `d66c531` 的真实代码）

本文件只记录能从源码直接确认的事实。每条缺陷给出：问题 → 代码证据 → 根因 → 影响 → 改进方向 → 验证方法。
「源码确认」不等于「运行时验证」；未执行的验证一律标注。

---

## 1. 真实调用链

### 1.1 组合根与应用启动

```text
apps/api/app/main.py:109  lifespan
  ├─ init_db / Alembic
  ├─ recover_ai_invocations() / recover_failure_analyses()          (main.py:127-128)
  ├─ requirement_lifecycle.recover_interrupted()                    (main.py:130)
  ├─ _recover_stale_runs() → TestRunService.recover_stale_runs()    (main.py:137-141)
  ├─ task_runtime.start() → TaskSchedulerService.start()
  │     └─ recover_interrupted() → schedule loop                    (main.py:146)
  └─ recover_quality_discovery_runs()                               (main.py:147-156)
shutdown (main.py:170-175):
  engine.dispose → browser_runtime.close_all → debug_session.close_all
  → recorder.close_all → task_runtime.stop
```

组合根 `apps/api/app/container.py` 单例装配：`TaskRuntimeService`（`:428-434`）、`QualityDiscoveryService`（`:411-426`）、`BrowserRuntime`（`:495`）。

### 1.2 Task Runtime（注册工具 + 持久 DAG）

```text
TaskRuntimeService (task_runtime_service.py:19-57)
  ├─ TaskExecutionOrchestrator  —— 固定工具分派、步骤执行、重试判定
  ├─ TaskSchedulerService       —— DB claim / lease / heartbeat / 恢复
  └─ TaskCommandService         —— 创建、暂停、恢复、批准、取消、workflow_replay
TaskSchedulerService.start() → recover_interrupted() → _schedule_loop()
  → tasks.pending(limit, runtime_instance_id) → _claim()
      → claim_for_execution(owner, lease_seconds)   [DB 条件更新]
      → 写 RUNNING + task.started/task.planning 事件 → commit
      → _start_heartbeat()
  → _execute_task() → _execute_dag()
      → 依赖解析、并行批次、步骤执行
      → 终态写入 + 事件（同一 repository scope）
```

关键事实：

- 租约是**数据库级**的：`lease_owner` / `lease_token` / `lease_expires_at`（`persistence/models.py:950-953`，迁移 `0020_task_lease`）。
- 恢复是**围栏式**的：`finish_fenced(..., require_no_live_lease=True)`，拿不到才跳过（`task_scheduler_service.py:115-123`）。
- 取消通过独立列传播，不依赖进程内信号：`cancel_requested_at/by`（`models.py:954-957`，迁移 `0022`）。

### 1.3 TestRun / ExecutionJob（本地进程 + 分布式 Worker）

```text
TestRunService.create_and_execute_run()                    (test_run_service.py:291-323)
  ├─ runner_type=LOCAL  → _schedule_local_run() → asyncio.create_task → _RUN_WORKER_TASKS
  ├─ runner_type=WORKER → ExecutionJobORM → WorkerDaemon claim → HTTP 回报
  └─ runner_type=JENKINS→ 远端控制器
persist_suite_result() → _verdict(exit_code, ...)           (:838, :1149-1161)
recover_stale_runs()                                        (:1099-1117)
```

关键事实：

- 本地执行的所有权是**进程内字典** `_RUN_WORKER_TASKS`（`:139`，写入 `:443-458`）。
- `recover_stale_runs` 的 docstring 明确写：*"This assumes a single API instance."*（`:1107`）。
- 分布式 job 按 worker 心跳回收，而不是按 run 年龄（`:1107-1117`）。
- 判定函数只看退出码与解析结果数，缺结果一律 `ERROR`，不会因为「没有失败」而 `PASSED`（`:1149-1161`）——这是正确且必须保留的行为。

### 1.4 Quality Discovery（持久行 + 进程内循环 + 内存广播）

```text
API → QualityDiscoveryService
  ├─ _start()                       (quality_discovery_service.py:802-830)
  │    ├─ task_commands 已装配 → Task Runtime 创建 EXPLORE_PRODUCT 任务
  │    └─ 未装配 → _schedule() 进程内 asyncio 任务（:792-800）
  ├─ 状态/结果持久化 → QualityDiscoveryRunORM（JSON result + version 乐观锁）
  ├─ 结构化事实 → DiscoveryEvidenceORM（可查询索引）
  └─ live 广播 → DiscoveryLiveHub（进程内 dict，:47-53）
```

关键事实：

- Discovery **已经有两条执行路径**：Task Runtime 路径与进程内 fallback。生产装配走前者（`container.py:418-426`），测试/独立构造走后者。
- `result.events` 是**有界 JSON 数组**（`quality_discovery_service.py:934-944`），不是游标可寻址的事件表。
- 结构化的 `DiscoveryEvidenceORM` 与 `result.events` 是两套记录，职责不同但都描述同一次运行。

### 1.5 Workflow Studio（本轮最重要的状态变化）

```text
WorkflowDefinitionORM → WorkflowDefinitionVersionORM          (models.py:822-846)
  → save/validate/publish/compare/compile_plan                 (workflow_definition_service.py:208-343)
  → POST /workflows/{id}/launch                                (api/workflow_definitions.py:155-211)
      → runtime.commands.workflow_replay()                     [幂等键]
      → compile_plan(for_execution=True)
      → runtime.commands.create_workflow(...)                  [写 TaskORM + 步骤]
      → TaskSchedulerService 执行
```

关键事实：

- 已发布工作流是**用户可编辑的 DAG**，由 `TaskRuntimeService` 执行，不是第二套执行引擎。
- 幂等键 `workflow_idempotency_key` 有唯一约束（`models.py:921-927`），并绑定版本与 checksum（`:958-964`）。
- 迁移 `0019_workflow_definitions`、`0023_workflow_task_execution` 已落地。

> 这一项与旧研究文档「Workflow Canvas 只是观察器」直接冲突，以代码为准（见 `01-inheritance.md` O-1）。

---

## 2. 三个执行域的状态模型对比

| 维度 | Task Runtime | TestRun / ExecutionJob | Quality Discovery |
|---|---|---|---|
| 主表 | `agent_tasks` | `test_runs` + `test_executions` + `execution_jobs` | `quality_discovery_runs` |
| 事件 | `agent_task_events`（自增 id 游标） | SSE 流 + `log_output` 文本 | `result.events` 有界数组 + 内存 hub |
| 并发控制 | DB lease + token + 过期 | 无统一租约；本地为进程内任务 | ORM `version` 乐观锁（单行） |
| 恢复 | 围栏式 BLOCKED/CANCELLED，不重放 | 按年龄/心跳关闭为 CANCELLED | 陈旧行置 PAUSED（600 秒阈值） |
| 取消 | 独立列 + 心跳感知 | 进程内 cancel + 远端取消 | 进程内 stop event + 行状态 |
| 父链接 | 顶层 | `test_runs.task_id`（可空） | 无；靠 `result.runtime_task_id` 弱关联 |
| 证据 | `agent_task_evidence` / `agent_task_artifacts` | `test_executions` + `failure_records` + `ArtifactORM` | `discovery_evidence` + `result` JSON |

**结论**：三者都能工作，但**所有权与恢复规则不一致**。Task 是唯一具备多实例安全基础的域。

---

## 3. 缺陷清单

### F1 — 跨域父链接不完整（P1，独立评审修正为 PARTIAL）

- **问题**：Task / TestRun / Discovery 三套生命周期并存。**域内**链接是完整的（TestRun → executions → jobs → failure 均有外键）；缺的是**跨域**统一父列。
- **证据**：`models.py:265-313`（test_runs 内部 `task_id` / `parent_run_id`）、`:320`（executions.run_id）、`:721`（execution_jobs.run_id）、`:412`（failure_records.run_id）；Discovery 与 Task 的关联只存在于 JSON `result["runtime_task_id"]`（`quality_discovery_service.py:838`）。
- **根因**：三个域独立演进，Task Runtime 后接入，只有 TestRun 留了可空外键。
- **影响**：跨域查询靠适配器；无法用数据库约束保证子记录属于父任务；归档语义不一致。
- **改进方向**（按 Critic 建议降级）：给 `quality_discovery_runs` 加可空 `task_id` 列与索引，补齐 DiscoveryEvidence 的 artifact 外键；**不做**跨域统一契约层。
- **验证方法**：新数据父列非空断言；历史 NULL 允许；迁移可降级。

### F2 — 调度所有权不一致（P1）

- **问题**：Task 有 DB lease，TestRun 本地执行与 Discovery fallback 仍是进程内所有权。
- **证据**：`test_run_service.py:139,443-458` 与 `:1107`；`quality_discovery_service.py:792-800`；对照 `task_scheduler_service.py:169-192`。
- **根因**：Task 的租约是后加的（迁移 `0020`），其它域未回填。
- **影响**：API 横向扩容时，本地 run 与 fallback Discovery 可能重复执行或无人回收。
- **改进方向**：复用 Task 的 claim/lease/fenced-finish 模式，不新造机制。
- **验证方法**：双 API 进程 + 同一 run 并发创建，断言只有一个执行者（需多进程环境）。

### F3 — 状态与事件写入非原子（完成路径）（P1）

- **问题**：Discovery 正常完成路径仍是「更新状态 → 单独写事件 → 发布 live」，两次事务。
- **证据**：`quality_discovery_service.py:1099-1111`。恢复路径已改为单事务（`:898-912`），完成路径未改。
- **根因**：`_finalize` 先写状态，再调用 `_event`（`_event` 内部是 `_change_result` + `publish`）。
- **影响**：进程在两次写之间崩溃，会出现「终态但无事件」；反向顺序则可能「事件已广播但状态未提交」。
- **改进方向**：把终态与终态事件放进同一事务（复用 `persisted_event` 机制），提交后再发布。
- **验证方法**：在两次写之间注入异常，断言状态与事件要么都在、要么都不在。

### F4 — BrowserRuntime 无跨进程所有权（P1）

- **问题**：会话存在进程内 dict，`restore_session` 只是用 `storage_state` 新建会话，不是接管已有浏览器。
- **证据**：`adapters/playwright/browser_runtime.py:72`（`_sessions`）、`:225-231`（restore 直接 create）、`:329+`（close_all）；端口 `BrowserRuntimeSession` 无 owner/heartbeat 字段。
- **根因**：设计上浏览器是 API 进程资源，非共享资源。
- **影响**：API 重启后旧会话不可接管；多实例下无法判定会话归属。ROADMAP §2 已把「跨进程浏览器接管」列为进行中。
- **改进方向**：短期维持进程内所有权 + 明确失败语义；中期若要接管，需要会话租约与显式所有权，而不是共享浏览器进程。
- **验证方法**：重启后 `get_session` 返回 None 且不泄漏进程；不得声称已支持接管。

### F5 — 重试资格由工具名决定，而非副作用类别（P1）

- **问题**：步骤失败后是否重试，取决于 `step.tool` 是否在白名单里，而不是错误是否可重试、操作是否幂等。
- **证据**：`task_execution_orchestrator.py:374-392`。
- **根因**：白名单随工具增长追加，缺少副作用分类。
- **影响**：有副作用的生成类工具（如 `tests.generate`）与只读工具（`browser.inspect`）使用同一策略；新增工具容易漏判。
- **改进方向**：给每个注册工具声明副作用类别（只读 / 幂等写 / 不可重放），重试只看类别 + 错误类型。
- **验证方法**：对每个工具注入瞬时错误与不可重试错误，断言行为符合其声明类别。

### F6 — Discovery 有两条执行路径（P2，渐进收敛项）

- **问题**：`_start()` 在有/无 `task_commands` 时走不同路径。
- **证据**：`quality_discovery_service.py:802-808`。
- **根因**：为兼容独立构造与测试保留 fallback。
- **影响**：两套路径的恢复与并发语义不同，容易只测其中一条。
- **改进方向**：保留 fallback 但标注仅测试用；生产装配必须断言走 Task Runtime。
- **验证方法**：生产容器构造后断言 `task_commands is not None`；两条路径各有覆盖。

### F7 — 证据模型分散，缺少统一内容哈希（P1，独立评审修正）

- **问题**：`TaskEvidenceORM`、`DiscoveryEvidenceORM`、`TestExecutionORM`/`FailureRecordORM`、`ArtifactORM` 各自记录证据。归属并非完全缺失（`ArtifactORM` 有 `project_id`/`created_by`），缺的是统一 content hash 与严格的引用完整性。
- **证据**：`models.py:996-1028`（TaskEvidence 有 artifact_id 外键）、`:759-800`（DiscoveryEvidence 的 `artifact_id` 只是无外键字符串）、`:328`（execution 用 `artifact_paths` JSON）、`:431`（failure 用 `evidence_bundle` JSON）、`:751-755`（Artifact 有归属，但无 hash）。
- **根因**：证据按域各自建模，`stored_artifacts` 只存路径不存内容摘要。
- **影响**：跨域溯源靠多次 join 与字符串匹配；无法校验证据是否被替换；删除引用的对象后可能留下悬空字符串。
- **改进方向**（按 Critic 建议）：给 `stored_artifacts` 加 `content_hash`；把 `DiscoveryEvidenceORM.artifact_id` 改为真实外键。**不做**统一证据服务层。
- **验证方法**：同一产物在三个域的 hash 一致；悬空引用数为 0；迁移可降级。

### F8 — 本地执行已在子进程中运行，但编排存在两份（P1，独立评审修正）

- **问题**：本地 TestRun 通过 `subprocess.Popen` 启动 Pytest（具备进程级隔离），但「谁调度、谁回收、谁判定完成」存在两套编排：API 进程内的 `_RUN_WORKER_TASKS` 与 `ExecutionJob`/`WorkerDaemon`。
- **证据**：`packages/qa-core/qa_core/execution/pytest_runner.py:90`（子进程启动）；`test_run_service.py:436-458`（进程内调度）；`apps/worker/worker/daemon.py:25`（worker claim）。
- **根因**：单机模式与分布式模式共用一套服务，但调度路径分叉。
- **影响**：同一 run 在两种部署形态下恢复语义不同；进程级隔离不等于容器/最小权限沙箱。
- **改进方向**：短期统一恢复语义与状态写入；容器/网络/权限隔离属于部署层威胁模型，另行评审。**不要**把 TestRun 塞进 Task Runtime（Critic 明确反对，无证据支持）。
- **验证方法**：两种 runner 的终态、迟到结果拒绝、取消传播行为一致；沙箱能力单列安全门。

### F9 — 前端依赖后端状态词汇，缺少统一映射层（P2）

- **问题**：Task / Run / Discovery 的状态字符串各自直达 UI，展示语义靠前端判断。
- **证据**：三套状态枚举（`project_model/task_models.py:28`、`project_model/models.py:58`、`DiscoveryStatus`）。
- **根因**：无跨域 display category 映射。
- **影响**：新增状态时 UI 需要逐处适配；不同页面同一含义可能显示不同。
- **改进方向**：只读投影层提供 display category，保留原始状态字段。
- **验证方法**：对三域所有状态值做映射快照测试。

---

## 4. 应当保留的既有资产

| 资产 | 为什么保留 |
|---|---|
| `TaskSchedulerService` 的 lease + fenced finish | 已具备多实例安全基础，是其它域应当复用的模式 |
| `_verdict()` 的退出码判定 | 满足 ROADMAP §0 第 1 条，任何重构不得替换 |
| `BrowserRuntime` 端口/适配器分离 | 边界测试强制，且是唯一 Playwright 所有者 |
| `DecisionService` + provider registry | 已有预算、超时、置信度、fallback 语义 |
| Workflow 版本 + checksum + 幂等键 | 已经是「可发布 DAG」的正确形态 |
| `DiscoveryEvidenceORM` | 已是可查询结构化证据，不是需要推倒的临时结构 |
| 架构边界测试 | 防止 router 直接访问持久化、service 直接持有 ORM |

---

## 5. 未验证项（不得当作结论）

- 多 API 进程下 TestRun/Discovery 的实际重复执行行为：**BLOCKED**（需多进程环境）。
- PostgreSQL 16 全量套件：**BLOCKED**（仅定向 19 项已跑）。
- 真实 provider 的人工批准闭环：**BLOCKED**（QA-003 历史状态）。
- 浏览器重启后的资源泄漏：**UNKNOWN**（未做进程级观测）。
- 前端状态映射的实际不一致程度：**UNKNOWN**（未做 UI 走查）。
