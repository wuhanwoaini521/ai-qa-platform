# Autonomous QA Agent V1 验收

日期：2026-10-04
结论：**PARTIAL**

## 验收摘要

Agent V1 复用了现有 Task Runtime、TaskStep、AI Provider、JEV、Browser、Pytest/TestRun、Approval、SSE、Workspace、Studio 和 Workflow。目标解析、动态计划、暂停恢复、失败分支、审批及结果摘要有真实代码和测试覆盖。

端到端黄金旅程没有通过：独立首次用户实际运行因 `fake_provider_selected` 在 0.258 秒后受阻，AI 调用为 0；不能将模拟 Provider 当作真实模型结果。浏览器型 `CREATE_TEST` 审批旅程单独执行通过；全量回归中的 Chromium 子进程启动和页面探索仍受 `spawn EPERM`、负载敏感性影响，所以 Browser 不判完整通过。

## 能力验收

| 能力 | 结果 | 证据与边界 |
|---|---|---|
| Goal Understanding | PASS | 中英文正向/否定范围解析用例通过；`Do not run any tests` 与 `Do not fully test this existing requirement` 已覆盖。 |
| Dynamic Planning | PASS | 使用真实 Context 组装 TaskStep；计划 DAG 的唯一键、依赖和条件分支有测试。未知依赖及故障分支重复 key 已修复。 |
| Continuous Execution | PARTIAL | 长任务自动执行通过；首次真实需求旅程被 Provider 配置阻断。 |
| Context Awareness | PASS | 需求、项目、Workspace、Automation 绑定及计划 token 进入任务计划；盲测成功找到并保留已有需求上下文。 |
| Risk Control | PASS | 源码 Apply 仍需持久审批；浏览器只执行观察到且通过安全分类的候选。 |
| Approval | PASS | Create Test 的生成草案审批、批准后续跑及注册在单测中一次完整通过；该测试在全模块负载下的前置 Browser click 有失败记录。 |
| Resume | PASS | 持久化暂停/恢复、刷新后读取当前工作区并失效旧草案有回归覆盖；长任务刷新后暂停并恢复同一 Run。 |
| Replanning | PASS | 重编译当前事实、只重跑允许步骤、保留已完成步骤和 active execution budget 有回归覆盖。 |
| Recovery | PARTIAL | 失败后可进入诊断、重试/重规划；真实 Provider 不可用时按阻塞终止，不能完成 AI 恢复链。 |
| Human Takeover | PARTIAL | Studio 深链和现有文件可打开；暂停后重读工作区逻辑有测试。未完成“用户在 Studio 改代码后由同一真实 Goal 自动 Validate → Retry → Verify”的完整实测。 |
| Result Summary | PASS | 结果契约含状态、测试、Run、Findings、Unresolved、AI 使用量；目标测试通过但回归失败现会判为未验证。 |
| Traceability | PASS | Task、Step、Run、Artifact、Evidence 以持久 ID 关联；Workflow 查看长任务事件及结果。 |
| First-time User | FAIL | 首页就绪到开始任务 5 分 22 秒；任务 0.258 秒后因 Fake AI 阻塞，0/24 步、0 AI 调用、没有 Run/审批/源码写入。见 `output/autonomous-qa-agent-v1/first-time-user-postfix.md`。 |
| Dogfooding | PARTIAL | 完成 3 条平台旅程；Studio 只验证打开真实项目文件，未完成 Studio Run/Debug 的端到端闭环。 |
| Golden Journey | FAIL | 未到达 Cases、Automation、Source Approval、Apply、Retry、Verify；没有真实 Provider，不能判 PASS。 |

## Golden Journey 与首次使用指标

| 指标 | 实际结果 |
|---|---|
| 用户目标 | `使用 QA Agent 测试一个已有需求。` |
| Time to discover Agent | 未单独计时 |
| Time to First Useful Action | 5 分 22 秒（用“首页就绪 → 开始 Goal”作代理指标；没有单独埋点） |
| 首页就绪 → Start | 5 分 22 秒 |
| 点击数 | 登录后记录到 6 次关键导航/目标操作；不含登录表单和文本输入 |
| 页面流转 | 5 次：总览 → 默认项目 Workspace → 项目列表 → 需求 → 需求 Workspace → 任务结果 |
| Wrong turns / Questions | 1 次可恢复绕行：默认项目没有需求，需进入项目列表选已有项目；0 个用户提问，0 个不可恢复死路 |
| Start 后人工介入 | 0 次；任务立即阻塞，未出现审批决定 |
| Start 后耗时 | 0.258 秒至 `BLOCKED` |
| Goal completion time | 未完成；0.258 秒时被 Provider 阻塞 |
| Approval count | 0；目标在审批前阻塞 |
| 最终状态 | `BLOCKED`，0/24 步完成、1 步失败 |
| Provider / Model | `fake` / `gpt-4o-mini` 为配置标签；实际 AI 调用 0，不能视为真实模型 |
| JEV 调用 | 0；环境中未启用 |
| 本次 TestRun | 0 |

## Dogfooding

| Journey | 结果 | 观察 |
|---|---|---|
| Workspace → 已有 Requirement → Agent | BLOCKED | 找到 `Workspace goal continuity` 与关联 Case；计划显示 24 步，但 Fake AI 阻止第一步。 |
| Studio → 打开测试文件 | PARTIAL | 浏览器成功载入平台 Dogfood 项目及真实测试源码；未跑该文件、未打开 Debugger，也未返回同一 Goal 继续执行。截图 `13-studio-current.png`。 |
| Workflow → 长任务 → Inspector → Refresh/Pause/Resume | PASS | 一个目标运行约 9 分 36 秒，目标 TestRun 303.321 秒、1/1 通过；刷新后可暂停/恢复，Run ID `run_d59dba70e9c2` 未重复。 |

### 发现并修复

- RUNTIME BUG：失败子图把字符串依赖拆成字符，并与自动化分支重复使用 `approval`/`validate` key。现在依赖是 tuple，失败/修复步骤有独立前缀。
- RUNTIME BUG：前缀步骤输出未映射回已有工具处理器使用的 canonical key。已补兼容别名并加入测试。
- RESULT BUG：最终验证遗漏修复后的 regression Run，目标 Run 通过时可能误报成功。现在 target 与 regression 均需通过，摘要纳入 regression。
- GOAL SCOPE：英文“不运行任何测试”和“不要完整测试已有需求”曾触发错误范围。已补否定解析与回归测试。
- RUNTIME RACE：ApprovalRequired 处理曾可能把并发取消改回等待审批；现对 Task 状态、当前步骤和 RUNNING TaskStep 做同事务条件更新。
- RUNTIME RACE：并发 Replan 曾可重复重置步骤；现先对 owner、BLOCKED/FAILED 状态与 replan budget 做 CAS 认领，再改步骤。
- BRANCH OUTPUT：跳过的 repair regression 曾可进入 Verify；repair 审批也可能优先读到此前生成提案。现只为已完成步骤生成别名，repair 审批优先使用当前 repair proposal。
- AGENT UX：新空 Workspace 增加可见的“选择一个已有项目”出口；完成结果显示“新建目标”，不再混淆输入区。当前截图经独立视觉复核。
- TEST FIX：`test_recorder_uses_jev_choice_and_verifies_it_with_playwright` 的 Locator stub 缺少真实点击校验所需的 `evaluate()`；补齐 stub 后隔离复测 1/1 通过。未改生产逻辑。
- BROWSER STABILITY：全量回归中的 Browser 相关失败包含 3 个 `spawn EPERM`、Agent 页面探索未满足验证条件、以及负载下的 locator click 稳定性。页面探索隔离复测通过，但不抵消全量失败；仍记为未解决，不计 Browser 回归通过。

## 回归与构建

| 项目 | 结果 |
|---|---|
| Backend full suite | 最终修复后 464 passed / 4 failed / 4 skipped，846.96 秒（14 分 6.96 秒）；失败：`test_jev_verification_failure_keeps_attempt_and_explicit_local_fallback`、`test_short_navigation_captures_actual_page_before_browser_close`、`test_real_browser_created_inside_test_and_fixture_both_emit_frames_and_evidence`、`test_network_body_is_bounded_redacted_and_has_real_duration`。4 项隔离复跑均在 Chromium `launch()` 处以 `spawn EPERM` 失败，确认是当前 Windows 执行环境不能启动浏览器。 |
| V1 并发/审批/repair 回归 | 10 passed，24.36 秒；覆盖取消与审批竞态、并发 Replan、repair 输出别名与 proposal 选择。 |
| Agent Task module | 早期全模块运行 56 passed / 1 failed（361.44 秒）；后续全量回归中的探索 E2E 在负载下失败，隔离复测 1 passed（63.86 秒）。点击用例隔离复测 1 passed（108.82 秒），不抵消全量负载失败 |
| Browser approval E2E | 单独运行 1 passed，108.82 秒；它只证明 Create Test 草案审批链，不证明真实 AI Goal |
| Browser exploration E2E | 前一轮全量回归曾在负载下失败，隔离复测 1 passed（63.86 秒）；最终全量回归通过。当前其余 4 项 Browser 失败均在 Chromium 启动时遇到 `spawn EPERM` |
| Frontend tests | 78 passed |
| Typecheck | PASS |
| ESLint | PASS |
| Production build | PASS；Monaco 编辑器 chunk 约 4.03 MB，Vite 发出 >500 kB 警告 |
| Ruff lint | 源码及测试目录 PASS；`ruff check .` 会扫描 `output/` 和 `.tmp-test-validation/` 里的生成项目样例，报告 238 条样例 lint 问题 |
| Ruff format | 本轮四个核心后端实现/测试文件 PASS；全源码格式检查仍有其他既有文件不符合格式要求 |

## 独立评审

- Code Review：PASS。独立审查发现并修复 2 个 High（审批与取消竞态、Replan 缺少 CAS）和 1 个 Medium（跳过步骤别名/repair proposal 分支选择）；复审无 Critical/High/Medium 遗留。范围限于 V1 Runtime/Workflow、安全边界和相关测试。
- Ponytail Review：PASS。没有新增依赖、Runtime、Provider、SSE 或 Agent 抽象；复用了已有 Task Runtime 与 capabilities。全工作树含此前阶段的大量变更，LOC 仅按本 V1 核心文件列出。
- UI/UX Review：独立 Reviewer 对 `14-completed-result-current.png` 和 `15-empty-workspace-current.png` 的页面信息层级与入口修复判为通过；完整首次用户流程仍有默认空 Workspace → 项目列表的额外跳转，真实 Goal 受 Provider 阻塞，故整体体验验收为 PARTIAL。

## Red Team 与性能边界

- Generated test evasion：参数化检查 `assert True`、`skip`、`xfail`、`importorskip`、`skip/skipif` 标记和吞异常通过，共 8 类绕过，均被拒绝；对应测试通过。
- Goal scope：覆盖“只分析不修改”“不要运行测试”“不要使用浏览器”等约束；计划里不会出现相应的写入、Run、Browser 工具。英文 `Do not run any tests` 与 `Do not fully test this existing requirement` 已加入回归。
- Context isolation：并行创建 Requirement Alpha/Beta 的 Goal，分别保留各自 requirement_id，没有串 Context；对应测试通过。
- Approval/recovery safety：只允许恢复所属且等待审批的任务；等待审批期间用户修改的源码会保留并阻止覆盖；Replan 拒绝重放已完成的 source write。对应回归通过。
- Execution controls：重复 Start 的幂等键、待运行任务取消和取消运行中的子 Pytest 均有回归覆盖并通过。
- Limits：上述红队以解析、计划和运行时安全用例为主；由于真实 Provider 未配置，没有以真实模型完成恶意 Goal 的端到端演练。24-step 首次 Goal 在第一步前阻塞；长任务观察到 26 个事件，未达到 500 events、10+ AI calls 的压力场景。

## Screenshot 清单

用户要求的 01–12 文件以真实浏览器截图为准，不复制或伪造：

| 文件 | 状态 |
|---|---|
| `01-goal-entry.png` | 存在；旧项目上下文，不代表当前 Golden Journey |
| `02-plan-preview.png` | 存在；旧的只读计划，不代表本轮动态长任务 |
| `03-agent-running.png` | 存在于验收目录根部；只是预填 Goal 的待开始状态，不是 Running 证据 |
| `04-findings.png` | 存在于验收目录根部；是只读覆盖分析的 `COMPLETED_WITH_UNRESOLVED` 结果，不是本轮 Golden Goal findings |
| `05-decision.png` | 缺失 |
| `06-approval.png` | 缺失；真实 Goal 未到审批步骤 |
| `07-workflow.png` | 存在于 `screenshots/`；长任务工作流视图 |
| `08-studio-handoff.png` | 存在但为加载骨架，不能作为交接通过证据 |
| `09-retry.png` | 缺失 |
| `10-verification.png` | 存在；旧 Run 截图，不代表本轮 Goal |
| `11-final-result.png` | 存在；与 10 相同的旧结果视图 |
| `12-first-time-user.png` | 存在；修复 Planner 之前的未知依赖失败 |

有效补充截图：`13-studio-current.png`、`14-completed-result-current.png`、`15-empty-workspace-current.png`、`16-first-time-postfix.png`、`long-run-paused-after-refresh.png`。截图位于 `output/autonomous-qa-agent-v1/screenshots/`。

## Remaining

- 配置并验证真实 AI Provider，然后重新执行同一首次用户目标和完整 Golden Journey；Provider 不可用时不能通过代码模拟来替代。
- 在允许 Chromium 子进程启动的环境完成 Browser 全量回归（当前测试环境返回 `spawn EPERM`）；修复并在整套回归负载下重测 locator click 稳定性。
- 补全 Studio Run/Debug → 同一 Goal 恢复 → Verify 的真实 dogfood；补采未完成的 03–06、09 截图。

## Ponytail Impact

- Reused existing components：Task Runtime、TaskStep、Workspace/Workflow、Runtime projection、浏览器与 Pytest/TestRun UI。
- Reused existing backend services：AI Provider、JEV/Decision、Browser、Approval、Evidence/Artifact、Task SSE、Failure/Repair/Verification。
- Removed duplicate implementations：0；本轮通过扩展已有 Tool/Task Runtime 完成，没有新增第二套执行器。
- New files added：本次收尾新增 1 份验收文档；V1 实现另有 `docs/autonomous-qa-agent-v1.md` 设计说明。
- New dependencies added：0。
- New abstractions added：0。
- LOC added / removed：当前工作树相对 HEAD 的四份核心实现/测试文件（`task_workflows.py`、`task_runtime_service.py`、`test_agent_tasks.py`、`test_recorder_service.py`）为 3196 / 82。该统计覆盖此前 V1 实现与本次收尾，不能解释为本次收尾 patch 单独增加的行数。
- Why each new abstraction was unavoidable：无新增抽象。
