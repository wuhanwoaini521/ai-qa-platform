# JEV Browser Action Orchestration V1

## 目标与边界

复用现有 Runtime Task 执行自然语言浏览目标：AI 根据当前真实页面生成少量候选动作，JEV 只在候选之间选择，Playwright 执行动作，再重新读取页面并验证结果。每次决策都依赖最新观察，不预先生成盲跑脚本。

V1 面向桌面网页。购物旅程最多验证加入购物车；结账、付款、下单、账户修改和破坏性操作仍会阻止或要求确认。没有新增第二套 Runtime、Browser controller、JEV service 或 AI provider。

## 执行循环

1. 通过现有 `EXPLORE_PAGE` Task 和 BrowserRecorder/Playwright 打开目标站点。
2. 页面明确通过 `role=status` 显示仍在加载时，最多等待 2 秒；同一次 Agent 运行里，相同 URL 和加载文案只等待一次。随后观察 URL、标题、可见文本、Accessibility tree、交互控件、表单值、选择状态、网络计数和轻量 state hash。
3. 现有 AI provider 读取目标、当前子目标、最近动作结果和页面快照，返回结构化 `BrowserAgentPlan`，其中每个 `BrowserActionCandidate` 只能引用本次观察到的控件。
4. 在 JEV 前校验目标存在、可见、启用、动作与元素类型相容，搜索输入值合法，选择值属于启用选项；拒绝高风险动作。JEV 输入只含经过校验的目标控件和最多 5 个候选。
5. 候选多于一个时调用现有 DecisionService。JEV 只能返回候选 ID 或 abstain，不能创造 locator。JEV 不可用、超时、弃权或返回无效 ID 时回退到 AI 首选或本地候选排序，并写入失败与 fallback 记录。
6. 用现有 locator 验证器和 Playwright 执行动作，保存 URL、耗时、状态 hash、动作结果、截图和 evidence。
7. 重新观察页面，校验预期效果；不符合预期时重新规划，受最大动作数、恢复次数、相同控件和 URL 往返保护。
8. 只有当前页面证据与完成条件吻合才报告完成。购物车任务必须观察到购物车数量增加或新的确认提示。

## 安全与恢复

- 普通搜索/筛选提交只在控件本身具有明确搜索语义时视为安全。目标文本里的“搜索”不能降低其他表单提交控件的风险。
- 购物车操作要求目标明确表达加入购物车意图；英文及常见中文“添加到购物车”等表达受支持。不会自动结账。
- 暂停在动作边界生效。项目任务通过已有 RecorderSession 让用户接管同一页面；恢复时重新观察，并把暂停期间页面变化记为 human takeover。
- 状态无变化、动作未达到预期或执行失败会触发有限重规划；反复同控件、相同页面状态或 URL 往返会停止并记录原因。
- 未绑定项目的任务使用后台 headless browser，当前没有可接管的用户可视 Recorder 页面。

## 数据与界面

沿用 Task steps、events、Decision、evidence、artifacts、AI trace 和 BrowserRecorder。Decision samples 保存页面状态、候选、AI 首选、JEV 选择/分数、fallback、provider/model、AI/JEV 延迟、token 计数、动作结果和验证结果，供离线评估。

Workspace 默认只显示 QA Agent、当前目标/动作/最近结果。Runtime Trace 展示事件序列；Flow 显示现有 task-step DAG；候选、JEV 分数、fallback 和验证细节放在 Inspector。Browser 页面从同一 RecorderSession 打开，不创建第二个 viewer。

## 已知限制

- 当前工作环境配置的是 fake AI provider，未提供真实 AI API key，且 JEV 未启用/未配置 key；因此真实模型 + 真实 JEV 的线上决策结果无法在本环境验收。
- 当前网络策略阻止访问 `www.uniqlo.com`，无法完成优衣库 live journey。项目 demo shop 只能证明浏览器闭环和购物车证据机制，不能代替真实优衣库或真实 provider 验收。
- 页面完成判断依赖可观察文本、URL、显式 completion evidence 或用户提供的 observable text criteria；对无法从页面观察的目标不会声称完成。

## 相关实现

- `apps/api/app/services/task_runtime_service.py`：复用 Task Runtime 执行、观察、候选验证、JEV 调用、执行、恢复与证据持久化。
- `packages/qa-core/qa_core/ai/models.py`：结构化候选及浏览计划契约。
- `packages/qa-core/qa_core/ai/browser_safety.py`：候选的独立风险分类。
- `apps/api/app/services/locator_decision_service.py`：复用 locator 校验。
- `apps/web/src/features/runtime/RuntimeOverview.tsx`、`RuntimeTrace.tsx`、`RuntimeInspector.tsx`、`RuntimeBrowser.tsx`：默认状态、事件/决策细节与同会话浏览器入口。
