# AI QA Platform V3 验收记录

日期：2026-10-03（Asia/Shanghai）
工作区：`D:\code\self-github\ai-qa-platform`
总体：**PARTIAL**。产品骨架、真实 Runtime 投影、路由上下文、主要前端检查及全量后端套件通过；真实 AI 生成、完整 Failure 写操作、Recorder 保存、调试断点和实时 RUNNING Workflow 本轮未完整演练。未用 Fake 数据代替这些场景。

## 1. Overall

**PARTIAL**。统一 Workspace/Workflow/Studio 结构落地，代码与 UI 独立 Review 的 High/Medium 问题已修。后端全量测试 429 passed、4 skipped；前端 78 passed；Typecheck、前端 ESLint、Ruff check、i18n、production build 通过。全仓 Ruff format check 有 13 个文件不符合格式，未批量格式化以避免改写原有 V2 工作区差异。写操作型 AI、修复、重跑、Recorder 保存及性能压测未完整验收。

## 2. Unified Workspace

**PASS（骨架与导航）；完整业务验收 PARTIAL**。`/workspace/:projectId` 已内嵌需求、用例、Failure 子流程，并以 URL Context 保持 project/requirement/design/case/binding/task/run/failure/browser/file/line/node/step/stage/returnTo。Requirement、Cases、Automation、Result、Failure 阶段在同一 Workspace 路由切换。真实数据浏览覆盖 1 个项目、1 个需求、7 个用例、3 个 Run、6 个 Failure。没有调用 AI 分析或生成。

## 3. Live Workflow

**PARTIAL**。`/workflow` 带 task/run ID 时复用现有 `RuntimeDetail` 与真实 Runtime Projection；无 ID 时显示既有任务列表。真实观察到 1 个 FAILED Run 和 2 个 BLOCKED Task；没有 RUNNING Task/Run。没有为截图创建假执行状态。

## 4. Automation Studio

**PARTIAL**。保留真实 Monaco、文件树、Browser 预览、Recorder、TestRun、debugpy 与 AI Assistant；Studio 页面和 Recorder 模式可打开。真实 Debugger 启动了 Golden Demo 的 debugpy 会话，接受 `tests/test_known_locator.py::test_known_locator_change` 并显示 RUNNING；离开 Studio 时触发卸载清理请求。会话终止结果没有独立 API 状态可读，本轮未验证 DAP 结束确认。没有编辑/保存源代码，也没有执行 AI Review、目标重跑。

## 5. Requirement → Run

产品内路径为：Workspace 选择 Requirement → 既有 Analysis/Test Design → Cases → Automation → Run/Result。前四个阶段在同一 Workspace 页面，不需路由跳转；实际浏览覆盖需求与用例阶段、URL 刷新恢复。**未实际触发 AI Analyze、Generate Automation 或新增 Run**，因此不把本场景报告为端到端 PASS。

## 6. Failure → Verify

Workspace Failure 阶段直接呈现已有 `LOCATOR_CHANGED` Failure、来源 Run、摘要、诊断状态与诊断/修复/重跑/验证链。Failure→Studio 深链已用真实 failure/nodeid 启动 debugpy。**未点击诊断、应用修复、Retry 或 Verify**，避免更改 Golden Demo 的故障和运行历史；该写操作场景为 PARTIAL。

## 7. Workspace → Workflow

**PASS**。Workspace 的 Workflow 入口可打开统一观察路由；运行上下文构造器保留 project/case/run/failure。Workspace 需求/用例/阶段在刷新后保持。真实页面按钮进入/返回在本机浏览器中走查通过；完整跨界字段断言另由 `workspaceContext` 单测验证。

## 8. Workflow → Studio

**PARTIAL**。Runtime 节点的源码打开回调构造 Studio 深链，传递 file/line/case/failure/run/task；构造器有前端单测。实际页面按钮走查因本机 API 随后的登录请求超时而未完成。Studio 的同一条深链已由真实 Failure 调试场景加载，不把未点击的 Workflow 按钮冒称端到端通过。

## 9. Studio → Workflow

**PARTIAL**。Studio 提供 Workflow 入口，并使用共享 Context 构造目标地址；链接构造有单测。Studio 页面已真实打开，但本机 API 登录请求超时后，第二轮按钮往返无法完成，故没有报告为实测 PASS。

## 10. Runtime Unification

**PARTIAL**。Workflow/Studio/Workspace 共享后端 Runtime Projection；Run 状态通过相同 `useRunStore`/Run ID 归并，Task/Run 完整快照通过 Runtime Hook。Workspace 与 Studio 是精简呈现，Workflow 是完整观察视图。多种独立业务 Runtime 入口仍保留兼容，并非所有 AI/需求 SSE 被改写为 Runtime SSE。

| 可核验口径 | V2 基线 | V3 当前 |
|---|---:|---:|
| Runtime Projection 数据源 | 1 | 1 |
| RuntimeDetail 实现 | 1 | 1 |
| 同一 Run 的重复 Store/SSE 订阅 | 0（同 Run 消费者共享 Run Store） | 0 |
| Runtime SSE 传输助手 | 1 个 `openEventStream`；Task 与 Run 各自一类订阅 | 1 个 `openEventStream`；Task 与 Run 各自一类订阅 |
| Runtime UI 表面 | Runs/Studio/业务 Context 多处复用 | Workspace Mini、Workflow Detail、Studio Mini 共 3 种呈现 |

这些基线来自 `docs/platform-v2-architecture.md` 与当前共享 Hook/Projection 的调用图。此处“重复”按重复数据源/同一 Run 并行订阅计算，不把不同实体的 Task、Run 流误计为重复。

## 11. Intelligence Unification

**PARTIAL**。Intelligence 作为 Workspace、Failure、Studio、Runtime 上的能力呈现，不增加 AI 一级导航或假 Agent；仍复用现有 Provider、lifecycle、test automation、Failure Intelligence 接口。本轮没有真实 Provider 凭据，未执行语义生成。

本轮按 6 个目标域盘点：Requirement、Test、Automation、Locator、Failure、Verification Intelligence；Provider Registry 为 1 个共享入口。V3 主要统一入口、Context 和 Runtime 呈现，没有把 6 个不同领域操作改成 1 个 AI flow。由于输入/输出合同不同，无法给出“重复 AI flow 数”的可靠 Before/After 数字；现有重复风险列入架构债务，不伪报为已归零。

## 12. JEV Integration

现有 JEV 仍是候选决策层，Runtime 可呈现实际记录的 Decision/trace；无必要的流程不强制调用 JEV。qa-core JEV、Locator/Failure 决策测试包含在全量后端套件中。本轮未制造 JEV 事件，也未用假事件证明集成。

## 13. Browser / Recorder

真实 Studio 的 Golden Demo Browser 预览与 Recorder 页面已打开并截图；Recorder 没有启动录制会话、生成代码或保存为 Case。运行期 Browser 会话和帧仍按原 Runtime Projection/Run Store 关联。本轮 Recorder 场景为 PARTIAL。

## 14. Debugger

debugpy/DAP 会话真实接受 Failure 深链的 pytest nodeid，Studio 自动定位 `tests/test_known_locator.py`，面板显示运行中与真实调试输出；离开 Studio 后 hook 发出 close 清理请求，但本轮未取得会话终止确认。未设断点，因此没有验收 paused、Call Stack、Variables、Continue/Step Over/Step Into/Step Out/Pause；Debugger 页面能力的后端回归由全量套件覆盖。

## 15. AI Coding

保留 Studio 当前文件、Case、Failure 上下文及已有 AI Assistant/Review/Fix 能力；没有可用 Provider 时不输出或声称完成 AI 改码。本轮未调用真实模型、未生成或应用补丁。`packages/qa-core/qa_core/ai/provider.py` 另有一行既有 retry 提示文案对齐 provider 回归断言；该文件开始任务前已存在用户改动。

## 16. Before / After Navigation Count

计数口径为完成产品步骤所跨越的 route 数，不把 tab/modal 算成页面跳转：

| Journey | V2 路由路径 | V3 路径 |
|---|---:|---:|
| Requirement → Run/Result | Requirements → Test Cases → Runs：2 次；若需进 Studio 写代码则 3 次 | Workspace 阶段内 0 次；查看完整执行可选 Workflow +1，写代码可选 Studio +1 |
| Failure → Verify | Failure → Studio → Retry Run → Failure：最多 3 次 | locator 修复/验证在 Workspace 内 0 次；代码修复往返 Studio 为 2 次 |

这是路由结构的前后计数，不代表本轮已执行相应写操作。

## 17. Context Loss Before / After

改造前审计发现 project localStorage、requirement/case session storage 和分散 query 参数共 **3 类上下文载体**，跨到 Studio、Run、Failure 时容易漏传下游 ID。改造后统一由 16 个类型化 Context 字段在 URL 传递；Workspace 刷新实测 requirement/design/case/stage 无丢失；Workspace/Workflow/Studio 链接构造和旧参数别名由 3 项 `workspace-context` 单测覆盖。已测样本观察到丢失 **0 次**；未完成的 Studio/Workflow 页面按钮往返不计入实测样本。

## 18. Backend Tests

`uv run pytest --basetemp=C:/Users/admin/.codex/visualizations/2026/10/03/01a100fd-576a-7de2-a25e-792bde99a9e4/pytest-v3-full-elevated -p no:cacheprovider`：**429 passed、4 skipped、0 failed，44 warnings，583.20s**。4 项 PostgreSQL 集成测试因未配置数据库而 skip；warning 主要是 pytest 将带 `__init__` 的模型/服务类识别为不可收集，以及测试夹具中的 `SyntaxWarning`。Chromium 进程在普通沙箱曾返回 `spawn EPERM`，单项浏览器测试在受控提权后通过，全量套件随后也在受控执行环境通过。

## 19. Frontend Tests

`pnpm --filter @ai-qa/web test`：**78 passed、0 failed**，包括新增 Workspace Context 与既有 Runtime DAG/SSE/Failure 状态模型测试。

## 20. Typecheck

`pnpm --filter @ai-qa/web typecheck`：**PASS**（`tsc --noEmit`）。

## 21. Lint

前端 `pnpm --filter @ai-qa/web lint`：**PASS**。`uv run ruff check .`：**PASS**。i18n parity：**PASS，24 namespaces / 2 languages / 1965 keys**。全仓 `uv run ruff format --check .`：**PARTIAL/FAIL，13 files would be reformatted，316 files already formatted**。涉及的格式化差异横跨任务开始前已存在的 V2 用户修改及未改文件；未做全仓格式化以避免大面积改写用户差异。`git diff --check` 没有 whitespace error（仅 Git 的 LF/CRLF 提示）。

## 22. Production Build

`pnpm --filter @ai-qa/web build`：**PASS**。Workspace chunk 21.14 KB、Workflow chunk 7.77 KB；仍有既有 Monaco Editor chunk **4,031.71 KB（gzip 1,043.98 KB）** 超过 Vite 500 KB 阈值的 warning。

## 23. E2E

- Workspace：真实项目数据加载；Requirement/Cases/Automation/Result/Failure 阶段；刷新保留 URL Context。导航与上下文走查 PASS，AI Analyze/Generate/Run 写路径 PARTIAL。
- Failure：真实 Failure 详情与 repair/verification 状态链显示 PASS；诊断、Apply、Retry、Verify 按钮未操作，故写路径 PARTIAL。
- Studio/Debugger：真实 Studio/Recorder 页面加载；真实 debugpy Failure node 启动成功，显示 RUNNING；编辑/保存/测试重跑、DAP 断点与 step 操作未执行。
- Workflow：真实 FAILED Run、BLOCKED Task 详情加载；数据库当时没有 RUNNING Task/Run，故无 Workflow Running 样本。已测 Legacy `/automation → /library`、`/tasks → /workflow`（保留 project query）、`/runs/tasks` 兼容路由。
- 页面错误：首次路由走查记录 0 个 pageerror。后续本机 `/api/auth/login` 请求超时，导致剩余 Workflow↔Studio 按钮往返未能完成；API `/api/health` 仍返回 200。未重启用户服务。

## 24. Performance

**PARTIAL**。前端单测验证 500 个事件有界窗口、10 分钟活动跨度布局和事件去重；Workspace 在 **1920×1080、1440×1000、1366×768** 三种尺寸完成浏览器查看，其中 1920 和 1366 视口实测页面宽度无横向溢出（1440 有截图及 Failure 布局尺寸测量）。本轮没有执行 30 nodes/100 edges 的生产规模 DAG、10 分钟浏览器/内存/SSE 压测；Monaco 4.03 MB chunk 是首要加载债务。

## 25. Code Review

独立静态 Code Review 无 Critical。发现 3 个 High、1 个 Medium：Failure→Studio 未传父 Run ID；Studio 新 Run 仍携带旧 Task ID；Workspace 在当前 Requirement 无关联 Case 时误选其他 Case；生成 Case 未传 TestDesign ID。均已修复并纳入相关测试。Reviewer 未改代码。

## 26. UI/UX Review

独立静态 UI/UX Review 无 Critical/High，5 个 Medium 均已处理：Workspace/Library 加载错误与重试、Run/Failure “最多加载 8 条”的真实限制提示、普通 Workspace→Studio 返回 Workspace、Workflow 样式、MiniBar 空闲时重复下一步文案。之后真实浏览器截图发现 Workspace 嵌入 Failure 页时全局 grid 样式把内容压至约 250px；已添加 workspace-mode 单列布局并重拍。修复后 1440px Failure 内容宽 **848px**、标题宽 **323px**。独立 Review 本身未做视觉浏览器观察，视口检查由本轮实测补充。

## 27. Regression

后端完整测试 429/4；前端 78；Typecheck/ESLint/Ruff/i18n/Build 均如上。真实读取检查覆盖 Project、Requirement、TestCase、Run、Failure、Runtime Task、Studio、Recorder、Legacy routes。未做用例重写、AI 修复、Recorder Case 保存和 Run retry 的数据写回回归。测试生成的 `apps/api/runtime/` 和已有项目的其他未跟踪内容均保留，未清理。

## 28. Screenshots

PNG 截图与 Playwright 走查 JSON 保存在 `output/platform-v3-acceptance/e2e/`：

- Workspace：[`workspace.png`](../output/platform-v3-acceptance/e2e/workspace.png)、[`workspace-cases.png`](../output/platform-v3-acceptance/e2e/workspace-cases.png)、[`workspace-automation.png`](../output/platform-v3-acceptance/e2e/workspace-automation.png)、[`workspace-result.png`](../output/platform-v3-acceptance/e2e/workspace-result.png)
- Workflow Running：**无现存 RUNNING 记录，未制作假截图**。
- Workflow Failed：[`workflow-run-failed.png`](../output/platform-v3-acceptance/e2e/workflow-run-failed.png)；另有 [`workflow-blocked.png`](../output/platform-v3-acceptance/e2e/workflow-blocked.png)
- Studio：[`studio.png`](../output/platform-v3-acceptance/e2e/studio.png)
- Debugger：[`debugger.png`](../output/platform-v3-acceptance/e2e/debugger.png)，真实 debugpy 运行中，随后关闭。
- Recorder：[`recorder.png`](../output/platform-v3-acceptance/e2e/recorder.png)，未启动/保存录制。
- Failure Repair / Verification：[`failure-repair-verification.png`](../output/platform-v3-acceptance/e2e/failure-repair-verification.png)，展示真实 Repair/Verify 链状态，尚未执行写操作。
- 视口：[`workspace-1920x1080.png`](../output/platform-v3-acceptance/e2e/workspace-1920x1080.png)、[`workspace-1366x768.png`](../output/platform-v3-acceptance/e2e/workspace-1366x768.png)；Library：[`library.png`](../output/platform-v3-acceptance/e2e/library.png)。
- 结构化路由和视口记录：[`browser-smoke-report.json`](../output/platform-v3-acceptance/e2e/browser-smoke-report.json)。

## 29. Remaining Architecture Debt

- AI、Requirement Lifecycle、Case Automation、Failure、Recorder 保持各自领域 API/SSE；共享 Context/Runtime 观察不代表所有 Intelligence 已收敛到一个服务。
- Task、Run 继续是不同对象；只有存在真实 TaskStep 时才绘制 Task DAG。无 Task/Run 时 Workflow 显示任务列表，不自动拼接 Requirement 全流程图。
- Studio 现有 Monaco chunk 约 4 MB；需要后续按语言 worker/编辑器能力拆包和首屏加载测量。
- Workspace 当前 Runs/Failures 面板只取最近最多 8 条；数量不是后端全量计数。

## 30. Remaining UX Debt

- 需要在隔离验收数据上完成 Analyze→Generate→Run→Pass 和 Failure→Diagnose→Repair→Retry→Verify 的完整写路径。
- Workflow Running、审批等待、真实 retry/并行路径未在本机数据中出现；不能从历史 FAILED/BLOCKED 数据验证动画状态切换。
- Recorder 当前只验收入口与 UI；Locator Intelligence 到项目原生 Page Object/Fixture 的真实保存路径需单独验收。
- DAP 当前没设置断点；Call Stack、Variables 和 stepping 还需一次受控暂停场景。
- 本机 API login 在后续浏览器尝试中超时，限制了最后一轮 Studio↔Workflow 按钮实测；需服务恢复后重放。

## 31. Deferred V4

1. 在隔离数据库和一次性项目中完成全写操作的五个 Demo Journey，并在测试后清理隔离数据。
2. 增加真实 RUNNING/approval Task、运行中的 Run 与 retry/verify 的稳定 E2E fixture。
3. 有界压力：30 节点/100 连线、500 事件、50 用例、10 分钟浏览器/SSE/内存测量。
4. Monaco Editor/worker 分块、压缩与首屏 bundle 预算。
5. 配置可用 Provider/JEV 后实测真实 Analyze、生成、Locator/Failure Intelligence 与 AI Coding diff。
6. Recorder 保存项目原生 Case/Fixture，以及 Debugger 断点暂停、Step、Variables/Console 端到端验证。

## 32. Acceptance Report

本报告：[`docs/platform-v3-acceptance.md`](platform-v3-acceptance.md)。产品架构：[`docs/platform-v3-product-architecture.md`](platform-v3-product-architecture.md)。

## 33. Git Status

没有创建 commit。仓库在任务开始前已有大量 V2 未提交修改；本轮保留这些差异，未执行 reset/clean。V3 源码、两个文档、截图报告以及后端测试生成的 runtime 内容仍是工作树改动/未跟踪文件；`apps/api/runtime/` 按项目说明属于运行数据，不应提交。最终状态含 63 个已跟踪修改路径（其中包括起始 V2 工作）和多个未跟踪目录，不能把这些都解释为本轮新增。

## 34. Final Conclusion

Workspace、Workflow、Studio 已共享真实项目上下文和 Runtime 数据并显著减少日常跳转；核心结构与自动化检查通过，但外部 AI、Recorder 写入、Failure 修复验证、实时运行及压力场景仍待隔离数据下验收，因此总体为 **PARTIAL**。
