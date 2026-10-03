# AI QA Platform V2 Acceptance

验收日期：2026-10-02（Asia/Shanghai）。总体 **PARTIAL**：Runtime 收敛、真实运行/审批/重跑/调试链路与独立 Review 已通过；真实外部 AI Analyze/Design/Generate 和远程 JEV 因没有可用凭据未验收，不使用 Fake 冒充通过。

## Summary

这次基于已有未提交 V2 实现继续收敛，保护了开始时 154 个文件的字节备份及 Git 状态。没有重置用户修改、部署、付费模型调用、替换执行引擎或新增顶层业务页面。

独立验收服务：Web `http://127.0.0.1:15183`，API `http://127.0.0.1:18011`。DB、workspaces、artifacts 位于 `runtime/platform-v2-acceptance/live/`，与用户原运行库隔离。原运行库只用于只读备份迁移验收。当前真实模型状态 UNAVAILABLE，fallback_active=false。测试中的显式 Fake 仅用于契约测试，不列作业务 E2E 成功。

## Implemented

统一 Overview 中的实际测试结果/分页/有界日志；Studio 内嵌六视图；Failure 真关联和审批命令；正式 retry/Task 外键；Requirement/Binding 使用实际存储数据；可折叠 Platform；light/dark/system 主题；Flow 默认可读布局、滚动与全图；独立 Review 修复 Diff、源码冲突、重复 SSE、日志冻结、N+1、暗色对比度和 Trace 语义。

删除无引用 RequirementDetail，合并 StudioRunPanel/RunOutputPanel/RunsPage/ContextTaskProgress/FailureWorkflowPanel 中的重复执行视图。旧 TestDesignPanel 和 standalone Recorder/Debugger 仍有实际用途，保留兼容，不按文件名判定废弃。

## Architecture

详见 [platform-v2-architecture.md](platform-v2-architecture.md)。Run Store 管实时状态，RuntimeProjection 只读组合已存在实体；领域写命令与观察视图分离。没有创建第二套 Graph/执行状态机。

## Domain Changes

`test_runs.task_id`、`parent_run_id`、`origin_failure_id` nullable 外键负责正式关联；旧记录保守回填，不靠时间或标题猜关系。Task 的实际 targeted verification Run 同时有 Task、原 Run、原 Failure 三个引用。

审批摘要新增真实 unified Diff Artifact、截断标志、源文件存在性和 SHA-256。批准后 source.write_generated/source.apply_repair 校验当前文件；冲突 BLOCKED，保护等待期间修改。50 Task 列表独立实测 2 SELECT。

## Runtime

六视图共用 RuntimeDetail/快照/选中步骤；Runs、Studio、Requirement/Failure 的 ContextTaskProgress 复用同一观察组件。Task only 一条 SSE；同 Run 多消费者共用 Store。Overview 显示真实进度/测试结果；Inspector 展示真实 step/evidence/artifact/decision/browser/failure/run 关联。

有界上限为 500 events、200 log entries、20,000 log characters、100 Network/Console/Browser steps、32 Browser sessions。任务详情的领域轮询不建立第二条 Runtime SSE。取消/完成不会被迟到 snapshot 回退。

## Flow

原问题是长横向图被 Fit 到约 23%，字不可读且留白过大。现在默认纵向 100% 可读节点、原生滚动，支持横向、全图、实际大小、点选/前后步骤、定位/跟随执行、手动浏览暂停跟随和 Focus/Escape。

真实 DAG 结构决定布局；状态/日志/帧不重新排节点。600 秒 30 节点/100 边测量 layout mutation=0。初审 Task 画布 y≈786，修后约 y≈640–686；1366×768 默认仍需要下滚或 Focus 查看完整节点，这是明确剩余 UX 边界。

## Timeline

使用真实 Task/Step/Run/Execution/Browser/AI 时间。缺失时间显示 unavailable；可推导 Execution 时间标记 derived，绝不宣称录制的开始时间。

真实 15 秒 pytest Task `3a0654b5dfd641d4b28151b322a01cd4` 中，运行 bar 的宽度 3 秒间从 2.66333% 增至 12.7333%，完成后保留记录。证据 `output/playwright/platform-v2/journeys-reviewed/result.json`，截图 `timeline-real-growth.png`。

## Trace

安全 Normalizer 白名单/脱敏/字符串上限；非有限或负数 duration 不可用。Frame、raw prompt/response、整段源码/DOM 不放公共 Trace。普通 pytest 显示“执行 Trace / 运行开始 / 运行完成”，AI 文案仅用于实际 AI 场景。

## Browser

真实 pytest + Playwright BrowserSession、事件、Network/Console 和最后帧刷新恢复均验收。Browser/Timeline/Trace 同步使用已有关联，不生成假截图。真实 Browser E2E run `run_72ec40086144` 的 4 个 Browser 事件和 session lane 已验证；独立 UI 额外检查 Network/Console。

Artifact image Preview 显示真实 PNG，Download 文件头与 PNG 一致，text Preview 有真实内容；结果 `phase16/result.json`。

## JEV

真实 Local Strategy + Playwright 选择/动作验证已在 EXPLORE_PAGE 任务和截图中通过；外部 JEV 未配置，标为未验证。没有将规则选择包装成远程 JEV 推理，也没有补造 confidence。

## Failure

真实 pytest Failure → 收集 Evidence → FailureClassifier → 用户提供修正 → unified Diff 下载 → UI 批准 → 写入 → targeted pytest → verified=true 已走通。

Task `3927e4b8ea054795ac2304073dda4ede`，原 Run `run_91d7c4bb1b39`，Failure `fail_82843d00b929`，验证 Run `run_cab0ccfc1fbf` PASSED。AI budget=0、明确规则来源及用户提供一行修正；原断言不修改。完整差异 `journeys-reviewed/approved-actual.diff`。

外部 AI 诊断失败的真实记录仍保留，E2E B 为 PARTIAL；无模型成功、伪诊断或虚构验证。源码审批期间冲突/新文件抢占/完整 Diff 尾部保护由新增 4 项实际 workspace 测试及独立 Reviewer 验证。

## Studio

真实已绑定用例在 Monaco/Studio 调度 pytest，唯一 Run SSE，统一 Runtime 结果。Recorder 实际 navigate/click → Generate → 保存为 Case 并运行，Run `run_dffb0eb7c031` PASSED。

Failure → Studio/真实 debugpy 断点及 locals → 修改 value=1 为 value=2 → 保存 → UI 运行测试 → retry PASSED → 返回原失败详情，已通过。Failure `fail_507bdf3c0b62`，parent Run `run_d8175a2d057e`，retry `run_2ebd1108cd9b`，同时保留 parent_run_id/origin_failure_id。截图 `failure-debug-real-paused.png` 和 `failure-debug-retry-return.png`。

## Requirement Journey

Requirement `req_4b75225cca97` → Case `tc_c0e0af3f2cca` → 实际 AutomationBinding → Studio → Run `run_cd53a9b4c3d5` PASSED。此路径使用人工编写的测试，明确不冒称 AI 生成。

实际点击“AI + Jev 分析需求”得到可见失败，Provider UNAVAILABLE、fallback_active=false；没有生成假成功分析。AI Analyze → Design → Cases → Automation 的真实模型端到端验收为 PARTIAL。页内 Analyze/Design/Coverage/Case 能力和已有结构保留；旧 qa_model 为空的分析/设计入口继续兼容。

## Navigation

Before：原审计 14 个目的地/多组执行中心入口。
After：7 主入口 Dashboard/Projects/Requirements/Test Cases/Studio/Runs/Failures；Platform 可折叠 5 入口 Flaky/Quality/Security/Workers/Settings。Task 位于 Runs，旧 /tasks 保留 query 重定向；Recorder 从 Studio 进入。

## Database Migration

当前 head `0003_task_run_relationship`。真实原库只读 backup 到独立副本，upgrade 两次 → downgrade base → upgrade：35 表、882 条业务记录保持，44 个 Execution 时间明确 derived，Foreign Keys 开启；原库 SHA-256 完全不变。降级会丢新列元数据，报告没有将其称为零损失回滚。

证据 `output/playwright/platform-v2/phase28/legacy-migration-result.json`，`runtime/platform-v2-acceptance/legacy-migration.log`；单测迁移/legacy schema/歧义回填在 full suite 内通过。未执行原库写入迁移。

## Tests

最终 backend full suite：**423 passed、4 skipped、0 failed、0 errors**，704.14 秒，44 warnings；总 427 cases。4 个跳过项均要求 PostgreSQL 连接。证据 `runtime/platform-v2-acceptance/accepted-full.xml` / `.log`。包含 API、qa-core、worker、integrations。

最终 frontend：**58 passed、0 failed**，`frontend-reviewed-tests.log`。Typecheck、前端 ESLint、全 Python Ruff 均 PASS；最终 Vite build PASS，46.33 秒。Monaco 分块约 4 MB 的既有 warning 仍保留，未忽略失败检查。`git diff --check` 无 whitespace error，只有现有 CRLF 提示。

中间日志保留以追踪：新增日志测试首次漏导入 TestRunORM、旧状态断言仍期待 implicit Fake fallback，已分别修复测试导入/改为 UNAVAILABLE 后重新跑完整 suite；未把中间失败计作最终通过。旧初次 sandbox Chrome/临时路径权限失败也未计作有效业务结论。

复现命令（PowerShell，Python 使用 uv，前端使用 pnpm）：

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'runtime/uv-cache'
uv run --offline --no-sync pytest -q --basetemp runtime/platform-v2-acceptance/reproduce-tmp
uv run --offline --no-sync ruff check apps/api apps/worker packages scripts
pnpm --filter @ai-qa/web test
pnpm --filter @ai-qa/web typecheck
pnpm --filter @ai-qa/web lint
pnpm --filter @ai-qa/web build
```

Windows 下实际 Chrome/subprocess 测试通过自动审批在沙箱外执行；未安装新依赖，mise 未安装时使用已有 Node 24 / uv / pnpm。

## E2E

| 场景 | 结论 | 真实证据 |
| --- | --- | --- |
| A Task pending/running/complete、DAG、选择 | PASS | phase24/result.json；phase25/result.json |
| B 实际 pytest Failure + 模型诊断 | PARTIAL | 原失败真实，模型不可用，不伪造诊断 |
| C 实际 Browser / Trace / Timeline | PASS | phase-browser/result.json；phase24/C |
| D 刷新重建最后真实帧 | PASS | phase24/D |
| E SSE 实际 HTTP 中断并恢复 | PASS | 修复后 run_3f45b0c764b6，2 次连接、峰值同时 1、终态 PASSED、无重复 Projection events |
| F 审批/重跑/Verify | PASS（规则/用户修正路径） | journeys-reviewed/result.json，真实 Diff + UI Approval + 原关联 |
| G 10 分钟有界性能 | PASS | phase28-performance-reviewed/result.json；另有最终 retained heap 复核 |

另有 Main authored journey、Recorder Generate Save Run、Failure Debug Modify Retry Return、真实 Timeline 增长、Artifacts Preview/Download。所有业务运行使用真实 API/DB/pytest/Playwright，无 request mock；只有性能 DAG 负载是明确标记的 fixture，其未执行步骤保持 PENDING/SKIPPED，不作为业务工作流成功证据。

## Performance

修复后已完成 **600.635 秒**：30 steps、100 edges、500 有界 events、50 个真实 HTTP pytest assertions、200 行真实日志、100 条真实网络记录，pageerror=0、layout mutation=0，可见 Event Stream 9 行。期间其他真实 Task 验收加入列表，整页 DOM 936–975，节点图位置保持不变。

最终稳定环境复核增加 Chrome retained heap 采样，数据见 `output/playwright/platform-v2/phase28-performance-final/result.json` 和 `runtime/platform-v2-acceptance/performance-final.log`。下方 Final Measurements 以实际完成结果追加；不把原始堆每次 GC 波动误判为连续泄漏或稳定 retained heap。

## Code Review

独立 Reviewer 没参与业务实现，首次 1 P1 + 4 P2 全部修复、逐项复核关闭，最终 **PASS**。独立审批 tests 4 pass、Run Store 13 pass、50 Task 2 SELECT、20k log 重现修复确认。详见 [platform-v2-code-review.md](platform-v2-code-review.md)。

## UI Review

独立 Reviewer 初审 138 次真实检查，修后 30 次最终复核，总 **168 次**；覆盖 1920×1080、1440×900、1366×768 的 light/dark、Runtime 六视图、Studio、Requirement、Failure、Browser 遥测及真实状态。6 个 Studio 真运行 PASSED，pageerror/根级横溢出均 0。

主按钮 normal light/dark 17.20/16.42:1、hover 9.52/12.10:1、成功状态 6.43/10.55:1；暗色对比度、深链筛选/重复标题/列表密度、非 AI Trace 文案全部关闭，最终 **PASS**。详见 [platform-v2-ui-review.md](platform-v2-ui-review.md)，最终截图 `ui-review/recheck-final/`。

## Regression

13 项原能力覆盖：Projects、Requirements、Test Cases、Studio、Recorder、Runs、Failures、Debugger、Browser、JEV、Workers、Settings、Pytest。结果 `phase28/result.json` 有 18 项实际页面/操作检查：编辑需求和 Case、实际 Recorder 流程、debugpy 断点/step/continue、Browser 与 pytest、现有管理页面均 PASS。

JEV 的实际本地策略/设置回归 PASS，远程 JEV 为未验证；Workers 为现有管理页/契约测试验证，不冒称已有生产 Worker pool；真实模型能力不因 Fake 单测通过而标为 PASS。

## Remaining Gaps

1. 缺真实模型/JEV凭据，AI 分析、生成、模型诊断与远程 JEV 需在正确配置后再走真实业务验收。这是整体 PARTIAL 的主要边界。
2. PostgreSQL 环境未提供，SQLite 验证不能替代其专用集成测试。
3. 当前 Task workflow 无真实并行 sibling 调度，未生成 parallel 截图或新调度器。
4. 1366×768 默认 Flow 首屏高度、Monaco 大分块、旧 Requirement 兼容入口保留为非阻断 UX/维护项。
5. Recorder/Debugger 仍内存 session；重启丢交互状态符合现有实现，不宣称持久化恢复。源文件乐观 guard 不提供外部编辑器跨进程分布式锁。

## Deferred V2

真正 Agent Entity、产品 Multi-Agent、动态 Planner、Redis、Replay Player、Recorder/Debugger 持久化、AI 成本引擎、大规模 RBAC、部署和换栈均未开展；没有因 UI 名称新增不存在的领域对象。

## Final Acceptance

总体 **PARTIAL**。Runtime/正式关联/真审批修复/真实 pytest/Recorder/Debugger/有界性能/独立 Code 与 UI Review 已有可核验结果；外部 AI/JEV 仍需环境支持。工作保持未提交，避免把开始时已有用户修改合并成代理提交。所有 Runtime 数据和截图作为本地验收证据保留并忽略 Git，未提交。

关键证据入口：`output/playwright/platform-v2/journeys-reviewed/`（Diff、审批、完成、调试回跳、Timeline、AI 失败）、`phase24/`（pending/running/failure/browser/reconnect）、`phase25/`（Event Stream pause/resume）、`phase28/`（Recorder/Debugger/回归/迁移）、`ui-review/recheck-final/`（最终主题和尺寸）、`phase28-performance-final/`（最终负载）。


## Final Measurements and Git Status

最终稳定测量 **600.026 秒、586 个样本**，仍为 30 steps/100 edges/500 events、50 个真实 pytest 通过、200 行日志、100 条网络记录。DOM 960–978（分钟采样均为 978）、可见 Event Stream 9 行、节点 layout mutation=0、pageerror=0。10 次 Projection 请求中位 65.45 ms、最大 287.83 ms。

Chrome GC 后 retained heap 从 **21.30 MB → 21.90 MB（+2.85%，约 0.61 MB）**，分钟 retained 样本约 21.19–22.05 MB；未观察到 10 分钟内无界 retained growth。该结论限定于本负载和测量时长，不冒称无限运行证明。证据 `phase28-performance-final/result.json` 与 `runtime/platform-v2-acceptance/final-performance-summary.json`。

工作树当前 103 个已跟踪改动、73 个未跟踪文件（完整逐文件计数，包含开始时已有 V2 实现）；未创建 commit。初始 154 个快照文件中 124 个字节保持、29 个在本任务授权范围编辑，唯一移除为已确认无引用的 RequirementDetail，原始备份仍在。来源记录 `runtime/platform-v2-acceptance/change-provenance.json`；最终状态 `final-git-status.txt`、全差异 `final-diff-stat.txt`。这些数字不表示 176 个文件都是本轮新增开发。

已取消仅为 Artifact 预览验收创建的待审批 Task，验收项目剩余活跃 Task=0；Recorder session 已关闭，Debugger 已结束。专用 Web/API 服务保留用于直接查看结果，原有服务未动。备份、测试临时文件、Runtime 数据和 Playwright 截图已在 Git ignore 范围，未提交。
