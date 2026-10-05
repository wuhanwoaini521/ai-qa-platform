# JEV Browser Orchestration V1 Acceptance

## 结果

**Overall: PARTIAL**

**Architecture: PASS（代码路径和本地 fixture E2E）**。AI 候选 → 安全校验 → JEV 候选选择/回退 → Playwright 执行 → 新观察 → 证据校验已接入现有 Task Runtime。

**UNIQLO Journey: BLOCKED**。尝试加载 `https://www.uniqlo.com/cn/zh_CN/` 时浏览器返回 `net::ERR_NETWORK_ACCESS_DENIED`，页面保持 `about:blank`。没有最终 URL、购物车状态或 live journey 步骤可报告；这不是产品流程 PASS。

**真实 AI/JEV: BLOCKED**。当前设置为 fake AI provider，无 AI API key；JEV 未启用且无 JEV API key。实际模型选择质量、线上延迟与真实 JEV 正确率尚未验收。测试替身结果仅证明调用契约和集成行为。

**Final Question: NO**。本环境还不能证明真实 AI 和真实 JEV 已共同驱动一次真实站点浏览直到目标完成；需在可访问优衣库并配置真实 provider 的环境重跑。

## Golden Journeys

### 优衣库

- 状态：BLOCKED（网络访问被拒）。
- 步骤、Final URL、Cart Verified：未产生；不得将 demo shop 结果替代为优衣库结果。
- AI Calls / JEV Decisions / Correct / Abstain / Fallbacks / Browser Actions / Failed Actions / Recoveries：无 live 运行数据。

### 第二站：项目 demo shop

- 状态：PASS（本地真实 Chromium 页面与真实 Playwright 操作；AI 与 JEV 为 fixture provider）。
- Journey：搜索 Everyday Tee → 打开商品 → 选择 White → 选择 M → 通过中文“添加到购物车”按钮加入购物车；user goal 同时包含中文加入意图。
- AI Calls：6（fixture）；JEV Decisions：4（fixture；另外两步只有一个安全有效候选，不需要 JEV）；JEV Correct：4（由 fixture 明确选择并通过后续动作证据）；JEV Abstain：0；Fallbacks：0。
- Browser Actions：6/6 成功；Failed Actions：0；Recoveries：0；Loop Detection：未触发；Goal Completion：通过页面购物车数量/确认变化验证。
- 样本及截图作为 Task artifacts/evidence 保存。该结果验证站点无关的浏览执行路径，不代表真实 AI/JEV 线上质量。

## 接管与恢复

- JEV 不可用回退：本地 browser E2E 以 fixture timeout 验证 fallback provider、原因和决策样本被记录。
- Take Over → Resume：本地 HTTP 页面 E2E 在同一个 BrowserRecorderSession 手动将页面切到 `/manual`，恢复后 AI 观察到新 URL，`human_takeovers=1`。
- Bad action → recovery：PASS。本地真实浏览器 E2E 让 JEV 选择一个不会产生预期效果的可见按钮；Agent 标记 unexpected、重新观察并选择详情链接，随后用页面证据完成目标。
- Loop Detection：PASS。真实本地页面 E2E 重复选择同一可见控件两次，第三次选择前由 guard 阻止执行并记录 `browser.loop_detected`；重复控件和 URL 往返另有单元断言。

## 前端验收

- 默认 QA Agent 状态、Runtime Trace/Flow/Inspector、同 RecorderSession 浏览器链接：实现已接入。
- Node 测试：78 passed。
- Typecheck：PASS；Lint：PASS；Build：PASS。构建报告 Monaco chunk 大于 500 KB 的既有拆包提示，不影响构建成功。
- 页面检查截图（使用 route-mocked API 与合成 Runtime payload，仅用于 UI/UX 视觉检查，不是 live AI/JEV 运行）：
  - `C:/Users/admin/.codex/visualizations/2026/10/03/01a10202-19f4-7e82-bd6e-428808389025/jev-runtime-overview.png`
  - `C:/Users/admin/.codex/visualizations/2026/10/03/01a10202-19f4-7e82-bd6e-428808389025/jev-runtime-flow.png`
  - `C:/Users/admin/.codex/visualizations/2026/10/03/01a10202-19f4-7e82-bd6e-428808389025/jev-runtime-trace.png`

## 后端与代码审查

- 覆盖候选 schema、动作安全、购物车证据、目标完成证据、loop guard、JEV fallback、候选约束、真实本地浏览器执行、第二站购物车和同会话人工接管。
- 本轮独立只读审查发现并修复：搜索目标误降级任意 submit、两词目标只匹配一个词即可完成、中文“添加到购物车”漏识别。
- Focused backend/browser regression（最终代码）：**16 passed**（164.41s）；覆盖浏览器安全/计划/购物车/loop 单测、Task replan、JEV 正常/回退、错误动作恢复、实际 loop guard、中文按钮 demo shop 和同 RecorderSession 接管恢复。
- Backend full regression（最终修复前运行）：474 passed、4 skipped、5 failed。1 项旧 replan 测试假设 EXPLORE_PAGE 有两个 runtime steps；测试现已改为显式补一个 synthetic step，并在 focused regression 中通过。另 4 项既有直连 Playwright Chromium 的测试因环境进程权限失败（`spawn EPERM`）；本轮 browser-agent E2E 使用项目 `launch_chromium` 路径通过。尚未在最终修复后重跑全套。
- 增加有界加载等待：页面 `role=status` 明确显示 Loading 时，在生成候选前最多等 2 秒；同一 Agent 运行内每个页面 URL/加载文案只等一次。第二站异步目录初始加载 E2E 通过。
- **Code Review：PASS。**独立复审确认中文购物车意图、按钮风险分类和确认文本完整；重复加载等待按 URL/文案去重；目标词需全部匹配，submit 放行只由控件自身搜索语义触发；无剩余 P0–P2 问题。
- **Ponytail Review：PASS**；没有新增依赖、service、manager、runtime 或 adapter。新增两个 Pydantic schema 表达结构化模型响应；继续复用既有 Task Runtime、Playwright、AIProviderRegistry、DecisionService、LocatorDecisionService、RecorderSession 和 evidence/artifact API。
- Hardcoded UNIQLO Logic：NO（核心编排代码中无 `uniqlo`、固定裤子/黑色商品路径或站点专属 selector）。

## Ponytail Impact

- Reused existing components: Task Runtime、BrowserRecorder/RecorderSession、Runtime UI、Playwright locator 验证器。
- Reused existing backend services: AIProviderRegistry、DecisionService/JEV、Task/Decision/Event/Evidence/Artifact persistence。
- Removed duplicate implementations: 0；功能扩展已有路径，没有引入第二份实现。
- New files added: 本功能新增 `apps/api/tests/test_browser_agent.py`、本报告和设计说明；其他 worktree 文件已有用户变更，不在这里归因。
- New dependencies added: 0。
- New abstractions added: 2 个 Pydantic 响应 schema（候选动作和计划），作为 AI 结构化响应边界；未新增运行时服务或 orchestration manager。
- LOC added / removed: 当前 worktree 在本任务开始前已有多轮未提交用户改动，Git 无法按本轮准确拆分。受控实现集中扩展既有服务和模型文件；不把累计 dirty diff 的行数伪报成本轮净增量。
- Why each new abstraction was unavoidable: 模型返回的候选列表、动作类型、候选 ID 和完成证据需要受限、可校验的结构化契约；否则只能依赖自由文本解析，无法安全地把模型输出交给 JEV/Browser。

## 最终状态

本地闭环、回退和人工接管已有可重复验证；优衣库 live journey 与真实 AI/JEV 验收仍 BLOCKED，因此 Overall 保持 PARTIAL。
