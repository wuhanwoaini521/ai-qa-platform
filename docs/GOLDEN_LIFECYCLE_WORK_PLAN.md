# Golden QA 生命周期实施与验收计划

基线：`1fdcf50`。目标是用现有 Requirement → TestDesign → TestCase → AutomationBinding → TestRun → Failure/Artifact 贯穿项目，不新增顶级 Knowledge 页面、第二套 AI Runtime 或 Graph DB。

## 实施范围

| 工作 | 现有实现与需要补齐的行为 | 验收 |
|---|---|---|
| 结构化测试模型 | 复用现有三种实体；增加有界 Pydantic 内容与覆盖引用；稳定展示 ID | CRUD、旧客户端兼容、无跨项目/悬空引用 |
| 需求分析与设计 | 复用 Orchestrator/AIExecutionService/DecisionService；持久化结构化结果、阶段、来源、Jev 排序 | 实际 AI/Jev、失败与 Fake 明示、重新打开可回顾 |
| Knowledge 与 Coverage | 从既存实体/外键及内容引用动态投影；有真实分母、最新有效执行与可点击明细 | AC → Case → Nodeid → Run → Evidence；过滤/搜索/邻域 |
| Golden Demo | 独立标记的 Demo Shop；小型本地页面、真实 fixture、6 个场景与一项已知 Locator 失败 | 幂等 seed、安全 reset、真实通过/失败历史 |
| 项目 Journey | 项目 Overview/Knowledge、六步 Stepper、下一操作、面包屑与上下文持久化 | 不重复选项目/对象，旧 URL 保留 |
| Requirement/Test UX | 结构化分析、交互思维图、场景图、覆盖明细、Case Flow/Table 与 readiness | 能说明测试为何存在、覆盖何项、如何自动化 |
| Studio | 上下文、Code/Record/Debug/Review、同页 Live Run/Evidence、数据、网络、命令面板 | 生成/审批/执行/调试/修复可在同一上下文完成 |
| Review 与 Regression | 独立 Code/UX Review；所有已有回归与新增业务测试 | 实际结果记录，PostgreSQL 不可用如实说明 |
| 验收报告 | Golden、Failure、Traceability 三条完整 E2E，至少八张实际截图 | 数量/覆盖/点击/跳转/缺失项来自真实数据 |

## 数据边界

- 结构化内容保存在现有实体的 JSON 文档列，关系来自现有实体外键与校验后的内容引用。图谱是可重建的读模型。
- Demo 数据与自动化均属于专门的 Demo 项目；reset 必须验证标记并拒绝活跃运行，不能删除用户项目或任意目录。
- 种子参考分析明确标识为人工参考资料，不能当作 AI/Jev 的已完成调用；运行历史只能来自实际 pytest。
- AI 只加载当前对象及有界一/二跳关系，不发送整个图谱；覆盖率由确定性查询计算。
- 图谱中的执行、失败、修复与证据只引用已经存在的真实记录。

## 当前进度

- [x] 读取完整需求，核对已有接口、模型、页面与执行链。
- [x] 结构化模型、受治理的分析工作流、场景设计、Knowledge/Coverage。
- [x] Golden Demo seed / reset / 本地真实测试站点；reset 和引用校验有 API 回归。
- [x] 项目 Journey、需求与 Test Case 上下文视图。
- [x] Requirement / Test Case / Studio UX、同一 Run 的 live evidence/telemetry。
- [ ] Golden、Failure、Traceability 三条完整持久化 E2E；当前真实浏览器受进程启动权限阻断。
- [x] 完成静态代码与 UX 第二轮自查；发现问题已修复并重新运行针对性回归。
- [ ] 由不同审查者完成独立 Code/UX Review。
- [ ] 真实 AI + Jev 成功验收；已调用已配置服务，当前 AI 输出未通过 JSON Schema，Jev 连接探测返回 network_error，均未伪称成功。
- [ ] PostgreSQL 回归；环境未设置 `AI_QA_TEST_DATABASE_URL`。
- [x] 整理实际验收摘要，并按核心后端、前端体验、Demo/验收材料分类提交；未通过的实测项保持未勾选。

## 本轮实测（2026-10-02）

- Demo 图谱实际计数：1 Requirement、6 AC、3 Business Rules、3 Risks、5 Flow、7 Scenarios、7 Designs、7 Cases、6 Automation bindings、0 persisted Runs。AC/rule/risk/flow/negative 设计覆盖分别为 6/6、3/3、3/3、5/5、1/1；自动化为 6/7；尚无真实持久化执行记录，因此 execution 为 0/6、pass 分母为 0。
- 分析流程保留人工 `REFERENCE`，实际 AI 记录为 `FAILED / INVALID_STRUCTURED_OUTPUT`：模型两次返回通用文本，未通过 `RequirementAnalysis` 校验，结果未覆盖参考资料且 Jev 未运行。另一个合成风险排序探测由 Jev 返回 `fallback / network_error`。
- 完整 Python 回归：359 passed、5 failed、4 skipped。5 个失败均因 Playwright Chromium 子进程 `spawn EPERM`；其中 2 个旧 Agent Task 测试、3 个 live browser telemetry 测试。另有 4 个已配置跳过的用例。改动涉及的 API 工作流回归 11 passed，AI/provider 回归 7 passed；不启动浏览器的 telemetry 回归 3 passed。
- Web typecheck、lint、12 个单测、i18n（20 个 namespace、2 种语言、1386 个 key）通过；Production build 通过，Monaco editor chunk 约 4 MB，Vite 有大 chunk 警告。
- 全仓库 Ruff lint 通过；本次改动的 Python 文件格式检查通过。全仓库 `ruff format --check .` 仍会指出未修改的既有 `scripts/task.py` 排版差异。
- 当前保存的 Golden UI 实际截图仅有 Overview 与 AI loading 两张：`output/playwright/golden-01-overview.png`、`output/playwright/golden-02-ai-progress.png`。尚未生成用户要求的八个最终状态截图；CLI 包未在本机离线缓存，自动化用例不能在当前权限下启动 Chromium。
