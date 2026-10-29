# 目标架构与方案对比

状态：**建议（未批准）**。本文件不授权任何代码修改；Architecture Gate 结论见 `06-review-gate.md`。

---

## 1. 三个候选方案

| | A — 保守修复 | B — 现有边界内渐进重构 | C — 引入外部框架能力 |
|---|---|---|---|
| 核心主张 | 只修被复现的缺陷，不动结构 | 保留全部现有组件，统一所有权与写入语义，增量补列 | 用 LangGraph / Browser Use / Skyvern 承担编排或浏览器生命周期 |
| 改动面 | 单点 | 中，按域推进 | 大，跨系统 |
| 迁移 | 无 | 仅增量、可空列 | 数据与运行时双迁移 |
| 多实例 | 不解决 | 逐步解决 | 依赖外部实现，仍不保证副作用原子 |
| 框架依赖 | 无 | 无 | 有（含 AGPL 与 FastAPI 版本冲突） |
| 违反 §0 风险 | 无 | 低（若守住单一所有权） | **高**：极易形成第二套 Runtime / 浏览器所有者 |
| 证据基础 | 已复现的缺陷 | 已确认的缺陷 + 可测收益 | 无运行证据，仅来源元数据 |

### 为什么不是 A

A 能修掉 F3/F5，但不解决 F1/F2 的所有权缺口。Critic 已指出：现有证据证明的是**表示不一致**，不是**用户可见故障**——所以不能直接跳到「统一契约」。但完全不动也不对：Discovery 的两条执行路径与 TestRun 的进程内调度，是**已经写在代码注释里的**单实例假设，属于可测量风险，不是假想。

### 为什么不是 C

- LangGraph：官方文档明确「恢复时从节点开头重跑」，副作用必须幂等；它的 checkpoint 无法原子提交 Playwright、文件系统、Pytest 子进程与本项目数据库。直接嵌入等于第二套调度与检查点所有者，违反 §0 第 6 条。
- Browser Use：LLM-first 且以 agent 自评成功；与本项目「Pytest 退出码是唯一判定」冲突。它值得学的是索引失效校验、断连分类、停滞检测，不是接管浏览器。
- Skyvern：AGPL-3.0 且 manifest 声明 FastAPI `<0.137`，与本项目 0.141.1 直接冲突；自托管等于再引入一套任务/浏览器/证据所有权。
- 三者都没有任何本项目内的运行证据。

### 推荐：B′（Bounded B）— 现有边界内的有界重构

与旧研究中的「候选 B」不同，本方案**明确拒绝**统一事件存储与统一证据服务层。Critic 的观点被采纳：在三套生命周期之上再加一层抽象，会成为第四套影子状态。

B′ 只做五件事：

1. **所有权收敛**：每个执行域只有一个调度入口，且该入口的所有权语义写在数据库里或显式声明为单实例。
2. **写入原子化**：状态与其终态事件在同一事务内提交，提交后再广播。
3. **重试按副作用分类**：不再用工具名白名单隐式决定。
4. **增量补链接**：可空父列、真实外键、内容哈希。
5. **只读投影**：UI 通过一层只读视图统一展示，不改底层表。

---

## 2. 目标状态

### 2.1 所有权矩阵（目标）

| 关注点 | 唯一所有者 | 现状差距 |
|---|---|---|
| 工作流/任务调度 | `TaskRuntimeService` + `TaskSchedulerService` | 已满足 |
| Discovery 执行 | `TaskRuntimeService`（通过 `EXPLORE_PRODUCT` 任务） | 存在进程内 fallback（F6） |
| TestRun 执行 | `TestRunService` + `ExecutionJob`/`WorkerDaemon` | 本地路径进程内调度，注释自认单实例（F2） |
| Playwright 生命周期 | `BrowserRuntime` 适配器 | 已满足；无跨进程接管（F4，明确不作为本期目标） |
| AI 决策 | `DecisionService` + provider 注册表 | 已满足 |
| 测试判定 | Pytest 退出码 → `TestRunService._verdict` | 已满足，不得改动 |

### 2.2 状态与事件写入规则（目标）

1. 状态变更与对应的终态事件在**同一事务**内提交。
2. live/SSE 广播发生在 **commit 之后**。
3. 失败注入下，要么状态与事件都在，要么都不在。
4. 终态不可回退：迟到的 worker 结果必须被 fencing 拒绝，而不是覆盖。

### 2.3 重试规则（目标）

每个注册工具声明副作用类别：

| 类别 | 含义 | 重试 |
|---|---|---|
| `READ_ONLY` | 观察、读取、分析 | 允许（有界、指数退避） |
| `IDEMPOTENT_WRITE` | 可安全重复的写入（按 key 去重） | 允许，但必须有幂等键 |
| `EFFECTFUL` | 浏览器点击、外部写入、代码变更、子进程 | **默认不重试**；只有显式声明的可重试错误才重试，且需人工确认 |

现状问题：`task_execution_orchestrator.py:374-392` 用工具名白名单混合了只读与生成类工具。

### 2.4 数据增量（目标）

| 变更 | 类型 | 回滚 |
|---|---|---|
| `quality_discovery_runs.task_id`（可空，索引） | 增量列 | 可空，可保留 |
| `DiscoveryEvidenceORM.artifact_id` → 真实外键 | 约束修正 | 先回填再约束 |
| `stored_artifacts.content_hash`（可空） | 增量列 | 可空，可保留 |
| 事件表：不改结构 | — | — |

**不做**：统一事件表、统一证据表、跨域 schema 合并、删除任何历史字段。

### 2.5 只读投影（目标）

新增一个只读查询层（类似现有 `RuntimeProjection` 的定位），把 Task / TestRun / Discovery 映射为：

```text
ExecutionSummary:
  id, kind, project_id, owner_id
  domain_status            # 原样保留
  display_category         # RUNNING / WAITING_HUMAN / SUCCEEDED / FAILED / STOPPED / BLOCKED / UNKNOWN
  parent_task_id
  started_at, finished_at
  event_cursor_kind        # db_cursor | bounded_json | stream_only
  evidence_refs[]
```

约束：

- 只读，不写库。
- 不新增表。
- 原始状态字段必须保留，投影只加 `display_category`。
- 前端逐步采用；旧接口继续可用。

---

## 3. 明确排除

| 排除项 | 原因 |
|---|---|
| 引入 LangGraph / Browser Use / Skyvern 作为生产依赖 | 无运行证据；违反单一所有权；Skyvern 有许可证与版本冲突 |
| 新建统一事件存储或消息队列 | 现有 DB 事件游标已够用；新存储会形成影子真相 |
| 把 TestRun 迁入 Task Runtime | Critic 明确反对，无证据表明需要 |
| 跨进程浏览器接管 | 需要会话租约与网络化浏览器，成本远高于收益；ROADMAP §2 已列为进行中，不抢跑 |
| 重写 Workflow Studio | 它已经是正确形态（版本 + checksum + 幂等键），只需复用其模式 |
| AI 判定或自动修复扩展 | 与 §0 冲突；本轮不涉及 |

---

## 4. 预期收益（可测量）

| 收益 | 衡量方式 | 当前基线 |
|---|---|---|
| 终态与事件不再分叉 | 失败注入测试：状态与事件一致率 100% | 未测 |
| Discovery 单一执行入口 | 生产装配断言 `task_commands is not None`；fallback 仅测试可见 | 未测 |
| 重试行为可解释 | 每个工具的副作用类别有声明，测试覆盖三类 | 未测 |
| 跨域展示一致 | 状态映射快照测试覆盖三域所有状态 | 未测 |
| 证据可校验 | 同一工件 hash 一致，悬空引用为 0 | 未测 |
| 多实例安全 | 双 API 进程只允许一个执行者 | **BLOCKED** |

以上全部是**验收目标**，不是已获得的结果。

---

## 5. 与旧候选 B 的差异

| 旧候选 B | 本方案 B′ |
|---|---|
| 统一 `ExecutionRecord` / `ExecutionEvent` / `Evidence` 契约 | 不做统一契约，只做只读投影 + 增量列 |
| 双读双写 + 兼容适配器 | 不做双写；按域单点替换 |
| 可能新增事件/证据映射层 | 明确禁止新增映射层 |
| 迁移面覆盖所有域 | 迁移面限于 3 个可空列/约束 |

差异原因：Critic 指出旧 B 可能成为影子真相源，且缺少用户可见故障证据。B′ 保留了「改善所有权与一致性」的目标，去掉了「统一抽象」的部分。
