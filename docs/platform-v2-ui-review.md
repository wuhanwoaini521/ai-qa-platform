# Platform V2 独立 UI 评审

评审者未参与业务实现，只修改本评审报告与验收脚本。评审对象是 `http://127.0.0.1:15183` 的真实应用及 `http://127.0.0.1:18011` 隔离验收 API，未伪造接口或浏览器画面。时间：2026-10-02。

## 初审结论

**需修复。** 实际交互、主题切换、数据关联基本成立；存在一个影响暗色主题主操作可读性的 P1，以及两项执行界面的 P2。以下结论以初审时实际界面为准，修复后应追加复审，不覆盖初审证据。

**最终独立复审：PASS（本报告覆盖范围）。** 实现者修复后，评审者用真实浏览器重新检查三种尺寸、两种主题。UI-01 / UI-02 / UI-03 全部关闭；短屏仍需滚动或使用 Focus 的限制见末尾，不代表整个产品已完成 WCAG 合规认证。

## 覆盖与证据

- 1920×1080、1440×900、1366×768，分别检查 light、dark；通过 `documentElement.dataset.theme` 及 computed `--surface` / `--ink` 核实真实主题。
- Runtime Overview / Flow / Timeline / Trace / Browser / Artifacts、Flow Inspector / Fit、真实 Browser 历史、Retry 父运行链、Requirement、Failure、Studio：78 次截图检查。
- 在 Studio 分别运行现有 `tests/test_regression_debug.py`，源码未修改。6 个真实 Run 均 PASSED，分别检查嵌入 Runtime 六视图：36 次截图检查。运行 ID 详见 `studio-result.json`。
- light / dark 下检查 Runtime 六视图 Focus：12 次截图检查。Escape 正常退出；Flow 选中步骤切到 Timeline 再回 Flow，selection 保持。
- 另外检查真实 Browser 的 Network / Console：12 次截图检查。实际 Network 有 2 条 GET / 200 记录，Console 有真实日志；不是空占位截图。
- 上述 138 次截图检查：浏览器 `pageerror` 为 0，根文档横向溢出为 0。导航中被取消的网络请求不视为应用错误。画布、编辑器内部滚动不等同根文档溢出。
- 评审者直接查看了 Flow / Inspector / Trace、Requirement、Failure、Browser、Artifacts、Timeline、Studio 等代表截图，并查看已有真实 pending / running / failed / retry / completed / Local Strategy / Event Stream 证据。
- 当前调度器没有实际并行 sibling 执行，本评审未制造“并行运行”截图。没有可用外部 AI / JEV；本地策略与 Playwright 验证不冒充外部模型结果。

截图目录：`output/playwright/platform-v2/ui-review/`。可重跑脚本：`review.py`、`studio_review.py`、`detail_review.py`、`telemetry_review.py`。测量文件：`result.json`、`studio-result.json`、`detail-result.json`、`telemetry-result.json`。

## 发现的问题

### UI-01 · P1 · 暗色主按钮及状态文字对比度不足

`apps/web/src/index.css:745` 的 `.btn-primary` 使用 `background: var(--ink)`，但前景固定 `#ffffff`。`index.css:4057` 的暗色主题将 `--ink` 改为 `#edf1f7`，导致已启用的“新建需求”“AI + Jev 分析需求”等按钮白字白底。实际测得 `rgb(255,255,255)` / `rgb(237,241,247)`，对比度 **1.13:1**；同按钮 light 模式为 **17.20:1**。

Runtime 状态使用 `runtime.css:76` 的 `--surface-muted`，该变量在 `index.css:175` 固定浅色，暗色主题未覆盖；`PASSED` / `COMPLETED` 因此是浅绿字浅底。应修正主题语义变量或组件配色，并同时检查正常与 hover 状态。

证据：`1440x900-dark-requirement.png`、`1366x768-dark-failure.png`、`1440x900-dark-browser-real-history.png`、`detail-result.json`。

### UI-02 · P2 · Task 深链上下文与画布可见面积不匹配

`apps/web/src/pages/TasksPage.tsx:73` 读取 `taskId` 后只更新 detail，仍默认选中“运行中”。打开已完成任务出现“运行中 (0)”与“任务列表 (0)”，右侧却显示已完成 Task，形成矛盾的上下文。

`index.css:2660` 列宽为 `0.82fr / 1.18fr`，左列空列表占约 40%；`TasksPage.tsx:270` 起重复输出 Task 标题、状态及 ID，紧接着 RuntimeHeader 再输出一遍。1920×1080 时 Flow 画布约从 y=786 开始；1366×768 首屏看不到节点。建议深链与筛选同步、缩小任务列表，并让 RuntimeHeader 承担唯一执行标题。

证据：`1920x1080-light-runtime-flow.png`、`1366x768-light-runtime-flow.png`。

### UI-03 · P2 · 普通 TestRun Trace 被标为 AI 分析

没有 AI Calls 的真实 pytest TestRun，在 Runtime Trace 中显示“AI 执行过程”“AI 运行开始”“AI 分析完成”。`apps/web/src/components/AIExecutionTimeline.tsx:25` / `:38` 的 lifecycle 标签与 `:108` / `:111` 的标题在 `runtime=true` 时仍用 AI 文案。应让 Runtime 模式采用通用执行措辞，AI 面板保留现有 AI 标签。

证据：`1920x1080-dark-studio-runtime-trace.png`；对应真实 run `run_2bedf6462411`。

## 可确认的改善

Flow 默认纵向 100% 的节点正文可读，长标题分行，工具与耗时作为次级信息；Inspector 选中态明确，专注模式可以有效增加画布面积。查看全图是显式操作，不会在进入时把所有节点强制缩成无法阅读的小卡片。

Browser 的已结束运行明确标注“运行已结束 · 最后一帧”，真实截图与会话、网址、状态对应；没有 Task 浏览器会话时使用空态，未假装有画面。Failure 的断言失败明确提示不适用定位器修复，未把 AI Provider 缺配置包装为成功诊断。Artifacts 只展示实际存在的截图制品与下载/预览入口。

## 修复后复审

评审者未参与整改。实现者修改后，独立复审期间又发现 light 成功状态对比度 2.97:1，以及通用按钮 hover 规则覆盖主按钮前景，导致 hover 对比度 light 1.81:1 / dark 1.36:1。上述问题已回报实现者并补修，再次独立执行带对比度断言的浏览器检查。

最终脚本：`output/playwright/platform-v2/ui-review/recheck.py`。最终结果与 30 张截图：`output/playwright/platform-v2/ui-review/recheck-final/`；初审截图与中间 `recheck/` 测量保留。

| 复核项目 | light 实测 | dark 实测 | 结论 |
| --- | --- | --- | --- |
| 主按钮正常态对比度 | 17.20:1 | 16.42:1 | PASS |
| 主按钮 hover 对比度 | 9.52:1 | 12.10:1 | PASS |
| Runtime 成功状态对比度 | 6.43:1 | 10.55:1 | PASS |
| Task 深链筛选 | “全部”选中 | “全部”选中 | PASS |
| Task 列表宽度 | 260px | 260px | PASS |
| Task 标题去重 | Runtime 内唯一标题 | Runtime 内唯一标题 | PASS |
| 普通 TestRun Trace | 执行 Trace / 运行开始 / 运行完成 | 同左 | PASS |

30 次最终复核全部完成：`pageerror` 为 0、根文档横向溢出为 0。评审者再次直接查看了最终 1366×768 dark Inspector、1366×768 light Flow、1440×900 dark Requirement 主按钮与 1920×1080 dark 普通 TestRun Trace 截图。

初审 1920×1080 Flow 画布约从 y=786 开始，整改后提前到约 y=640–686，列表内容能显示且不再占 40% 宽度。1366×768 默认页面的画布约从 y=688 开始，首屏只露出第一个节点上部；完整阅读仍需要向下滚动或点“专注模式”。这是剩余的短屏密度改善空间，已有可用操作，未作为本轮整改阻断项。Focus 六视图与 Escape 退出已在初审真实交互中验证。

复审开始时专用验收 API 曾因 SQLite lock / 重启暂时不可用；恢复后才完成最终整轮检查。中间中断未计为通过，也未替换成模拟接口。
