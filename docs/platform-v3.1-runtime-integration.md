# V3.1 Runtime Integration

日期：2026-10-03（Asia/Shanghai）

本文记录 Workspace、Automation Studio 与 Live Workflow 如何复用现有 Task、TaskStep、Run、Failure、Browser、AI、JEV、Artifact 和 Context 实体。主导航与产品 IA 仍按 V3 冻结，不新增一级页面。

## Workspace ↔ Runtime

### 需求分析

Workspace 的 Lifecycle 分析入口创建 `ANALYZE_REQUIREMENT` Task：

- `project_id` 是必需项；`inputs.requirement_id` 必须属于该 Project。
- Task 计划包含一个持久化 `analyze` TaskStep，工具为 `requirement.analyze`。
- Handler 复用 `RequirementLifecycleService.stream()`；Requirement `qa_model.history` 仍是 AnalysisRecord 与分析结果的权威存储。
- Project、Requirement、最多 20 个关联 Case、验收标准和业务规则来自当前数据库。实际处理阶段先写入 Requirement AnalysisStage，再写入 Task Event，Runtime 通过同一个 Runtime Projection 显示。
- 现有 AI Completion 和 Jev Decision invocation 关联 Task ID 与 AnalysisRecord ID。阶段 trace 归属 `analyze` TaskStep，Trace Summary 不包含 prompt、模型原文或隐藏推理内容。
- Task AI call budget 由现有 Runtime budget 预留；Task 重试使用现有 replan API 重跑失败的只读分析 Step。
- 成功输出仅包含 requirement/analysis record 关联 ID、风险/场景数和摘要 Evidence，不复制整份 Requirement 分析文档。

`workflow.step` 的子阶段包括需求输入、Project Context、Existing Cases、验收标准、AI 语义分析、业务规则、风险/歧义、Coverage Gaps、Test Design 草案、JEV 决策与 Coverage。所有状态由后端事件和持久化记录产生。Workflow DAG 仍只绘制真实 `analyze` TaskStep；Lifecycle 子阶段是 Task Event，不虚构 TaskStep。

Workspace Inspector 从已选 Requirement 与 Runtime Snapshot 显示 Summary、Business Rules、Risks、Ambiguities、Coverage Gaps、Analysis Evidence、Latest Finding 和 Recommended Next Action。分析运行时暂不显示上一轮分析的 Summary/Risk 数作为本轮结果；没有当前证据的值显示 Pending。成功后 Lifecycle 面板切到 Test Design 视图，Case 仍在 Workspace 内创建。

### Run 与 Failure

TestRun、Task 和 Failure 保持独立实体。Run 状态来自共享 Run Store 与 Runtime Projection；Task 状态来自 Runtime Snapshot。Runtime Mini Bar 仅显示真实当前 TaskStep/Execution、计时、计数、Blocker 与后端声明可执行的恢复动作。失败恢复继续使用已有 Failure Intelligence、Task DAG、人工审批、源码验证、目标测试、Regression 和 Verify 服务。

## Studio ↔ Runtime

Automation Studio 读取同一个 Workspace Context，从 URL 恢复当前 Project、Requirement、Case、Task、Run、Failure、Browser Session 和源码位置。Studio 的 Runtime Mini Bar 复用 `useRuntimeSnapshot` 与 `RuntimeMiniBar`；正在 Studio 发起的 TestRun 优先于 URL 中的既有 Run，Task Context 优先于其父 Run，避免用错误实体 ID 请求 Runtime。

Monaco、文件树、Test Explorer、Run、Browser/Recorder、QA Assistant、JEV Locator、debugpy/DAP 和 Failure 深链继续使用各自已有后端 API。Task/Run 的完整观察跳转到 Workflow；Failure 返回 Workspace/Failure Context。Mini Bar 不为 Studio 合成额外 Run 或调试状态。

## Workflow ↔ Runtime

Workflow 是统一 Runtime Snapshot 的完整观察视图：

- Task 节点直接来自持久 TaskStep 与依赖关系。
- Run 节点与 TestExecution 来自真实 TestRun 数据。
- AIInvocation、JEV Decision、Evidence、Failure、Browser Session、Artifact 来自各自已记录的实体。
- Task SSE 支持 Last-Event-ID 回放；Run 消费者按 Run ID 共享 Run Store。
- 默认落到 Flow/Canvas；Overview 是次级视图。
- 缺少的时间戳、来源和证据保持 unknown/unavailable，不推断执行状态。

Runtime Event normalizer 仅公开限定的 metadata key 与脱敏摘要。由 API 保存的 TaskEvent 和 AIInvocation 是唯一状态事实；客户端动画只呈现 RUNNING、FAILED、WAITING 等后端状态，不触发后端操作。

## Context Model 与 Deep Link

`apps/web/src/app/workspaceContext.ts` 是 URL Context 的解析/构造边界。Context 包含 project、stage、requirement、test design、case、automation binding、task、step、run、parent run、failure、browser session、file、line、node 和 return target。

主要往返：

- Workspace → Workflow → Workspace：保留同一个 task/run 与工作阶段。
- Workspace → Studio：保留需求、Case、Task/Run、Failure、源文件与返回位置。
- Studio → Workflow → Studio：保留 Studio Context 与当前源文件。
- Failure → Studio：保留 Failure、父 Run、Case、nodeid、文件和行。
- 刷新从 URL 与 Runtime API 恢复 Context，不依赖本地临时 React 状态。

Task 与 Run 的 ID 不互换。Run 当前激活时优先使用其 Run ID；若 Context 只有 Task，则请求 Task Runtime。切换 Requirement 或 Case 时清理失效的下游 ID，防止跨对象串位。

## Failure Lifecycle

真实 Failure 由 Run/TestExecution 关系读取。Diagnosis、Repair Proposal、Diff、Approval、Apply、Workspace Validate、Target Run、Regression 和 Verify 都使用已有后端实体及动作。`AI_OUTPUT_INVALID` 只有当模型结构化输出验证失败或输出不完整时使用；UI 显示后端 `recovery_actions` 支持的 Retry/Replan/Inspect 动作，不展示不可执行按钮。

若真实问题是 Runner/Browser 权限、Provider 不可用或外部环境，必须保留其真实阻塞原因，不能生成伪造代码修复。源码改动仍要经过 Task 的审批 Step。

## AI/JEV 边界

Requirement Analysis 复用 `ProductionQAOrchestrator`、结构化 `RequirementAnalysis` Schema 与 `DecisionService`。Fake Provider 不会被包装成成功分析。模型输入先脱敏并受现有请求预算限制；JEV 只在明确的风险/场景优先级决策处调用。Task、AI invocation、JEV invocation 和 TaskDecision 的关联字段为 task_id/run_id/step_id；provider、model、耗时、失败及 fallback 使用已有持久遥测。

原始 prompt、模型自由文本和隐藏推理不会复制进 Runtime Event。结构化分析保存在 Requirement 域；Runtime 保存的是可观察的运行阶段、结果关联、计数与安全 Evidence 摘要。
