# AI + Jev 集成审计

审计日期：2026-10-07 至 2026-10-08（Overnight Architecture Boundary Audit V2）

## 2026-10-07 Architecture Boundary Follow-up

历史上真实浏览器 UI Golden 与 API-only AI/Jev Golden 均曾通过。随后一次重跑发现诊断请求以 `finish_reason=length` 在应用设定的 2,500-token 上限截断，workflow 因未完成 JSON 诊断而 BLOCKED。将诊断上限提高到 5,000、并收紧 prompt 输出长度后，真实 API-only 和真实浏览器 UI Golden 均通过；成功报告见本节下方的最新验收状态。

独立架构复审评分：Web → API A−、Page → Workflow A−、API → Application A−、Application → Infrastructure B、Core Boundary A−，Overall B+。复审未发现本次范围内遗留 P1；仍有 P2 级 BrowserRuntime/执行器粒度、DTO 展示启发式、查询投影与状态副作用、Onboarding 幂等性问题。最终完整后端回归为 **559 passed、6 skipped、45 warnings，1174.06 秒（19:34）**。PostgreSQL lane 在当前环境不可运行：未配置测试数据库，localhost:5432 无监听，Docker Engine 未启动，也没有本机 PostgreSQL 服务。

1440、768、360 宽度的真实浏览器截图中，桌面布局可读；较窄视口有内容裁切。本轮明确排除 UI 重设计，因此将此项记为非阻断 UI debt。

## 结论

Locator Repair 的真实后端 Golden Path 在隔离测试库和临时 workspace 中通过：旧 Locator 的 pytest 用例先失败，真实 AI 将规则分类 `ASSERTION_FAILURE` 修正为 `LOCATOR_CHANGED`，真实 Jev 从页面观测候选中选择 Locator，Playwright 验证候选，API 写入补丁，平台 Local Runner 重跑同一个 pytest nodeid 并通过，分析历史最终记录为 `VERIFIED`。本轮还捕获并修复了诊断响应 2,500-token 截断，修复后的 API-only 和 UI Golden 均通过。

全链路通过证据保存在 opt-in 测试 `apps/api/tests/test_live_locator_repair_acceptance.py`。该测试只有显式设置 `AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1` 才会运行；它只读读取本地已加密的 provider 配置，把密文复制到隔离测试库，不输出密钥，也不会改写开发数据库。

真实浏览器曾完成 Analyze、Apply、Verify 和精确测试 PASS。一次中间重跑因 Jev 低置信度走 Local Strategy 并保持 BLOCKED；另一次诊断请求被 2,500-token 上限截断。修复输出上限后，本轮 API-only 与真实 UI Golden 均通过。Local Strategy 不冒充 Jev pass。认证页面的浏览器状态恢复也未实现。

## Locator Repair 调用图

```text
FailuresPage
  → POST /failures/{id}/analyze/stream
  → FailureWorkflowService
  → FailureService.diagnose_failure_ai / AIProviderRegistry
  → 解析最终分类与页面证据候选
  → FailureService.generate_repair_proposal
  → 新建 Verification Browser，打开失败记录 URL
  → LocatorDecisionService / DecisionService.choose
  → Jev 选择候选
  → LocatorDecisionService.verify_candidate / Playwright
  → 返回已验证 Repair Proposal 与精确 diff
  → POST /failures/{id}/apply-repair
  → AST 限定到失败 test function 的单一 locator call，保存原文件及校验哈希
  → POST /runs，nodeids 仅包含失败的 test nodeid
  → TestRunService / pytest
  → POST /failures/{id}/analyses/{analysis_id}/verification
  → FailureWorkflowService.list_history 按真实 execution 状态持久化 VERIFIED
```

`Jev decides; Playwright proves`：候选只有在 Jev 确实返回、AI 诊断不是 fake/fallback、且 Playwright 验证成功时才允许 Apply。无候选、Jev fallback 或验证失败都会留下阻断原因，不能用 Local Strategy 冒充 Jev。

## Decision Runtime

`DecisionService.choose()` 是有门槛的决策入口：读取已保存运行配置，检查 provider、API Key、预算、请求大小与超时，对缺少置信度、低于最低置信度、预算耗尽、超时及 provider 错误作 fallback，并记录 invocation telemetry。Locator 决策现使用相同置信度门槛。

Settings 现在区分 Connectivity 和 Runtime。`POST /decision/runtime-check` 在静态预检通过后调用统一 `DecisionService.choose()`，因此 `READY` 同时要求实际决策通过置信度和运行策略；连接成功但低置信度会显示 `CONNECTED` + `BLOCKED`。独立 Test Connection 仍用于显示 API 连通性。

本次人工触发的真实 Runtime Check 曾返回 `CONNECTED`、`READY`、`enabled=true`、`provider=jev`、`model=jev-latest`、预算可用；真实决策响应返回的模型为 `jev-1.13.0`。真实 Locator 候选选择返回 `complete_order`、置信度 `1.0`、耗时约 `1512 ms`，fallback=false；Playwright 确认候选数量为 1、可见且 enabled。所有输出均未包含密钥。

## 场景调用矩阵

| 场景 | Rules / 本地策略 | Jev | LLM / AI | 执行与验证 | 审计判断 |
| --- | --- | --- | --- | --- | --- |
| Locator Repair | 候选证据与安全补丁约束 | 通过 `DecisionService` 选择 | 失败诊断与最终分类 | Playwright 候选验证；平台 pytest 精确复测 | **本轮修复 token 截断后，API-only 与 UI Golden PASS** |
| Browser Agent | 动作风险分类与候选过滤 | 歧义动作或强制策略下走共享决策入口 | 规划与动作建议 | Playwright 执行及页面状态检查 | **已接线；本次未做 live Jev 验收** |
| Recorder Locator | 实时页面候选生成；单一安全候选可直选 | 多候选时走共享 Locator Decision | 页面语义建议 | Playwright 验证后生成可复用步骤 | **已接线；本次未做 live Jev 验收** |
| Requirement Lifecycle | 风险和优先级信息 | 通过 `DecisionService` 选择情景/优先级 | 需求分析与场景建议 | 持久化 requirement lifecycle 结果 | **已接线；本次未做 live Jev 验收** |
| Failure Triage | 初始确定性分类 | 仅在进入 Locator Repair 后参与选择 | 根因诊断及分类修正 | 失败证据与源码上下文 | **AI 已验证；Jev 不承担 triage 分类职责** |
| Semantic Assertion Review | 确定性语义/风险审查 | 未接线 | 依现有 review 路径处理 | Assertion 检查 | **Jev 未接线** |
| Evidence Ranking | 本地证据排序 | 未接线 | 无统一决策调用 | 历史证据 | **Jev 未接线** |
| Regression Selection | 规则和历史信号 | 未接线 | 无统一决策调用 | Run 选择 | **Jev 未接线** |
| Agent Action Guard | 确定性风险及批准规则 | 不承担 guard 职责 | Agent 先提出动作 | 风险检查后由 Playwright 执行 | **Rule guard；不是 Jev 功能** |

关键接线位置：`apps/api/app/services/failure_workflow_service.py`、`failure_service.py`、`locator_decision_service.py`、`decision_service.py`、`task_runtime_service.py`、`recorder_service.py`、`requirement_lifecycle_service.py`。

## 修复内容

- AI 成功且非 fallback 时，最终 AI 分类不再被早期规则分类无条件覆盖；AI 分类无效或 AI fallback 时才退回确定性规则分类。
- 移除了 locator 候选的硬 token-overlap gate。旧 selector 与语义目标文字不同的候选仍进入 Jev，overlap 只影响顺序。
- Locator Decision 不再允许缺失 confidence 绕过最低阈值。
- Failure Analysis 在同一后端工作流里进入候选选择和 Playwright 验证，持久化 stage trace、分类来源、决策来源、候选和 patch diff。
- Apply 仅接受真实 AI + Jev、非 fallback、已 Playwright 验证的精确候选；限制到失败 test function 内唯一 locator 调用，持久化原文件、SHA-256 和回滚状态。文件在 apply 后被用户再次修改时拒绝覆盖式回滚。
- Apply 后前端同一主操作立即创建只运行原失败 nodeid 的 Run；Run 状态与分析记录关联，最终状态依据具体 execution 是否 PASS 决定。
- 增加 Jev Runtime Check，并在 Settings 明确分开显示 Connectivity 与 Runtime。

## 未覆盖与剩余风险

- Verification Browser 目前根据失败记录中的 URL 新开浏览器，没有恢复原 browser context、cookies、storage state、环境测试数据，也没有自动重放到失败 step 前。受登录保护的真实应用可能无法恢复到失败页面；当前 live fixture 是公开的 data URL 页面。
- 后端以 `FailureWorkflowService` stage trace、analysis result 和 repair proposal 字段持久化流程；还没有独立的 LocatorRepair 数据表或统一的强类型状态转换器。
- 真实 API-only 与浏览器 UI Golden 在本轮最终修复后均通过；普通前端回归为 97 tests passed，TypeScript、ESLint、production build 均通过。最终完整后端回归为 559 passed、6 skipped、45 warnings。PostgreSQL lane 因本机缺少运行中的数据库而 BLOCKED。
- 其他已接线场景本次只有代码路径/对应自动化测试审计，没有逐一使用真实外部 Jev 做验收。
- 现有 invocation telemetry 有 provider、model、decision、confidence、fallback 与状态，但尚未形成 Full Repair Success Rate 等修复漏斗指标/仪表盘。

## 验收命令

普通本地回归（真实 provider 测试默认跳过）：

```powershell
python -m pytest -q
```

显式执行真实 provider Golden Path（会调用已配置的 AI/Jev）：

```powershell
$env:AI_QA_RUN_LIVE_JEV_ACCEPTANCE='1'
python -m pytest apps/api/tests/test_live_locator_repair_acceptance.py -q
```

## Overnight Architecture Boundary Audit V2

### P1 完成状态

| 边界 | 状态 | 证据与限制 |
| --- | --- | --- |
| FailureRepairWorkflow | PASS | 状态、`allowed_actions`、apply/verify/retry/rollback 的权限由后端 workflow 计算；前端按后端 DTO 展示。修复诊断 token 截断后，API-only 与真实 UI Golden 均完成 PATCH_READY、Apply、精确复测和 VERIFIED。 |
| BrowserRuntime | PASS | Recorder、Task Browser Agent、Failure Repair/Locator Verification 与 Live Browser 通过 BrowserRuntime port/adapters 接入；Debugger 仅在适用的浏览器能力上复用。Live Browser 的 pytest 进程/session 仍有独立生命周期模型。 |
| TaskRuntime | PASS | 原大型服务已拆成 composition root、command、scheduler、orchestration、AI、browser、test execution、repair、evidence 等职责。两个预算 P1 已修复：任务上限在创建时读取 runtime 配置；Jev 决策会先预留 task AI budget，拒绝时不调用 provider。 |
| Repository Boundary | PASS | API routers 不直接访问 `AsyncSession`、ORM 或执行 SQL；`RuntimeProjection` 是有测试白名单的只读 Query Layer。 |

真实诊断最初以 provider `finish_reason=length` 截断在 2,500 tokens。将 `diagnose_failure_ai` 上限提高到 5,000 并约束 JSON 简洁度后，API-only 与 UI Golden 均通过；新增流式回归测试覆盖该上限。

### Architecture Boundary 评分

| 边界 | 评分 | 判断 |
| --- | --- | --- |
| Web → API | A− | 页面通过 REST/stream DTO 驱动 workflow；前端仍保留只影响呈现的分类归一、定位器解析和相关失败分组启发式。 |
| Page → Workflow | A− | 页面负责展示与调用，修复状态和动作授权由 `FailureWorkflowService` 决定。 |
| API → Application | A− | Router 负责请求校验、依赖注入、错误映射和响应；业务流程位于应用服务。 |
| Application → Infrastructure | B | Repository/port 边界已建立；`RuntimeProjection` 仍直接持有 Session 并执行只读 SQL，BrowserRuntime 的 `Page` 兼容边界也未完全隐藏 Playwright。 |
| Core Boundary | A− | AI、Jev、Rule 与 Executor 职责基本分离；真实 AI/Jev 最新 Golden 未稳定通过，因此运行可靠性不计为完成。 |
| Overall | B+ | 未发现本次范围内剩余 P1；真实 API-only 与 UI Acceptance 均已通过，下列为 P2。 |

### Client B 与 UI Replaceability

- API workflow tests 和 API-only acceptance 使用 HTTP API、workflow state、`allowed_actions` 与 events，不复用 React 逻辑；前端之外的调用路径已存在。
- Theme、布局和 Failure Repair UI 可以单独替换而不改变后端 AI/Jev/Repair 状态机。
- 本轮 API-only core Golden 在不启动 React 的情况下通过 HTTP workflow 完成 Apply、原 nodeid 精确复测及 VERIFIED；真实 UI Golden 也通过。因此“完全关闭 `apps/web` 后真实 AI/Jev Golden 当前 PASS”答案为 **YES**。

### 最新回归与格式状态

- Backend：`559 passed, 6 skipped, 45 warnings`，19:34。
- PostgreSQL：BLOCKED；缺少测试数据库 URL、监听中的 PostgreSQL 和启动的 Docker Engine。
- Web：97 tests passed；TypeScript、ESLint、production build 均通过。
- Ruff：`ruff check .` 通过；`git diff --check` 通过。此前检查的 146 个变更 Python 文件以及预算修复的 7 个文件通过格式检查；诊断预算变更涉及的 3 个 `qa-core` 文件已有整文件格式差异，单独格式检查仍报这 3 个文件，未批量重写它们。新增 Format Debt = 0。对整个 `apps/api` 与 `packages` 的宽范围检查共报告 10 个格式差异。
- 本轮 live AI/Jev Acceptance：API-only 与真实浏览器 UI 两项均通过。AI=`openai-compatible/deepseek-flash`，classification=`LOCATOR_CHANGED`，fallback=false，latency≈6.51s；Jev=`jev-1.13.0`，decision=`candidate_3`，locator=`get_by_role("button", name="Complete order")`，confidence=0.95，fallback=false，latency≈1.19s，Playwright verified=true。

### 独立 Review 与剩余 P2

独立 Reviewer 直接检查了预算修复与测试，没有发现剩余 P1。任务上限在创建任务时读取动态配置；Jev callback 被传入唯一的 `DecisionService` 决策入口，budget denied 时 stub provider 调用数为 0；locator decision 仍只预留一次。

1. `TaskBrowserExecutor` 仍约 3,000 行，包含观察、规划、安全、决策、执行和验证职责；`TaskExecutionOrchestrator` 仍约 700 行并保留兼容转发。
2. BrowserRuntime 暴露的 `Page`/locator 兼容面仍可见 Playwright 类型；Live Browser 的 worker/session 与单进程 BrowserRuntime 生命周期尚未完全统一。
3. `RuntimeProjection` 是只读查询层，但自身持有 ORM Session/SQL；依靠明确白名单维持边界。
4. Failure workflow 的部分 GET/read reconciliation 会写状态/事件，需继续梳理幂等和并发语义。
5. `failureWorkspaceModel` 的分类别名归一、失败 locator/错误摘要解析和相关失败分组属于展示启发式；它们不授予 Repair 动作，也不改变后端 workflow 状态。
6. Onboarding 重复 POST 尚无幂等 key；增加幂等性需为项目、测试入口、环境和参数建立稳定 fingerprint。
7. 缺少“强制 Jev + 预算耗尽 → 无浏览器动作”的组合回归测试；现有测试分别覆盖预算拒绝与 forced-Jev fail-closed。

### Removed

- 移除旧 `browser_proxy.py`，以 BrowserRuntime port/adapters 作为浏览器生命周期入口。
- TaskRuntime 不再将职责集中在旧的巨型实现中；运行入口收敛到拆分后的应用服务和共享 TestRunService。

### 最终判断

架构 P1 达标，Architecture Boundary V2 为 B+；真实 AI/Jev Locator Golden、API-only Golden、UI Golden 与最终后端回归均通过。Overall 为 **PARTIAL**：PostgreSQL lane 缺少数据库/Docker 环境；本轮验收临时目录清理也因 Windows ACL 在 `runtime/.qa-overnight-acceptance/pytest-budget-focused` 返回 Access Denied，未继续递归重试。`.ai-runs` 等原有运行数据未触碰。
