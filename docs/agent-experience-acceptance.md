# AI QA Platform — Agent Experience FINAL CLOSEOUT

日期：2026-10-04（Asia/Shanghai）

## Final Status

**Overall: FAIL**。不使用 PARTIAL：通过项、失败项和环境阻塞分别记录。实际浏览器操作证明 Workspace、Studio、Workflow、真实 Run 与 Debugger 都能运行，但第一次使用者没有通过“帮我测试这个需求。”启动测试任务；AI 请求失败或只返回文字，真实失败修复闭环没有验证通过。

## Acceptance Matrix

| Criterion | Status | Evidence |
|---|---|---|
| First-time User | FAIL | 能手动选择用例并运行；未发现自然语言 Agent 路径，诊断空流。 |
| QA Agent Discoverability | FAIL | Agent 能力藏在 Studio 助手内，Workspace 未形成自然入口。 |
| Natural Language Agent | FAIL | 文本回答没有启动任务、计划或 Run。 |
| Agent Plan | FAIL | 未生成可见计划。 |
| Agent Running | FAIL | 真实运行存在，但分析过慢且状态/阶段不够清楚。 |
| Agent Result | FAIL | 有真实 Run 结果，但没有完成 Agent 任务的汇总与验证。 |
| Next Best Action | PASS | 失败页正确提供“运行 AI 诊断”作为即时下一步。 |
| Workspace | FAIL | 严格首次使用发现目标未达成；1366×768 内容发现性仍弱。 |
| Studio | FAIL | 打开、编辑、保存、Run、Debugger 可用；Agent 任务与 Code Review 未成功。 |
| Workflow | PASS | 展示同一 Run 的真实状态、事件和失败证据；小视口可读性有债务。 |
| Failure → Repair → Retry → Verify | FAIL | 有不同 ID 的真实 Retry，但仍失败；没有可用 Proposal 或 Verify。 |
| Context Persistence | PASS | Workspace、Studio、Workflow 往返及刷新保留实体 context。 |
| Runtime Consistency | PASS | Workspace、Studio、Workflow 对同一 Run 均显示 FAILED。 |
| Golden Journey | FAIL | 未从自然语言计划走到经验证结果。 |
| Chromium | BLOCKED | 默认 bundled executable 在启动时遇到 WinError 5 / EPERM；Edge fallback 可用。 |
| Real AI | FAIL | Provider 有空流、超时、unavailable 和长时间 RUNNING。 |

## Environment

- Windows 工作站；仓库：D:\code\self-github\ai-qa-platform。
- Python 3.13.5；应用与真实界面运行在隔离副本 `.tmp-test-validation/closeout-runtime-20261004`，没有用主仓库 runtime DB 做测试写入。
- Playwright 默认 bundled Chromium/headless shell 无法启动；用系统 Edge 154.0.4258.37 通过 Playwright 完成真实页面操作和截图。隔离副本的测试 fixture 临时选择 Edge，断言未修改。
- 应用服务已停止；11 个本轮明确创建的探测脚本已删除。截图、运行 DB 和运行制品保留为验收证据。

## Chromium Investigation

- Playwright bundled `chromium_headless_shell-1243` 启动返回 `PermissionError(13) / WinError 5`，Node/Python 中对应的 `spawn` 表现为 `EPERM`；失败发生在浏览器进程启动、导航和应用代码执行之前。
- Node 子进程、Python 子进程、系统 Chrome 154.0.8037.58 和系统 Edge 均可启动。对 bundled executable 检查 ACL 也被拒绝访问。证据指向当前 Windows 对该 bundled 浏览器可执行文件的访问限制，不是平台页面逻辑。
- 因此默认 Chromium 状态为 **BLOCKED**。没有修改 OS 权限或安全设置。使用 Edge fallback 完成真实 UI E2E，但这不把 bundled Chromium 或默认 Chromium 回归改记为 PASS。
- 后端全量测试中 6 个浏览器依赖用例均在 Chromium `spawn EPERM` 处失败，未到达应用断言。

## First-time User Test

独立 Reviewer 只收到任务：“这是一个 AI QA 平台。请选择一个已有需求，让 AI 帮你完成测试。”没有提供架构或操作说明。

- Reviewer 找到默认选中的 REQ-001，选择 TC-006，并启动了新测试；它能完成常规用例执行路径。
- 新 Run `run_8536b83fbf5e` 真实执行后失败，0/1 通过，耗时 24.74 秒；错误包含 `Page.screenshot: Timeout 3000ms exceeded`。
- Reviewer 进入失败恢复并点击“运行 AI 诊断”。约 20.6 秒后收到 `AI provider returned an empty stream`；没有修复提案、批准、重跑或验证。
- 它没有从自然语言入口启动 QA Agent，也没有看到计划或 Agent 创建的测试任务。首次使用目标 **FAIL**。Reviewer 全程 9 次有效点击；另有小视口下 2 次未命中诊断入口的尝试，见 Click Metrics。

## Confusion Points

- Workspace 的用例/运行路径可发现，但“直接告诉 QA Agent 要做什么”的入口藏在 Studio 助手里。
- 自然语言请求“帮我测试这个需求。”在 Studio 只产生了文本答复；没有创建任务、计划、Runtime 或 Run。
- 默认上下文先选中 TC-007；Reviewer 需要自行切到 TC-006 才能复现已有定位器失败。
- 第一次失败是截图超时；人工修复后新的 Run 在 `shop.product()` 点击商品详情按钮处失败。错误摘要与失败分类没有指出已确认根因，自动定位器修复也被禁用。
- Workflow 的长错误被省略号截断；1366×768 下事件流和 Workspace 下方内容需要滚动，但提示较弱。
- AI 诊断需要 20.6 秒后返回空流；另一次诊断在 37 分钟后仍保持 RUNNING。用户很难知道何时会完成、卡在哪里。

## Fixes

- Studio 的 Browser/Run 面板不再因新 Run 自动弹出；按需打开，并从旧 560px 侧抽屉改成最大 1360×940、随视口缩放的居中大面板。
- Failure 页面复用已有证据与概览组件（累计减少 387 net lines）；运行记录/浏览器历史页不会自行触发 AI 诊断，诊断由失败流程中的明确操作启动。
- 保留并验证既有修复：跨 Workspace、Studio、Workflow 的路由 context；异步 Recorder 会话关闭；Provider 结构化结果修复和流清理受同一请求 deadline 限制；Runtime 使用持久化事件与已有 SSE/polling。
- 本轮针对用户截图的布局问题扩展 Workspace 可用高度，并让无 DAG 时的 Workflow 事件区占用剩余高度；真实视口确认原有的大块空白消失，诊断主按钮完整可见。
- 最终 1920×1080、1440×900、1366×768 三档 Workspace、Studio、Workflow 截图均已生成并经独立复核。
- Studio 真实 Debugger 已验证：断点命中 `conftest.py:38` 并显示调用栈及局部变量；单步跳过后停在 `page:39`；继续进入运行态；手动暂停再次停住；停止后状态为“已结束”。
- 用 Studio 可见 UI 修正隔离副本中的 `tests/test_known_locator.py`，改用现有 `ShopPage.add()` 并保留购物车两条断言。新的 Retry Run 与原 Run 不同，但仍在商品详情点击处失败。该修复是人工应用 AI 文本建议，不是自动修复；不报告为 VERIFY。
- 未伪造 Provider fallback、PASS 结果或 Repair 提案；未增加产品功能或依赖。

## Click Metrics

没有可靠的整改前基线；按要求用当前体验作为 Baseline 1。独立 Reviewer 在最新 UI 调整后没有重新执行完整首次使用任务，因此 After 用户点击数为 **NOT TESTED**。

| Journey | Baseline 1 实测 | After | 结果 |
|---|---:|---:|---|
| Requirement → Run（从登录开始） | 5 次有效点击：登录、QA 工作台、测试用例阶段、选择 TC-006、立即运行 | 未由独立 Reviewer 重测 | Run 已真实创建，但自然语言 Agent 路径失败 |
| Failure → Diagnosis | Run 结果后的 4 次有效点击：总览、失败恢复、选择失败、运行 AI 诊断；小视口另有 2 次未命中尝试 | 未由独立 Reviewer 重测 | 诊断启动但 Provider 空流；Repair/Verify 未到达 |
| Failure → Verify | 4 次点击到诊断入口；后续阶段未发生 | 未测出有效闭环成本 | **FAIL**，不把失败分析当作验证 |

## Page Transition Metrics

- Reviewer 的 Requirement → Run：登录/总览 → Workspace（REQ-001）→ Cases → 选择 TC-006 → Run 结果；3 次 Workspace 内状态/上下文变化，Run 页面显示新 Run ID。
- Failure 诊断路径：Run 结果 → 总览 → 失败恢复列表 → 指定失败详情 → 诊断状态。诊断状态最后变为失败，不产生 Repair/Retry/Verify 状态。
- 修复后由开发验收通过可见链接完成 Workspace → Workflow → Workspace、Workspace → Studio → Workflow → Workspace，并刷新 Workflow。`projectId`、`requirementId`、`testDesignId`、`caseId`、`runId`、`failureId` 保持；Studio 还保留文件路径。三个 Surface 对同一 Run 均显示 FAILED。

## AI Provider Measurements

| 能力 | Provider / Model | 总耗时 | 真实结果 | Fallback / TTFT |
|---|---|---:|---|---|
| Requirement Analysis task `baebcf17e0944b4f9c064ad29f7c8d5f` | openai-compatible / space-bunny-free | 130.09 秒 | 三次 Provider 重试后 RuntimeError，任务 BLOCKED | 未 fallback；TTFT 未记录 |
| Requirement Analysis task `4eb83a0a5b604b55b2363cceccbabe11` | openai-compatible / space-bunny-free | 44.97 秒 | 45 秒超时，任务 BLOCKED | 未 fallback；TTFT 未记录 |
| Requirement Analysis task `4bec9f7e46ad41aa89e1c5e0abc85b80` | openai-compatible / space-bunny-free | 39.44 秒 | 空流，任务 BLOCKED | 未 fallback；TTFT 未记录 |
| Studio 自然语言“帮我测试这个需求。” | openai-compatible / space-bunny-free | 24.25 秒 | 返回非空文本；未创建 task/plan/run | 未 fallback；TTFT 未记录 |
| Failure Diagnosis `fail_1235de5c17a8` | openai-compatible / space-bunny-free | 20.6 秒 | 空流，分析 FAILED | 未 fallback；TTFT 未记录 |
| Code Review | openai-compatible / space-bunny-free | 32.5 秒 | `provider_unavailable`，没有 Review 结果 | 未 fallback；TTFT 未记录 |
| Retry Failure Diagnosis `fail_188160238bd2` | openai-compatible / space-bunny-free | 至 11:23 已运行约 37 分钟 | analysis `6f41d3d3-1690-499a-9d15-68ce03ee94c8` 仍为 RUNNING、无结束时间 | 未 fallback；TTFT 未记录 |

**Real AI：FAIL。** 一次助手文本回复成功不代表测试工作成功。小型连通性探测未计入产品成功率。

## Golden Journey

**FAIL。** 实际路径没有越过自然语言任务启动/计划阶段，也没有完成 Repair → Verify：

1. Reviewer 选 REQ-001 / TC-006，创建真实 Run `run_8536b83fbf5e`；Run 失败，`fail_1235de5c17a8`。
2. 真正 UI 输入“帮我测试这个需求。”后，Assistant 在 24.25 秒后只返回文字；没有 Task ID、计划、测试创建或 Run。
3. Reviewer 的失败诊断空流。开发验收随后在隔离副本中人工应用文本建议并保留两条断言。
4. 第一次不完整替换产生探索性失败 Run `run_10d2657e6106`；随后通过 Studio 修正并保存，再点击 Retry，创建不同的 `run_e4ff848d6148`。
5. Retry 在 `pages/shop.py:17` 的 “View Everyday Tee” 点击处超时，0/1 通过；分类与摘要没有确认根因。对 `fail_188160238bd2` 启动的诊断一直 RUNNING，没有 Repair Proposal、Approval 或 Verify。

## IDs

- Project：`proj_golden_shop_v1`
- Requirement：`req_golden_shop_v1`（REQ-001）
- Test Design：`des_golden_006`
- Case：`case_golden_006`（TC-006）
- 自然语言 Agent Task：**NONE**（未创建）
- Requirement Analysis Tasks：`baebcf17e0944b4f9c064ad29f7c8d5f`、`4eb83a0a5b604b55b2363cceccbabe11`、`4bec9f7e46ad41aa89e1c5e0abc85b80`
- Original Run / Failure：`run_8536b83fbf5e` / `fail_1235de5c17a8`
- Retry Run / Failure：`run_e4ff848d6148` / `fail_188160238bd2`
- Exploratory invalid edit Run：`run_10d2657e6106` / `fail_fa655e9f941e`
- Stuck retry diagnosis：`6f41d3d3-1690-499a-9d15-68ce03ee94c8`（RUNNING）

## Screenshots

九张最终截图共用 Retry Run `run_e4ff848d6148`，分别覆盖三种视口与三个 Surface：

| Viewport | Workspace | Studio | Workflow |
|---|---|---|---|
| 1920×1080 | [截图](../output/agent-experience-closeout-20261004/final-workspace-1920x1080.png) | [截图](../output/agent-experience-closeout-20261004/final-studio-1920x1080.png) | [截图](../output/agent-experience-closeout-20261004/final-workflow-1920x1080.png) |
| 1440×900 | [截图](../output/agent-experience-closeout-20261004/final-workspace-1440x900.png) | [截图](../output/agent-experience-closeout-20261004/final-studio-1440x900.png) | [截图](../output/agent-experience-closeout-20261004/final-workflow-1440x900.png) |
| 1366×768 | [截图](../output/agent-experience-closeout-20261004/final-workspace-1366x768.png) | [截图](../output/agent-experience-closeout-20261004/final-studio-1366x768.png) | [截图](../output/agent-experience-closeout-20261004/final-workflow-1366x768.png) |

Debugger 证据：`36-debug-breakpoint-set.png`、`37-debug-first-stop.png`、`38-debug-step-over.png`、`39-debug-manual-pause.png`、`40-debug-stop.png`。首次使用者与失败恢复截图位于 `reviewer/` 子目录；AI 请求、人工修复、Retry 和诊断截图为 20–35 序列。

最终截图独立复核：**0 Critical、0 High、5 Medium、2 Low**。最终九图直接发现 3 Medium（小视口事件不易滚动发现、长日志截断且偏浅、1366 Workspace 下方内容不易发现）和 1 Low（1366 Studio 工具按钮紧）。助手截图另有 2 Medium（等待状态不够明显、侧栏挤窄编辑器）与 1 Low（“部分能力受限：常规 AI”提示太泛）。没有异常大块空白。

## Regression

- Backend full suite（最终后端改动之后）：**429 passed / 6 failed / 4 skipped**，687.55 秒。6 个失败都在 Chromium `spawn EPERM`，应用断言没有执行。
- Focused streaming/API regression：**16 passed**，14.89 秒。
- Frontend tests：**78 passed / 0 failed**。
- Typecheck：**PASS**。
- ESLint：**PASS**。此前的完整 Ruff check/format 也通过；本轮只有 CSS/文档调整，没有 Python 源码调整。
- Production build：**PASS**，3,375 modules，50.29 秒。Monaco 主分块约 4.03 MB raw / 1.04 MB gzip，保留既有 chunk-size warning。
- Browser E2E：**FAIL/BLOCKED**。真实 Edge UI 流程被执行，但 Run 与 Retry 都真实失败；六个默认 Chromium 用例没有到达应用断言。

## Blocked Items

- bundled Chromium 的可执行权限由当前 Windows 环境拒绝；默认 Chromium 自动化仍 BLOCKED。
- Provider 的真实 Requirement Analysis、Diagnosis、Code Review 不稳定或不可用；没有可靠的无 fallback 结果。
- 最新失败诊断记录仍卡在 RUNNING，未产生结束事件、提案或验证结果。
- 浏览器测试全量回归中的 6 项无法验证产品断言。

## Remaining Debt

- Natural language 到现有 QA 任务/计划/运行能力没有闭环；这是 Overall FAIL 的直接原因。
- 失败分类把本次商品详情点击超时标成通用超时/定位器变化，但证据没有确认根因；不应生成或宣称成功的定位器修复。
- Retry 没有通过；当前只能确认新 Run ID 和新的失败，不能标记 VERIFY。
- 五项 Medium、两项 Low 的视觉易用性问题仍在；整改后没有由独立首次使用者重测点击数。
- Git 工作区本身带有大量继承 dirty data。未删除 `.tmp-test-validation` 或 `apps/api/runtime` 内的 DB、工作区和运行制品。一个 360 项的 pytest 临时目录递归删除被自动审查拒绝，因为无法仅凭名称证明其中所有内容都可丢弃；没有绕过该拦截。

## Git Status

- `git status --short`：**87 tracked modified、33 compact untracked entries、120 rows**。
- 展开 untracked path：**2,053**（包括测试缓存、runtime/工件、报告和截图）；其中 `apps/api/app`、`apps/web/src`、`packages` 下有 **21 个未跟踪产品源码文件 / 3,777 LOC**。这些是相对 HEAD 的累计工作区状态，无法全归因给本轮。
- 当前 HEAD 对 tracked 文件 diff：**+4,018 / −1,743 LOC**。本轮 closeout 没有新增产品源码文件；具体单轮行数无法从未提交的任务开始快照精确分离。
- 本轮删除 11 个明确由本轮创建的探测脚本。保留验收截图、隔离运行 DB/制品和来源不明的旧临时目录；未清理 `apps/api/runtime`。

## Ponytail Impact

- Reused existing components：Workspace、Studio、Runtime、Failure、Workflow、RuntimeEventStream、既有路由和 context serializer。
- Reused existing backend services：task runtime、Requirement Lifecycle、Failure workflow、Test Run、event persistence/SSE、provider registry、browser controller。
- Removed duplicate implementations：继承的 Rebuild 已移除自动弹 Run Drawer 的 effect，并将 Failure 页面减少 387 net lines；本轮没有增加平行实现。
- New files added：本轮产品源码 0 个；工作区相对 HEAD 的 21 个未跟踪产品源码文件来自累积 dirty state。
- New dependencies added：0。
- New abstractions added：本轮 0 个。累积 rebuild 中的 4 个共享 contract/helper（workspace context、failure workspace model、trace summary model、runtime source opener）已有多个调用方，用于跨页面统一 context、failure state、事件展示和类型化源码导航；本轮没有新增包装层。
- LOC added / removed：本轮源码行数无法与未提交起点精确分离；当前累计 diff 为 tracked +4,018 / −1,743，另有未跟踪产品源码 3,777 LOC。布局收尾只改现有 CSS。
- Why each new abstraction was unavoidable：本轮无新抽象；上述累积共享 helper 因多个页面共用同一行为而保留，没有新建 service/adapter/runtime/event/SSE/provider。

## Final Conclusion

First-time User、QA Agent Discoverability、Natural Language Agent、Agent Plan、Agent Running、Agent Result、Workspace、Studio、Failure → Repair → Retry → Verify、Golden Journey 和 Real AI 均未通过。Workflow 的运行状态和事件证据、跨 Surface Context、同一 Run 的状态一致性、Debugger 控制，以及前端自动化检查通过；这些通过项不足以满足最终验收门槛。

**现在我是否可以把电脑交给一个第一次使用的 QA Engineer，不给说明书，让他通过 QA Agent 完成一次真实测试工作？ NO。**
