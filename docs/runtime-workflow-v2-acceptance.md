# Runtime Workflow V2 验收记录

验收日期：2026-10-03（Asia/Shanghai）
项目：AI QA Platform
主样本：`a30fa4b4b92d450084e9cda36de1c16f`
验收方式：读取真实 API 与已持久化任务；未点击重试、重新规划、审批或取消等会修改任务状态的按钮。

## Before

原运行详情以任务明细为主，状态、步骤、时间、Trace、Browser 与制品之间缺少统一的运行时视图；从 URL 恢复所选步骤、按 blocker 定位、空数据解释和 TestRun 关联也缺少一致的呈现方式。V2 将同一个 Runtime Snapshot 用于 Overview、Flow、Timeline、Trace、Browser、Artifacts 与 Inspector。

## Problems

- 历史事件中的 `task.blocked` 未稳定投影为 `BLOCKED`，阻塞失败的 Trace 汇总也需要保留终态。
- 部分旧记录缺少 AI invocation 的 step ID 或时间戳，步骤时长可能显示为近零值或无法关联。
- 恢复动作必须受失败类型、失败步骤、写入/审批状态和预算约束；通用“重试修复”提示不适用于创建、优化、探索、回归或审查任务。
- `SKIPPED` 是终态，不能计入剩余步骤数；AI 响应正文没有持久化时，界面不能暗示仍可检查正文。
- 窄视口的 Timeline 固定宽度会造成横向裁切；Flow 与 Overview 的双栏应按工作区本身宽度响应，而不只按浏览器总宽度断点。

## Architecture

- 后端由 `RuntimeProjection` 从任务、步骤、事件、AI 调用、证据、制品、浏览器会话及真实 TestRun 关系投影统一快照；事件状态通过 normalizer 兼容历史格式。
- 前端 `RuntimeDetail` 负责运行时工作区、URL 步骤选择和视图切换；`runtimeModel`、`timelineModel`、`traceModel` 与 DAG 布局模块承载派生计算；各视图只显示快照中存在的数据。
- SSE 事件流支持初次读取、增量事件、断线续连和终态收敛；BLOCKED/FAILED 终态任务另有 15 秒低频刷新，并在页面重新获得焦点时立即读取，以发现其他会话发起的恢复。客户端对日志、帧、Trace 与事件窗口设置上限。
- Recovery 使用既有 Task API 与原步骤计划；按钮文案说明保留当前 DAG。重试提示现按任务类型生成。

## State Model

真实 API 共读到 13 条任务：9 条 `BLOCKED`、4 条 `COMPLETED`；本次没有 `RUNNING` 或审批等待中的任务。V2 按真实的 Task/Step/Run 状态投影，不为缺失事件、耗时或关联虚构数据。`SKIPPED` 被排除在剩余工作之外。

## Blocked Semantics

主样本是 `FIX_FAILURE`，目标为 `tests/test_shop.py::test_empty_search`。当前 Task 为 `BLOCKED`；11 个步骤中 4 个已完成、1 个失败、6 个待处理。阻塞点为 `repair`，失败类型 `AI_OUTPUT_INVALID`，后续步骤显示为被阻塞。Overview 同时说明 AI 未返回可执行源代码、目标测试尚未启动；Inspector 展示失败类型和诊断字段。

## Overview

主样本显示阻塞步骤、下一动作、AI 原因、目标测试未启动、步骤进度、AI/证据/TestRun/制品统计。`blocked-1366.png` 首屏能读到原因与目标测试未启动，但位于首屏下半部；关闭 Inspector 后，Overview 仍保留阻塞原因。原因也出现在 Inspector 的诊断卡中，形成一次重复呈现。

## Flow

主样本 DAG 有 11 步，失败 `repair` 节点及其依赖/下游关系按真实任务数据渲染。选择步骤会写入 `?step=`，切换视图和 reload 后保留；“清除步骤筛选”会删除 URL 参数并关闭选择。

浏览器内 Flow 区域实测：1366×768 为 y=519–765、高 246px；1440×900 为 y=494–782、高 288px；1920×1080 为 y=504–1022、高 518px。Flow 面板在三种视口内完整显示，11 步 DAG 通过内部滚动查看全图；1366 首屏能完整看到 blocker 节点。

## Timeline

Timeline 同时使用真实 Task、Step、AI invocation、Browser 和 TestRun 时间跨度；未知时间不伪装为 0，短于 100ms 的记录显示为 marker。主样本的 repair 与关联 AI 调用约 50.7 秒，任务耗时约 3:12。已移除 700px 的强制最小宽度，并收窄名称与耗时列，使窄工作区仍能显示横轴和事件条。

## Trace

Summary Trace 按真实 step 归并事件，保留错误摘要、provider/model 与可展开的原始事件；错误筛选包括失败、错误和阻塞状态。主样本中失败 repair 与其 AI invocation 正确关联。历史数据没有持久化 AI 响应正文，因此不能展示正文内容。

## Inspector

步骤检查器显示状态、工具、时间戳、耗时、重试次数、真实输入/输出、证据、AI invocation、Browser 和 Run 关系。没有保存 AI 正文时显示明确说明。Inspector 的长内容仍需纵向滚动；步骤标题和任务错误来自实际数据，可能包含英文。

## Live Events

真实页面经本地 API 打开；前端事件流与后端续连逻辑由单元/集成测试覆盖。主样本为终态 BLOCKED，验收期间没有真实状态变化，因此没有把“实时更新”描述为已经在运行中任务上验证。对可能从其他会话恢复的 BLOCKED/FAILED 页面，已增加 15 秒轮询和焦点恢复刷新。最终浏览器采集记录 0 个页面异常、0 个 4xx/5xx 响应。

## Task List

项目任务列表有状态筛选和项目切换。Golden Shop 项目实际有 2 条任务，均 BLOCKED；浏览器 E2E 以项目 API 返回值为期望值，验证“失败”筛选显示 2/2、“全部”显示 2/2，并保留当前任务详情。全局 API 的 13 条记录分布为 9 BLOCKED、4 COMPLETED。没有真实 RUNNING 或审批等待记录。

## Recovery Actions

主样本 API 给出 `inspect_ai_output`、`retry_step`、`replan`，并满足无效 AI 输出、失败点为 repair、未写入源码、`replan_count=0 < max_replans=2` 的恢复条件。实现过滤掉不安全或不适用的恢复资格；Retry label 和提示按任务类型选择。所有按钮均未实际点击，因此没有验证真实数据库中的重试次数递增、后续状态迁移或 SSE 重连。

## TestRun

主样本没有关联 TestRun（0 runs），不是一个可用来验证关联关系的样本。额外读取了两条真实任务：

- BLOCKED 的 `RUN_REGRESSION` 任务 `4b822e0b01e14ac78a58b2f063c7bdb9` 关联一个真实失败 Run `run_e2263234847d`（关系来源 `foreign_key`），并有 3 条 evidence、1 个 artifact、1 个 browser session；Overview 链接与 API 的 Run ID 一致。
- COMPLETED 的 `FIX_FAILURE` 任务 `90dcd29431d3436db1c0649081da619c` 关联一个真实 PASSED Run `run_22c9d37db7d2`，并有 9 条 evidence、1 个 artifact。

两个案例均通过真实 GET 与页面截图验证，没有写入或替换任何关联数据。

## Performance

- 1366×768、1440×900、1920×1080 均采集布局矩形和真实数据截图；Flow 区域如上可见。
- 前端测试验证 500 条事件在有界视口内呈现；日志、Trace、浏览器遥测与帧缓存有上限。还验证 10 分钟活动 span 不会逐秒缩放已完成行。
- 这次没有用真实 30 步任务做浏览器渲染压力测量，也没有对 500 条事件做端到端性能基准；对应结论只限于代码和单元测试覆盖。
- 生产构建把 RuntimeDetail 拆为约 73.88KB（gzip 21.79KB）chunk。Monaco 编辑器 chunk 约 4,031.71KB（gzip 1,043.98KB），Vite 发出大于 500KB 的 warning；这是现有编辑器 bundle 的后续拆包工作，不是 RuntimeDetail chunk。

## Backend Tests

从仓库根目录运行完整 Python 测试套件：429 passed、4 skipped、44 warnings，耗时 645.21 秒。4 个 skip 包含未配置 PostgreSQL 的集成用例；此前错误的 collection 尝试不计入结果。

## Static Checks

Ruff 规则检查通过；全量 Python 格式检查在 11 个文件上报告需要格式化，包含未改动的既有源文件和用户已有改动文件，因此没有批量重排无关代码。TypeScript 类型检查、前端 ESLint 和 i18n 检查通过。生产构建通过，并提示 Monaco editor chunk 超过 500KB。

## Frontend Tests

前端测试 67 passed、0 failed；TypeScript 检查通过；ESLint 通过；i18n 检查通过（21 namespaces、2 languages、1691 keys）；生产构建通过。

## E2E

浏览器脚本对真实 BLOCKED 主样本验证 Flow 选步、URL 持久化、tab 切换、reload 和清除筛选；对当前项目的 Failed/All 任务筛选计数进行 API 对照；另外打开真实 TestRun 和 COMPLETED 案例并核验 Overview Run 链接、Timeline、Trace、Browser、Artifacts 与 Flow 页面。最终采集结果为 0 个页面异常、0 个错误 HTTP 响应；Failed 与 All 筛选均为 API 期望值 2/2。真实关联的 FAILED Run `run_e2263234847d` 与 PASSED Run `run_22c9d37db7d2` 都显示在 Runtime 标题区并可进入。度量和场景细节见 `output/playwright/runtime-workflow-v2/capture-metrics.json`，各视口截图位于同目录。

## Code Review

独立代码复核最终版本为 PASS：未发现 P0/P1/P2 问题。复核指出的 BLOCKED/FAILED 终态不刷新问题已通过 15 秒刷新与窗口焦点/可见性刷新修复；恢复为活动状态后重新建立 SSE。`QUEUED` 状态已补中英文翻译。两项改动有前端状态映射断言；hook 的真实状态迁移仍受限于没有可用的活动任务验收样本。

## UI Review

独立 UI 复核结论为 PARTIAL。复核最新截图显示 Overview、阻塞原因和恢复动作可辨，Flow 选中 blocker 节点在 1366/1440 首屏可见，1920 可见更完整拓扑；1366 Timeline 的 0/111/222s 刻度和 3:12 耗时均可读、没有重叠，但步骤名仍省略且步骤组需滚动。Trace 首屏内容需继续滚动，Inspector 长内容也需滚动。Overview/Inspector 对阻塞原因重复一次；主要失败原因不是仅用颜色表达。真实 Run 链接在 Completed 和 TestRun 案例的标题区首屏可见。

## Product Review

独立产品复核认为主样本的状态、阻塞点、AI 调用时长与恢复资格一致；Blocked 首屏显示原因、恢复动作和目标测试未启动。随后补充的真实 RUN_REGRESSION 和 COMPLETED 案例已由只读脚本验证 Run 关联、FAILED/PASSED 状态、浏览器会话与制品；两条 Run 链接均在标题区首屏可见，Completed 链接本身不显示 PASSED，需打开 Run 才能确认结果。没有真实 RUNNING、等待审批或已执行恢复的任务，所以产品验收仍为 PARTIAL。

## Remaining Issues

- 当前 13 条任务中没有 RUNNING、WAITING/审批中任务，无法以真实流转验证这些视图和审批动作。
- 没有点击恢复按钮；重试、补充说明后的执行结果、replan 预算变化和 SSE 状态续连未进行真实写入验收。
- 实时终态轮询代码已增加，但缺少外部会话恢复同一任务的真实状态变更，尚未端到端验证状态转回 RUNNING。
- 主样本的 AI response body 未持久化，界面只能显示失败类型、provider/model 和 validation reason。
- 长 DAG、Trace 和 Inspector 仍需要内部滚动；未进行真实 30 步浏览器性能测试。
- 1366 Timeline 的步骤名仍会截断；Overview 与 Inspector 在真实失败样本中重复呈现一次失败原因。Completed 标题区可打开真实 Run，但 PASSED 状态需进入 Run 页面确认。
- Monaco editor bundle 超过 500KB 的构建提示待后续拆包。
- Python Ruff 格式检查仍有既有源文件待格式化；Ruff 规则检查本身通过。
- 本次测试生成的最后一个临时 basetemp 目录仍被其他进程占用，清理收到 Windows 文件占用错误；目录位于 `apps/api/.tmp-runtime-full-final-494a64c0fb5648388148173cd142bd2e`，未尝试终止占用进程。
- 验收没有创建提交；最终工作区状态见任务交付摘要。
