# AI QA Platform 产品架构与运行时集成指南

本文描述平台的产品架构骨架以及 Workspace、Automation Studio 与 Live Workflow 如何复用 Task、TaskStep、Run、Failure、Browser、AI、JEV、Artifact 和 Context 领域实体。

---

## 1. 产品原则与三大工作区

平台日常核心入口收敛为三大协同工作区域：

1. **Workspace** (`/workspace/:projectId`)：承载需求、测试设计、用例、自动化脚本、执行结果与失败恢复的连续闭环。
2. **Live Workflow** (`/workflow`)：全景展示持久化 Task、TaskStep、Run 及关联证据的运行 DAG，观察数据源自真实 Runtime Projection。
3. **Automation Studio** (`/studio`)：全功能桌面级测试工程环境，承载 Monaco 代码编辑、测试收集与运行、真实 debugpy DAP 调试与浏览器录制器。

> Requirements、Cases、Runs、Failures 等独立列表路由继续兼容保留，主要用于全局审计与跨项目查询。

---

## 2. Workspace 主工作台

`/workspace/:projectId` 是日常测试工程的主战场：
- **Context 侧栏**：列出当前项目关联的需求、测试用例、近期执行 Run 与工作区代码文件。
- **阶段流转**：主工作区按 `requirement → cases → automation → result → failure` 阶段平滑切换。
- **Inspector 侧栏**：展示当前选中需求、用例、运行或任务的深度元数据（业务规则、风险、覆盖缺口、最新证据与推荐动作）。
- **Runtime Mini Bar**：底部常驻条，是真实 Run Store 与 Task Runtime 数据的精简投影，实时显示当前 TaskStep/Execution、运行耗时、Blocker 状态及后端声明的恢复动作。

### 阶段切换与 URL Context
阶段切换在 URL 中无缝完成。通过 `apps/web/src/app/workspaceContext.ts` 解析和序列化上下文（包含 `project_id`, `stage`, `requirement_id`, `test_design_id`, `case_id`, `automation_id`, `task_id`, `step_id`, `run_id`, `parent_run_id`, `failure_id`, `browser_session_id`, `file`, `line`, `nodeid`）。
刷新页面完全从 URL 和后端 API 恢复业务状态；切换需求或用例时自动清理失效的下游对象 ID，防止跨实体串位。

---

## 3. Workspace ↔ Runtime 深度集成

### 需求分析流水线
- 触发时创建持久化 `ANALYZE_REQUIREMENT` 类型的 Task。
- Task 计划包含持久化 `analyze` TaskStep（工具为 `requirement.analyze`）。
- 服务层复用 `RequirementLifecycleService.stream()`；权威分析历史与结果保存在 Requirement 的 `qa_model.history`。
- 分析阶段从数据库读取 Requirement、Project 及至多 20 个关联 TestCase，结合验收标准与业务规则执行结构化分析。
- 细粒度子阶段（Project Context、Existing Cases、验收标准、AI 语义分析、业务规则、风险/歧义、Coverage Gaps、Test Design 草案、Jev 决策与 Coverage）作为持久化 Task Event 投影到 Runtime。
- **Workflow DAG 呈现真实 `analyze` TaskStep，子阶段作为 Task Event 呈现，不伪装成额外 DAG 节点。**

### Run 与 Failure 边界
TestRun、Task 和 Failure 保持严格分离的独立领域对象：
- Run 状态来自共享 Run Store 与 Runtime Projection。
- Task 状态来自 Runtime Snapshot。
- 失败恢复沿用既有 Failure Intelligence、Task DAG、人工审批、源码验证、目标测试重跑与验证服务。

---

## 4. Automation Studio ↔ Runtime

Studio 读取同一 URL Context，支持：
- **双向上下文传递**：携带当前 Project、Requirement、Case、Task、Run、Failure 和源文件位置。
- **优先级调度**：正在 Studio 发起的 TestRun 优先于 URL 中的既有 Run；Task Context 优先于其父 Run。
- **调试器集成**：Failure 深链启动真实的 debugpy DAP 会话，绑定到失败用例的 exact nodeid，Studio 卸载时自动关闭活跃调试会话。
- **Recorder 联动**：生成的 Python 脚本直接进入 Monaco 编辑器，保存后自动建立 Test Case 与 Automation Binding。

---

## 5. Live Workflow ↔ Runtime

`/workflow` 是统一 Runtime Snapshot 的全景观察视图：
- **Task 节点**：直接对应持久化 `TaskStep` 实体与依赖连线。
- **Run 节点**：直接对应真实 `TestRun` 与 `TestCaseExecution` 数据。
- **实体关联**：AIInvocation、JEV Decision、Evidence、Failure、Browser Session、Artifact 来自真实记录，缺失项标记为 `unknown`/`unavailable`，绝不虚构执行节点。
- **SSE 断线恢复**：Task SSE 支持 `Last-Event-ID` 回放；Run 状态通过共享 Run Store 进行多客户端聚合。

---

## 6. Failure Lifecycle & 安全闭环

1. 真实 Failure 由 Run / TestExecution 关联读取。
2. 诊断流程生成结构化 Repair Proposal 与精准 diff。
3. **人工审批道钉**：源码改动必须经过显式审批操作，平台严格禁止无人值守自动写文件。
4. **验证执行**：应用补丁后，平台发起只运行该原失败 nodeid 的新 Run；只有该 Run 真正 `PASSED`，修复历史才标记为 `VERIFIED`。

---

## 7. AI 与 JEV 的边界职责

- Requirement Analysis 复用 `ProductionQAOrchestrator` 与 `DecisionService`。
- Fake Provider 明确标注为模拟，绝不会被伪造成真实分析成功。
- 原始 Prompt 与隐藏推理过程不复制到公开的 Runtime Event 中；结构化分析存储在 Requirement 域，Runtime 仅保存可观测的运行阶段、关联 ID、计数与脱敏证据摘要。
