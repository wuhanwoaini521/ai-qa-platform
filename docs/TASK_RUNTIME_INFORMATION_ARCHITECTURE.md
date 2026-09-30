# Task Runtime 信息架构

## Before Information Architecture

总览直接展示六类内部 Task；独立的“Agent 工作流”页面再次要求用户选择任务类型、项目和工作区，并填写 URL、测试文件、失败 ID、执行环境 JSON、录制步骤 JSON 等。录制器、失败分析、测试用例和执行页面与这套入口并行，造成业务上下文重复录入。

## After Information Architecture

顶层业务页面保持为：需求与设计、测试用例、自动化工作室、浏览器录制器、执行与运行器、失败分析、不稳定用例、质量与发布、安全与权限。原“Agent 工作流”更名为“任务中心”，定位为跨业务的观察与操作页面。

| 内部 Task | 用户看到的发起入口 | 自动传入的上下文 |
| --- | --- | --- |
| `CreateTestTask` | 浏览器录制器“生成自动化测试”；自动化工作室侧栏“生成测试” | 项目、工作区、URL、录制步骤、会话状态、测试目标；工作室只要求 URL 与目标 |
| `ExplorePageTask` | 浏览器录制器“AI 探索当前页” | 项目、当前 URL、录制器会话 |
| `FixFailureTask` | 失败详情“自动尝试修复” | 失败记录、测试 nodeid、源文件、原 TestRun 的环境和浏览器配置；Trace 与截图由 Runtime 从失败记录收集 |
| `OptimizeTestTask` | 测试用例详情“AI 优化” | 当前 Automation Binding 的文件、nodeid 和工作区 |
| `ReviewTestTask` | 测试用例详情“AI 审查” | 当前 Automation Binding 的文件、nodeid 和工作区 |
| `RunRegressionTask` | 执行与运行器“AI 回归” | 原 TestRun 的范围、环境、浏览器、markers 和 Runner 配置；Runtime 仍通过现有 TestRun 服务执行 |

任务中心负责查看运行中、待审批、失败和已完成任务，以及步骤进度、Timeline、Evidence、Artifact、代码变更审批、取消和安全重试。任务详情可返回发起的业务页面。普通用户界面不再暴露 Runtime JSON 创建表单；步骤输入输出仍可在任务详情的折叠区域检查。

生成测试在用户审批、写入工作区并通过现有 TestRun 验证后，自动登记为 TestCase 和 Automation Binding；录制器或工作室因此仍是工作的起点，测试用例与自动化工作室是结果的归属位置。

## 验收路径

1. 浏览器录制器 → 录制步骤 → 生成自动化测试 → 页面内进度 → 任务中心审批 → 测试用例。
2. 失败详情 → 自动尝试修复 → 页面内进度 → 任务中心审查补丁、审批与验证。
3. 测试用例详情 → AI 优化或 AI 审查 → 页面内进度 → 任务中心查看变更或报告。
4. 执行与运行器 → AI 回归 → 既有 TestRun 执行结果与任务分析。

需要代码生成或修复的路径依赖已配置的真实 AI Provider；Provider 不可用时 Runtime 会阻塞写入，而不会把 fake 响应作为代码修改建议。
