# Task Runtime 信息架构与任务类型规范

本文件规范 Task Runtime 的信息架构、任务类型枚举、发起入口、上下文传递规则及安全控制边界。

---

## 1. 业务入口与任务中心架构

顶层业务入口收敛为 **Workspace**、**Automation Studio**、**Live Workflow**、**Library**，并保留管理与历史查询页面。
原孤立的 Agent 页面更名为 **任务中心**（`/workflow` / `/tasks`），定位为跨业务的执行观察、人工审批与复盘入口。

业务操作（需求分析、录制生成、失败修复、测试探索等）直接在对应业务上下文中发起，由系统自动组装完整的上下文对象（项目、工作区、URL、nodeid、失败证据等），杜绝用户手动填写冗长 JSON。

---

## 2. 真实 TaskType 枚举与入口映射

代码依据：`packages/project-model/project_model/task_models.py` 中的 `TaskType` 枚举：

| TaskType | 用户发起入口 | 自动传入的上下文 | 产出与后续流转 |
|---|---|---|---|
| `QA_GOAL` | Workspace 顶部“QA 目标”输入框 | 项目、工作区、目标自然语言描述、可选关联 Scope IDs | 经 `POST /api/tasks/preview` 生成契约与 Preview Token；执行前校验 Token，支持暂停/恢复与步骤重排 |
| `ANALYZE_REQUIREMENT` | Workspace 需求面板“分析需求” | `project_id`、`inputs.requirement_id`、关联用例与验收标准 | 执行 `requirement.analyze`，子阶段作为 Task Event 投影，结果写入 `qa_model.history` 并切到测试设计 |
| `CREATE_TEST` | 浏览器录制器“生成测试”；工作室侧栏“生成测试” | 项目、工作区、URL、结构化录制步骤、页面快照 | 生成 Playwright Python 代码，经人工审批与 pytest 运行验证后，登记为 TestCase 与 Binding |
| `EXPLORE_PAGE` | 浏览器录制器“AI 探索当前页” | 项目、当前 URL、Recorder 浏览器会话 | 循环执行观察、候选元素提取、Jev 动作决策与页面验证，生成结构化探索轨迹 |
| `FIX_FAILURE` | 失败详情页“自动尝试修复” | 失败 ID、测试 nodeid、源文件路径、失败截图与 DOM 快照 | 提取失效 Locator，Jev 选择候选，Playwright 验证，生成 diff 提议；等待用户审批 |
| `OPTIMIZE_TEST` | 测试用例详情“AI 优化” | 当前 Automation Binding 的文件、nodeid 和工作区 | 提出 Page Object 重构或性能/等待条件优化建议 |
| `REVIEW_TEST` | 测试用例详情“AI 审查” | 当前 Automation Binding 的文件、nodeid 和工作区 | AST 静态规则检查与反模式诊断（如断言旁路、脆弱定位器） |
| `RUN_REGRESSION` | 执行与运行器“AI 回归” | 原 TestRun 范围、环境配置、浏览器 tags、pytest markers | 调度既有 TestRunService 执行，聚合回归分析结果 |

---

## 3. 任务中心职责与安全审批

1. **执行状态观察**：实时展示任务状态机（`PENDING` $\to$ `RUNNING` $\to$ `WAITING` $\to$ `COMPLETED` / `FAILED` / `CANCELLED`），渲染 TaskStep 依赖 DAG 与 Timeline 事件。
2. **人工审批道钉**：
   - 涉及向工作区写入或修改代码的步骤（如 `source.apply_repair`），必须经由审批步骤挂起为 `WAITING` 状态。
   - 用户在界面审查 diff 并点击“批准”后方可继续执行；拒绝则终止写入流程。
3. **断线与恢复**：
   - Task SSE 支持 `Last-Event-ID` 回放，客户端刷新后无损重连。
   - 暂停在步骤边界生效；恢复时校验工作区源码语法完整性并重新计算未执行计划。
4. **真实 Provider 约束**：
   - 代码生成与修复路径必须依赖已配置的有效 AI Provider；Provider 不可用时阻断写入，严禁将 Mock/Fake 响应冒充为真实代码修改建议。
