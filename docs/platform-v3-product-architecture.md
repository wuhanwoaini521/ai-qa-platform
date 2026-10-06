# AI QA Platform V3 产品架构

验收日期：2026-10-03。本文描述本轮代码落地的产品骨架；已有实体和执行能力以仓库实现为准。

## 产品原则

产品日常入口收敛为三个工作区域：

1. **Workspace** 承担需求、测试设计、用例、自动化、执行结果和失败恢复的连续工作。
2. **Live Workflow** 展示已有 Task、TaskStep、Run 及关联证据的运行过程，观察数据来自现有 Runtime Projection。
3. **Automation Studio** 承担代码编辑、测试运行、真实 debugpy 调试和 Recorder 操作。

Requirements、Cases、Runs、Failures 等历史入口仍然可用，主要用于查询、历史和管理；旧 URL 继续兼容。

## Workspace

`/workspace/:projectId` 是主工作台。Context 面板列出当前项目的需求、相关用例、近期运行和文件；主区域按 `requirement → cases → automation → result → failure` 阶段复用现有 Requirements、TestCases、Failures 功能；Inspector 展示当前需求、用例、运行和任务的真实数据。底部 Runtime Mini Bar 是现有 Run Store/Runtime 数据的精简投影，不制造进度或执行实体。

阶段切换在当前 URL 内完成。项目、需求、Test Design、用例、Automation Binding、Task、Run、Failure、Browser Session、文件、行、节点、步骤、阶段和返回位置通过 `workspaceContext` 读写 query string。Workspace 刷新后从 URL 恢复业务对象；失效对象只清理相应的下游 ID。历史 query 别名继续读取。

AI 分析、设计、生成和 TestCase 数据继续调用原服务。生成用例后，已有业务组件将真实生成的 ID 回传 Workspace；没有配置真实 AI Provider 时不展示 fake 结果。

## Live Workflow

`/workflow` 是完整执行观察入口。带 Task 或 Run 上下文时，页面直接复用 `RuntimeDetail` 和只读 Runtime Snapshot；节点与连线来自真实 TaskStep 依赖和 Runtime 实体，不创建 Planner/Research/Worker 等假 Agent。没有 Task/Run 上下文时保留已有 Task 列表。

Workflow 可由 Workspace Mini Bar 或工作台导航进入，并以同一 Context 返回 Workspace。可定位到真实文件的节点向 Studio 传递文件、行、Case、Failure、Run、Task 信息。Run 与 Task 是各自真实的领域对象，页面不会把 Run 伪装成 Task DAG。

## Automation Studio

保留现有 Monaco、文件树、测试收集、代码保存、TestRun、debugpy、Browser 预览和 Recorder。Studio 的 Runtime/Run 状态仍来自共享 Run Store；完整观察跳转到 Workflow。Failure 深链保留原失败、父 Run、nodeid、文件和行，并可启动真实 debugpy 会话。普通源码链接不自动启动调试，只有显式 Failure 调试深链会启动。

Recorder 仍使用项目内现有真实 Recorder 流程。本轮没有生成或保存新的 Recorder Case，也没有触发外部浏览器录制。

## Intelligence 与 JEV

Requirement、Test、Automation、Locator、Failure、Verification Intelligence 是附着在 Workspace、Studio、Failure 和 Runtime 上的能力，不是一级导航或假 Agent。现有 AI Provider/能力接口继续承担调用与校验；Failure 修复保留批准、校验、目标重跑等已有边界。

JEV 继续作为已有 Decision Layer，只有实际候选决策需要时才调用。Runtime 仅呈现已记录的 AI/JEV 事件、输入输出和证据；缺失信息显示为 unavailable，不补造虚拟节点。

## Runtime 与数据关系

底层实体保持分离：Project、Requirement、TestDesign、TestCase、AutomationBinding、Task、TaskStep、TestRun、Failure、BrowserSession、AIInvocation、Evidence、Artifact。Runtime Projection 组合真实关系，不建立巨型业务表。

前端通过按 Run ID 共享的 Run Store 合并实时事件、重连快照与 Browser Telemetry；Workflow 的 Task/Run 快照使用同一 Runtime Hook 和投影，终态刷新只用于持久化校准。Workspace 和 Studio 只呈现 Mini Runtime；Workflow 呈现完整 RuntimeDetail。领域写操作仍由原 API 命令承担。

## V3.1：Workspace、Workflow 与 Studio 联动

Workspace 中的需求分析通过 `ANALYZE_REQUIREMENT` Task 执行。Task 校验 Requirement 属于请求中的 Project；Runtime 中记录一个真实 `analyze` TaskStep，生命周期服务继续把权威分析历史写入 Requirement 的 `qa_model.history`。Requirement 阶段事件作为持久 Task Event 投影到 Runtime。现有 AI invocation 和 Jev decision 都带同一 Task ID、分析记录 Run ID，并归属当前 TaskStep；公开事件只保留经过筛选的阶段与摘要，不保存模型原始推理内容。

分析阶段从数据库读取 Requirement、Project 和至多 20 个关联 TestCase，并把这些事实随验收标准、业务规则一起交给现有结构化分析服务。Runtime 以内部 `workflow.step` 事件显示 Project Context、Existing Cases、验收标准、风险、覆盖缺口和测试场景阶段；这些事件来自实际加载、AI 结构化结果和持久化，不由前端定时器伪造。Runtime Mini Bar、Inspector 和 Workflow 都读取同一 Runtime Snapshot。分析仍保存在 Requirement 历史，Task Step 输出只保留关联 ID 和计数。

Runtime TaskStep 与 RequirementLifecycle 的子阶段有意保持两层粒度：Workflow DAG 节点是真实持久化 TaskStep；分析内部细阶段是真实持久化 Task Event，不伪装成额外 DAG 节点。Run 仍是 TestRun，不转换为 Task。Workspace、Studio 和 Workflow 的 Task/Run 选择优先级遵循 URL Context 的显式 ID。

用户在 Workspace 成功完成分析后留在同一 Workspace，需求面板切到设计视图；生成设计、创建 Case、打开 Studio、运行及失败处理沿用既有命令与实体。Workspace 嵌入式 TestCase 页面隐藏独立导航列表时使用单列布局，详情卡横跨主工作区，避免沿用独立页面双列网格后内容缩在左侧。

接口映射与失败恢复边界见 `platform-v3.1-runtime-integration.md`。

## Navigation 与 Context

主导航突出 Workspace、Automation Studio、Workflow、Library；项目概览有 Workspace 入口。Legacy `/tasks` 保留查询参数重定向到 `/workflow`，`/runs/tasks` 落在 Workflow，`/automation` 重定向到 Library。其他旧 Requirement、TestCase、Run、Failure、Recorder 路由仍保留。

跨界跳转统一通过 `workspaceContext.ts` 构造链接。Context 由 URL 显式携带；不会因切换需求或用例而意外继承旧 Run/Failure/Task/Browser/File 状态。

## Failure Lifecycle

Workspace 的 Failure 阶段嵌入现有 Failure Intelligence，保留分类、来源 Run、证据、诊断、修复适用性及验证链。不同分类仍由现有规则决定下一步；不在验收时对真实失败点击诊断、应用修复或重跑，避免改变 Golden Demo 业务记录。Failure → Studio 使用原 Failure 和父 Run Context；修复/重跑后结果仍使用原 TestRun、Task 和 Failure 关系。

## Developer Journey

- 日常：Workspace 内切换需求、用例、自动化和结果阶段。
- 观察：通过 Open Workflow 查看已有执行 DAG 和证据。
- 深度开发：从 Workspace 或 Workflow 携带 Context 打开 Studio。
- 调试：Failure 深链启动真实 debugpy；完成后 Studio 卸载关闭仍活动的调试会话。
- 历史：用 Library 和 legacy management routes 查询资料。

## 适用范围与后续

前端产品骨架复用已有执行数据和服务接口。AI Provider、流式接口、Failure 写操作和 Recorder 保存各自保留现有服务边界，不汇总为单一服务。
