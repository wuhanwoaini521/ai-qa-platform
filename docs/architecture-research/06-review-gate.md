# 独立评审与 Architecture Gate 结论

日期：2026-10-29 · 基线 `d66c531` · 评审对象：`01`–`05`

---

## 1. 角色验证

三个 Claude Subagents 均已实际调用，行为符合配置：

| 角色 | 调用内容 | 结果 | 只读确认 |
|---|---|---|---|
| research-scout | 读取 `ports/browser_runtime.py`，概括端口职责 | 正确识别「端口不含 Playwright 导入，生命周期归适配器」，并主动标出端口无 owner/lease 字段 | 仅 1 次 Read，无写操作 |
| architecture-critic | 读取 ROADMAP §0，说明如何质疑框架替换提案 | 引用第 6/3/5 条，判定「第二套 Runtime」为 BLOCKER | 仅静态阅读 |
| qa-reviewer | 读取 QUALITY_GATES §2，回答判定词汇 | 正确区分单项状态与交付结论，指出 PG16 不可用应记 BLOCKED 且结论不得为 PASS | 未运行测试、未写文件 |

后续三个研究委派（LangGraph / Browser Use / Skyvern）与两个评审委派（架构复核、验收矩阵）均正常返回。
**未使用** bypassPermissions，未新增 MCP，未安装依赖。

---

## 2. Architecture Critic 复核结果

Critic 逐条核对了 `02-current-architecture.md` 的发现，结论如下：

| 发现 | Critic 判定 | 修正内容 | 处置 |
|---|---|---|---|
| F1 生命周期分散 / 无统一父链接 | **PARTIAL** | 域内链接是完整的（TestRun→executions→jobs→failure 均有外键），缺的只是跨域父列；Discovery 与 Task 仅靠 JSON `result["runtime_task_id"]` 关联 | 已改为「跨域父链接不完整」，改进降级为可空 `task_id` 列 |
| F2 调度所有权不一致 | **CONFIRMED** | 补充：Discovery 在注入 `task_commands` 时已走 Task Runtime，`_tasks` 只是 fallback，严重度低于原描述 | 保留 P1，M4 只收敛 fallback |
| F3 终态与事件非原子 | **CONFIRMED** | 完成路径仍为两次事务（当前行号约 `1125-1128`） | 作为 **M2 首个执行项** |
| F4 BrowserRuntime 无跨进程所有权 | **CONFIRMED** | `BrowserSessionORM` 是另一个概念（测试 worker 页面，有 worker_id，仍无租约） | **DEFER**：仅多副本才有意义 |
| F5 Workflow 版本/幂等键（正面） | **CONFIRMED** | — | 作为可复用模式，保留 |
| F6 BrowserExplorer stub | **CONFIRMED** | 全仓除自身 `__init__` 外无导入 | 仅在确认外部消费者后弃用 |
| F7 证据模型分散 | **CONFIRMED（细微修正）** | `ArtifactORM` 有归属（project_id/created_by），但没有 content hash；`DiscoveryEvidence.artifact_id` 是无 FK 字符串 | 改进降级为 `content_hash` + 外键 |
| F8 TestRun 未受信代码 | **PARTIAL** | Pytest 实际经 `subprocess.Popen` 执行，具备进程级隔离；真正问题是**编排复制**，不是「没有进程隔离」 | 已改写为「编排存在两份」；容器级沙箱另列安全门 |
| F5（我的编号）重试按工具名 | Critic 未单独复核 | 本轮由我核实 `task_execution_orchestrator.py:374-392` | 保留为 M3 |

### Critic 的核心反论点

1. **过度设计风险**：把 F1 + F7 落成「统一执行/证据契约」，会在三套生命周期之上再加第四套抽象，违反「复用现有边界」。
2. **更便宜的替代**：
   - F3 → 复用工作区已验证的 `persisted_event` 单事务写法（最小改动）。
   - F1 → 加可空父列 + 修一个外键，增量迁移即可。
   - F2 → 让 Discovery 无条件走 Task Runtime，删除进程内 fallback；**不要把 TestRun 塞进 Task Runtime**。
   - F7 → 给 `stored_artifacts` 加 `content_hash`，比「证据服务」便宜一个数量级。
3. **优先级**：先做 F3（小、真实崩溃窗口、模式已验证）；推迟 F1/F7 的「统一契约」与 F4 的端口租约。
4. **无法从源码验证**：是否真有多副本部署；F3 是否发生过真实崩溃；F2 是否有实测失败；BrowserExplorer 是否为规划功能；「F5 应保留」属于价值判断。

### Critic 的架构门态度

> **REFACTOR WITHIN EXISTING BOUNDARIES.**
> 仅批准 F3 的完成路径单事务化、F1/F7 的增量列修复、F2 的「Discovery 去进程内 fallback」。
> F4 统一租约、任何「统一执行/证据契约」DEFER，缺多副本证据与崩溃复现。

这直接决定了 `04-target-architecture.md` 采用 B′ 而不是旧候选 B。

---

## 3. QA Reviewer 验收矩阵

### 3.1 可执行项

| # | 场景 | 现有测试入口 | 通过标准 |
|---|---|---|---|
| 1a | Task 状态/事件/工件崩溃注入 | `test_task_lease.py`、`test_discovery_task_runtime.py` | 注入失败后无孤儿 event/artifact；`finish_fenced()` 为 False |
| 1b | TestRun 状态+事件原子性 | 需新增（现有 15+ 处独立 commit） | 事件写失败时状态不落地 |
| 2a | 单进程 claim | `test_task_lease.py`、`test_distributed_execution.py` | 仅证明条件 UPDATE 正确；**不算并发证据** |
| 3a | 暂停/恢复/取消 + 迟到结果 | `test_task_cancel_fencing.py`、`test_runs_and_failures.py`、`test_job_reliability.py` | 终态唯一、迟到写入被 fence |
| 4 | 超时与重试边界 | `test_worker_process_integration.py`、`test_task_lease.py` | 子进程真退出、重试有界、超时后释放租约 |
| 5a | BrowserRuntime 回收 | `test_browser_runtime.py` | 空闲回收、`close_all` 不悬挂 |
| 6a | PG16 双通道 | `docker run postgres:16` + `AI_QA_TEST_DATABASE_URL` | 同套用例全绿，逐条记录 skipped |
| 7 | 核心功能兼容 | `test_workflow_execution.py`、`test_quality_discovery.py`、`test_runs_and_failures.py`、`test_architecture_boundaries.py` | 全绿 |

### 3.2 只能记 BLOCKED

| # | 场景 | 缺什么 |
|---|---|---|
| 2b | 双 API 进程 / 双 worker 进程 claim | 多进程 harness（可仿 `test_worker_process_integration.py` 的 LiveApi + WorkerProcess） |
| 3b | 跨进程迟到 worker 结果 | kill 后重启 + 旧结果到达的故障注入 |
| 5b | 进程重启后的浏览器会话行为 | 真实进程重启 harness（现有测试全是进程内 monkeypatch） |

按 `docs/QUALITY_GATES.md` §5.5，单进程测试不能替代多进程证据。**在这三项转 PASS 之前，不得声称「运行时生命周期收敛」已通过。**

### 3.3 容易写成假通过的断言（必须避免）

1. 未设 `AI_QA_TEST_DATABASE_URL` 时 `@pytest.mark.postgres` 被静默 skip——`0 failed` 不等于通过，必须记录 skipped 计数。
2. 只断言 `task.status`，不核对 `finish_fenced()` 返回值与 event/artifact/execution 行数——终态可能由别处写入。
3. 只断言 SSE 收到事件，不验证「先落库、可 replay」——Discovery live hub 是进程内订阅者，重启即丢。
4. 顺序执行两次写入被当成「原子」——必须注入 commit 失败或崩溃点。
5. 超时只断言状态为 TIMEOUT，不查子进程是否真的退出。
6. 浏览器「恢复成功」只断言 context 非空，未做真实导航与进程级重启。

### 3.4 数据库口径提醒

`docs/RC_ACCEPTANCE.md` 中 PostgreSQL **18.6** 的全量通过记录，按 `QUALITY_GATES.md` §5.5 **不能替代 PostgreSQL 16** 的生产声明。
本会话已用隔离 PG16 跑通 19 项定向测试，但这不等于全量。

### 3.5 QA 总体建议

> **BLOCKED（就绪结论）**：2a/6a/7 可产出真实证据；多进程 claim、跨进程迟到写、重启后浏览器会话三条关键通道缺 harness。未验证前不得声称通过。

---

## 4. Architecture Gate 结论

**Architecture Gate: NOT PASSED（保持 DEFERRED）**

### 4.1 为什么不能通过

| 条件 | 状态 | 说明 |
|---|---|---|
| 有可复现的架构问题证据 | **PARTIAL** | 源码层面确认；缺少真实崩溃/多副本故障复现 |
| 方案不引入重复 Runtime | **PASS** | B′ 明确复用现有所有权 |
| 方案不破坏确定性判定 | **PASS** | Pytest 退出码权威未动 |
| 迁移可回滚 | **PASS（设计层面）** | 仅可空增量列；未演练 |
| 多进程 / PG16 验收 | **BLOCKED** | harness 缺失 |
| 外部框架比较 | **NOT PASSED** | 未安装、未运行，只有机制学习 |
| 法务（Skyvern AGPL） | **BLOCKED** | 未评估 |

### 4.2 通过 Gate 需要补齐

1. M2 完成后，用失败注入证明终态与事件不会分叉（SQLite + PG16）。
2. 建立 M7 的多进程 harness，把 2b/3b/5b 转为可执行。
3. 明确部署形态：产品是否真的需要多 API 副本。**如果不需要，F2/F4 应降级为文档约束，而不是重构。**
4. 若仍考虑外部框架，必须做同任务、同站点的受控对比，并记录成本、延迟、许可。
5. 人工批准。

### 4.3 本轮可以批准的范围

只批准 **M1（只读基线盘点）** 与 **M2（终态写入原子化）** 的设计与实施准备。
M3 及之后需要各自的设计门。

---

## 5. 本轮研究结论

| 维度 | 判定 | 依据 |
|---|---|---|
| 研究成果继承 | **PASS** | 继承矩阵完成，过时项已标注 |
| 当前架构分析 | **PARTIAL** | 源码证据充分；运行时故障未复现 |
| 框架机制学习 | **PASS（机制）/ UNKNOWN（兼容性）** | 官方文档与源码已读；未安装未运行 |
| 独立评审 | **PASS** | Critic 与 QA 均实际执行并给出可采纳的修正 |
| 目标架构设计 | **PASS（设计层面）** | B′ 已按 Critic 意见收敛 |
| 路线可行性 | **PARTIAL** | M1/M2 可立即开始；M7 依赖新 harness |
| 就绪评估 | **PARTIAL** | 可以进入 M1/M2；不能进入框架替换或跨域契约重构 |

**总体：PARTIAL**。研究可以支撑「有界重构」的决策，但不足以支撑「架构已收敛」或「可以横向扩容」的声明。
