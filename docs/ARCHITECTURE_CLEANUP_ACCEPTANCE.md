# AI 升级与架构清理验收（2026-10-02）

本报告对应 `5119a2e` 后的开发。区分 AI 新能力的结构成本与清理效果，不把新增代码量伪装成仓库整体缩减。

## 能力地图

| 能力 | 前端入口 | API / 应用服务 | 运行时 / 数据 |
|---|---|---|---|
| Projects | 项目管理 | projects / ProjectService | ProjectRepository / projects |
| Test Explorer | Studio 测试树 | workspaces、onboarding | pytest collection / 工作区源码 |
| Automation Studio | Studio 代码模式 | workspaces / WorkspaceService | Monaco / 工作区文件 |
| Python LSP | 编辑器、Problems | language_service / PythonLanguageService | basedpyright 子进程，无源码副本 |
| Browser / Recorder | Studio 浏览器模式 | recorder / RecorderService | Playwright 会话；本地录制草稿 |
| Test Runner | 执行与运行器 | runs / TestRunService | PytestRunner、共享 report plugin / runs、executions |
| Debugger | Studio、失败处调试 | debug / DebugSessionService | debugpy DAP / workspace_breakpoints |
| Tasks / Agent Workflow | 任务中心、业务页进度 | tasks / TaskRuntimeService | 持久化 DAG / tasks、steps、events、evidence、decisions |
| QA Assistant / Copilot | 助手、Case 生成入口 | qa-assistant、tasks | ProductionQAOrchestrator / 审批后落盘与执行 |
| AI Runtime | 各业务复用 | AIExecutionService | AIProviderRegistry / ai_invocations、预算预约 |
| Requirement / Test Design | 需求与设计 | requirements、design / AIService | 版本 prompt、schema / 需求与用例模型 |
| Failure Analysis | 失败分析与修复 | FailureWorkflowService、FailureService | 分类、FailureEvidenceService / records、analyses |
| Locator / Healing | 失败页、录制、Task | LocatorDecisionService、LocatorHistoryService | 共享排序 → Jev/本地策略 → Playwright / locator_history |
| Jev | Settings、候选决策证据 | decision / DecisionService | JevDecisionProvider / ai_invocations |
| Settings / Health | 设置、全局健康提示 | AISettingsService、PlatformHealthService | 流式探测与缓存 / ai_provider_configs |
| Worker | 分布式执行节点 | workers / WorkerRepository | durable daemon、lease、取消 / workers、runs |
| 外部集成 | 相应业务入口 | 集成 API | 保留真实 Jenkins、GitHub、Jira 等适配器 |

普通模型调用链：`业务 → ProductionQAOrchestrator → AIExecutionService → AIProviderRegistry → Provider`。共享执行层负责 usage、失败/取消和预算；业务负责证据、意图和审批。Jev 保留独立候选选择协议；决策事件区分 Jev 和 Local Strategy。

## Before / After

| 重复来源或指标 | Before | After |
|---|---|---|
| 主导航 | 14 | 13；Recorder 收进 Studio |
| Recorder | 单独主入口 | Studio 两种模式，旧 `/recorder` 兼容重定向 |
| Provider 状态 | 两个服务重复探测 | AISettingsService 一个实际状态源；Header、Settings、readiness 复用 |
| SSE | 两套前端解析，运行服务编码帧 | 共享 parser；API 编码，服务返回领域事件 |
| API 错误 | 只依赖 detail | 兼容 detail，同时提供 code/message/details/request_id |
| pytest 证据 | 第一条错误可能分配给多个失败、估算时长 | 共享 report plugin；逐 nodeid 错误、堆栈与真实时长 |
| 重试 | Provider/Task 可能叠加写入与执行重试 | Provider 管模型；Task 仅自动重试读取/校验 |
| Fake | 未知 Provider 可悄悄回退，模拟结果易混淆 | 未知名称报错；Fake 明示；模拟代码不能当已验证测试落盘 |
| 服务文件（含 init） | 40 | 45；新增 5 个实际职责服务，没有宣称服务总数下降 |

新增服务负责执行治理、失败证据、Locator 历史、readiness、LSP 生命周期。没有把独立职责塞进大类来凑数。Task Runtime、Recorder 仍较大，是保留的技术债务。

## Deleted 与兼容判断

删除 9 文件、676 行：583 行生产/兼容代码、93 行仅旧 Fake 测试。按 `git show HEAD:<path>` 统计，不包括 AI 升级新增代码。

| 删除项 | 引用证据 |
|---|---|
| worker/executor.py、jobs.py | 只有旧 Fake executor、导出和模拟测试使用；真实 daemon 不调用 |
| qa_core/contracts.py、fake_adapters.py | 只有旧 barrel/Fake 测试引用；真实模块已有领域合约 |
| qa-core/tests/test_qa_core.py | 只测试被删的 Fake；真实 pytest、worker、取消与失败回归保留 |
| integrations/contracts.py | FakeGitHub/FakeTestRail 只被 barrel 导出，没有应用消费者 |
| 三个 pages 单行 re-export | 路由直接导入 Automation Studio、Requirements、TestCases 的已有 feature |

保留明确模拟用途的 FakeAIProvider；保留有当前客户端、任务来源和书签价值的 URL、response.detail。没有删除用户工作区、运行产物或改写历史失败。

## 可观测性与信任边界

- UI/API/Python 共用有界失败证据；分类依据当前异常，不因源码出现 locator 就修 Locator。缺失截图、DOM、网络、源码分别列明。
- 分析保存上下文、日志、检查、AI、候选决策、建议和验证阶段，带来源、耗时、失败/取消和历史。展示证据与决策摘要，不保存模型私有推理链。
- `assert 1 == 2` 的 Locator 修复返回 422。Task 在 AI 修复前阻止没有明确意图的矛盾常量断言；其他 AI 修复也须保留原断言 AST。
- 候选可点击只代表 Locator 验证。分析之后新建、同工作区且只执行原失败 nodeid 的实际通过运行，才把分析标记已验证。
- 人工批准补丁后才写代码；公共 Playwright API 提案替换实际调用，限定失败函数。动态表达式、重复匹配、跨工作区补丁拒绝应用。
- Locator 历史计真实执行、候选验证与自愈；自愈只在补丁之后复测通过计数。分析认领与计数同事务，重复查看不重复计数。
- Browser Agent 有步数/访问约束和独立危险动作判断。满足可观察文本条件不等于整个业务目标已完成。
- Recorder 原稿和优化稿分开；重新生成替换当前稿。优化不能新增未录制动作/参数或删除断言；运行前明确标记待验证。
- 上下文最多 12 文件、24,000 字符，单文件 6,000；记录来源和遗漏，限制 import 深度，排除依赖目录、越界和符号链接。
- Usage 来自实际调用；未报告 tokens 保持未知。可用性要求真实流式请求成功，不凭 models 列表宣称健康。

## 实际验收

外部 AI 仅使用专门创建的合成项目 `proj_de0e7dd5362e`。首次本地 HTTP 服务退出的失败记录保留，没有伪造通过。

| 场景 | 实际结果 |
|---|---|
| 普通 AI | openai-compatible / space-bunny-free；真实生成、诊断、修复、录制优化，无 Fake 替代 |
| Jev | jev-1.13-free；真实选出 role 候选，Playwright 核验 |
| Case → AI → 审批 → 运行 → 原 Case 绑定 | Task `5c5f0a1ab34a4355ab197133b9ea0da2` COMPLETED；`run_08bb6884d0fc` PASSED |
| Python TypeError 修复 | Task `90dcd29431d3436db1c0649081da619c` COMPLETED；只补 quantity=2；`run_22c9d37db7d2` PASSED，全部断言保留 |
| Locator 精确复测 | `run_d749c300356e` PASSED，仅 test_locator_error；分析 `05ba606c-9d53-4979-8670-b2b4639f65a3` verified=true |
| 自愈历史计数 | 补丁后 `run_daf7b890e4fe` PASSED；连续三次查询历史保持 verified=true、locator_heal_recorded=true；事务认领回归确认只计一次 |
| Recorder | 1 编辑器、0 sticky 叠加行；Raw 6 → Optimized 4 步；`run_2ab40f56e809` PASSED |
| 实时浏览器 | `run_6ffff3838ed0` 执行录制生成的脚本，在运行期间收到实际浏览器帧；捕获脚本自行创建的同步 Playwright Page，保留操作后的页面证据 |
| Python LSP | 真实进程、补全、Hover、定义/引用、缺失参数诊断；UI 已连接 |
| 手动断点 | 调试当前文件；先停已启用自动断点，继续后命中手动第 13 行，堆栈 test_assertion_intent:13 |
| 主路由巡检 | 13 个主路由渲染可见，无 pageerror；此检查不等于全部业务分支验收 |

最终完整后端回归分组执行：API 240 passed、4 skipped（460.79 秒）；Core、Worker、Project Model、Integrations 110 passed（26.48 秒），合计 350 passed、4 skipped。覆盖新增历史计数、断言保护、Locator 调用替换、脚本自建浏览器与下一用例恢复。前端协议/错误/SSE 8 passed；typecheck、ESLint、i18n（1220 keys / 19 namespaces / 2 languages）、生产 build 均通过；变更 Python 文件通过 Ruff 检查与格式检查。

截图在 Git 忽略的 `output/playwright/`：ai-upgrade-task-review、task-completed、studio-lsp、failure-analysis、locator-proposal、locator-verified、debug-breakpoint、recorder-regenerate、recorder-optimized、settings、run-evidence、live-browser。这些都是实际运行页面。

## 未验证范围与剩余债务

- 本机 Docker Linux engine 管道不存在，没有运行的 PostgreSQL。不能把 SQLite 通过算作 PostgreSQL 验收；相关测试仍保留并跳过。
- Live 细粒度 telemetry 当前限同步 Playwright，每个用例观察第一个实际 Page；异步与多页面完整跟踪需单独接入。
- 实际 AI/Jev 会受上游延迟影响；readiness 单项 6 秒超时显示降级，不阻止基本测试执行。
- Task/Recorder 仍较大；没有仅为文件大小拆分。数据库沿用 additive schema 更新，版本迁移体系仍是后续债务。
- Locator 新页面验证不复用登录态；受保护页面可能缺乏自动验证证据。
- 优化对照属于前端会话状态；保存后的代码和 Case 持久化，不声称优化对照已跨会话持久化。
- 主导航减少一项；保留有独立价值的 Projects、Cases、Runs、Tasks、Failure，没有新增重复 Agent 页面。

复验：`uv run --no-sync pytest apps/api/tests apps/worker/tests packages/qa-core/tests packages/project-model/tests packages/integrations/tests -q`；`pnpm --filter @ai-qa/web typecheck`、`lint`、`test`、`build`；`uv run --no-sync python scripts/i18n_check.py`。真实浏览器和子进程需本机运行权限；限制必须如实记录。
