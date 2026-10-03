# AI QA Platform V2 Architecture

2026-10-02。基于现有 React/TypeScript、FastAPI、pytest/Playwright 和 Task Runtime 收敛；没有新增 Agent Entity、技术栈或执行引擎。

## Domain

Project 是业务范围，Requirement 描述需求，TestCase 保存测试意图，AutomationBinding 关联 workspace/file/nodeid；Task 是有界工作流，Run 是实际测试执行。Failure、CaseExecution、BrowserSession、AIInvocation 和 Artifact 各自保留真实记录，RuntimeProjection 只组合这些记录。Execution Observatory 是观察视图，不是业务主导航或新的领域对象。

## Main Journey

Requirement → 分析/设计/用例 → AutomationBinding → Studio → Run → Failure。需求页保留分析、设计、覆盖和用例入口；旧数据的 TestDesignPanel 仍有真实调用，保留兼容。AI 流式失败应展示失败与真实 Provider 状态，不能静默切换 FakeAIProvider 宣称生成成功。Studio 根据实际 Binding 的 file/nodeid 运行，而不是从标题推断测试函数。

## Runtime

唯一 RuntimeDetail 在 Runs、Studio、业务 ContextTaskProgress 中复用。六个视图共享 selectedStepId 和同一只读快照：Overview、Flow、Timeline、Trace、Browser、Artifacts。Task 操作是 RuntimeTaskActions 的领域命令，独立于 Projection；没有在 GET Projection 中推进工作流或修改数据库。

Run Store 按 runId 管理 SSE、重连、终态协调和浏览器遥测。多个消费者引用同一 Store，一条 Run SSE；最后一个消费者退出释放订阅。Task 只在 useRuntimeSnapshot 建立一条 Task SSE；业务 hook 定时读取领域详情，不再重复订阅，updated_at 不再触发拆建连接。Projection 的轮询是持久化状态校准，不是第二套 Run reducer。

## Task/Run

`test_runs.task_id`、`parent_run_id`、`origin_failure_id` 为 nullable Foreign Keys。Task 的子 Run 正式写入 task_id；原 Run、失败和 retry/verification Run 用真实外键连接。旧记录只有可唯一证明的输出 run_id 才回填，歧义保持 null 并记录日志，禁止按时间/标题猜关联。取消状态不可被迟到 worker 或重连快照退回 RUNNING。

Task list 批量读取步骤：50 个 Task 为 2 次 SELECT，不再逐项 N+1。Projection 同样从持久化表批量组合，不创造时间戳、模型置信度或并行步骤。

## Failure

Evidence → FailureClassifier → AI/JEV 或明确规则边界 → Proposal → Diff → Approval → Apply → Target Run → Verification。AI 不可用时页面明确不可用；规则分类不等于模型诊断。用户提供修正或 AI-call budget 为 0 的真实规则路径可走审批和 pytest 验证，单独标明来源。

审批保存 unified Diff、完整真实 Artifact、base_exists 和 SHA-256。摘要有截断标志和下载入口；没有可审阅 Diff/基线时前端禁用批准。Apply 比较审批基线和当前文件，不一致则 BLOCKED 且保留修改；新文件用 exclusive creation。已有文件采用乐观并发检查：同进程检查与写入之间不让出事件循环，外部编辑器的极短文件系统竞态仍属于边界，未扩展成分布式文件锁。

## Studio

Studio 保留 Monaco、文件树、源码保存、Case 上下文、Run 调度、debugpy 和 Recorder 入口。执行结果嵌入 RuntimeDetail；原独立结果/日志/浏览器/制品 Runtime 标签实现已合并。空闲 demo 预览明确展示为演示，没有作为运行结果。

从 Failure 打开 Studio 携带 failureId/parentRunId，实际重跑继承原 browser/environment/runner profile 并写入 retry 关系；返回失败详情链接保留原问题上下文。Recorder/Debugger session 仍是进程内交互状态，不伪装成可恢复持久化 Task。

## Events

EventNormalizer 使用白名单和脱敏 metadata，限制字符串长度，拒绝非有限/负数 duration。Trace 不放原始 prompt、response、源码、整个 DOM 或 Browser Frame。完整源文件和 Diff 只通过领域详情/Artifact 审阅。

Run Store 上限：Trace/events 500，log entries 200、log text 20,000 字符，Network/Console/Browser steps 各 100，Browser sessions 32。帧按 session 保留最新值。日志后端也是有界文本；SSE 以内容差异发送 `replace: true`，相同长度的滚动尾部仍继续更新，重连不会重复拼接整段日志。

Live Event Stream 渲染可视窗口，用户滚动离开底部暂停自动跟随，Resume Live 恢复。Flow 布局只依赖真实 DAG 结构；状态/日志/帧更新不重新布局。Timeline 使用记录时间与明确标记的 derived 时间，运行中按真实时钟增长。

## Artifacts

只列实际存在的 Artifact，显示实际 name/type/source/step/run/case/created_at/size/content_type。认证下载返回实际文件；image、text、HTML report 使用有限预览，HTML sandbox 禁止执行，文本截断说明提供完整下载。历史 Browser frame 使用实际保存的最后帧，缺失证据不创造占位截图。

## Navigation

原审计中的 14 个目的地收敛为 7 个主入口：Dashboard、Projects、Requirements、Test Cases、Studio、Runs、Failures。Platform 可折叠，包含 Flaky、Quality、Security、Workers、Settings。Task 是 Runs 内工作流视图；旧 `/tasks` 深链重定向并保留 taskId。Recorder 是 Studio 的能力入口。正式概念统一，但旧路径/持久化字段保留兼容。

## Limits and evolution

无外部模型凭据时无法验收真实 AI Analyze/Design/Generate 和远程 JEV。真实 Task 工作流没有并行 sibling 调度，因此不生成伪并行截图。PostgreSQL 专用测试需连接环境；当前 SQLite 验证不能替代 PostgreSQL。Monaco 大分块和短屏 Flow 首屏高度为后续优化项。未新增 Replay、Redis、动态 Planner、成本引擎、持久化 Recorder/Debugger 或大规模 RBAC。
