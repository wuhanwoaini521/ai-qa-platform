# 能力对标与差距清单（2026-10-31）

目的：回答“之前调研的开源项目功能都加了吗”，并给出从「需求 → 执行」流程继续演进的排序。

## 一、四个开源项目的实际处置

结论：**没有把任何框架作为运行时依赖引入**，只吸收了思想并用现有抽象实现。

| 项目 | 吸收的点 | 落地情况 |
|---|---|---|
| browser-use 0.13.14 | 有界浏览器 Agent 循环（观察→决策→动作→证据） | 已实现为 Task Runtime 内的 Browser Agent，带步数/时长/重试上限，经 BrowserRuntime 执行；未引入其 SDK。 |
| tester-army/e2e 0.22.0 | 编排 + 从录制生成 POM/脚本 | 以 Recorder → Workspace 生成脚本 + 人工确认的方式实现；其依赖的 `playwright-core 1.64.1` 超过本项目 1.62.0 上限，明确不安装。 |
| Scrapling 0.5 | 自适应选择器/容错抓取 | 以 Jev 决策 + Playwright 校验 + 定位器修复建议（人工批准后精确重跑验证）实现；未引入其 fetchers。 |
| Crawl4AI 0.9.5 | 结构化抽取 + LLM 抽取 | 以 Discovery 的观察状态 → 草稿断言/回放步骤（仅建议、需人工采用）实现；其许可证带额外署名条件，未引入。 |

来源与版本证据：`docs/architecture-review/framework-comparison.md`（tag 固定、license、依赖对比）。其余 7 个框架仍为 **未验证**，11 框架门禁仍 **DEFERRED**。

## 二、现有流程能力盘点（代码为准）

| 阶段 | 现状 | 证据 |
|---|---|---|
| 需求 | AI 分析 + Jev 决策 + 持久化历史/阶段/回滚/取消/重启收敛 | `requirement_lifecycle_service.py`，历史记录 `SUCCESS/FALLBACK/FAILED`、`analysis_stale` |
| 场景/用例 | 结构化设计、场景草案、采用后才生成用例 | `requirement_lifecycle_service` 决策阶段、用例详情页 |
| 自动化 | Monaco 编辑器、录制→脚本、人工批准 | `automation-studio`、`recorder_service.py` |
| 执行 | pytest/Playwright，Worker/远程 runner，SSE 实时事件 | `task_execution_*`、`test_run_service.py`、`workers` |
| 证据 | 截图、页面证据、日志、运行轨迹 | `browser_sessions`、`page_evidence`、Runtime 投影 |
| 失败诊断 | 真实 AI + Jev 分类、流式进度、历史可信度 | `failure_service.py`、`failure_workflow_service.py` |
| 修复 | 提案 → 人工批准 → 应用 → 精确验证重跑 → 审计 | `test_live_locator_repair_acceptance.py`（真实 Provider 通过） |
| 探索 | 实时浏览器帧、元素框、草稿断言/回放 | `quality_discovery*`、`QUALITY_DISCOVERY.md` |
| 质量 | 覆盖率、风险分、发布门禁、变更影响与回归选择 | `quality_intelligence_service.py` |
| 集成 | GitHub / Jira / TestRail / Jenkins 适配器 | `packages/integrations` |
| 治理 | AI 预算、provenance、脱敏、RBAC/项目 ACL | `ai_execution_service`、`redactor.py`、`authz.py` |

## 三、仍缺的能力（按价值/成本排序，已按代码复核修正）

1. **Grounded 断言生成（P0）**：`qa_core/orchestrator.author_test()` 已具备知识接地（`KnowledgeGrounder`）、代码生成（`PytestCodeGenerator`）与 AST 校验，但**没有任何产品路径调用它**；需求分析产出的场景/断言仍来自通用提示词，缺少“断言 ← 验收标准（criterion_id）”的可校验契约。这正是社区文章 45052 的核心质问：AI 改了操作后，如何证明仍在验证原业务规则。
2. **修复只覆盖定位器类（P1）**：非 `LOCATOR_CHANGED` 直接 `LocatorRepairNotApplicableError`；断言类、数据类、环境类失败没有提案通道。对外命名也要收紧——当前“AI 修复”实质是定位器修复。
3. **失败聚类与归因（P1）**：只有同 nodeid + classification 的 recurrence，没有跨用例相似度聚类、簇级分诊。
4. **需求→用例→脚本→提交追溯（P1）**：有 criterion/rule/risk id 与覆盖率、用例到文件的绑定，缺 commit/行号级链路；Discovery findings 的 provenance 未做 schema 强制。
5. **测试数据与登录态复用（P1）**：`storage_state` 只在失败快照中加密保存作证据，不能复用于执行；没有数据工厂与清理策略。
6. **生成物评测门禁（P1）**：有决策离线指标与 AI 遥测，但需求分析/用例/断言没有 golden set 回归门禁。
7. **视觉回归（P2）**：只有截图证据，没有基线与差异审批。
8. **接口/契约测试执行（P2）**：模型允许 API 维度，执行仍只有 pytest subprocess，没有 API runner 与同 run 混合编排。
9. **缺陷单**：`JiraService.create_bug_draft` + `create_bug(confirm_publish)` **已存在**（预览后确认发布），缺的是与失败簇/归因联动、以及 UI 入口的完整闭环——因此不算从零新建。
10. **环境缺口**：PostgreSQL 通道未验证；11 框架门禁仅 4 个已核验；视觉回归/批量定位修复/多租户 SAML/S3 均无代码。

## 四、下一批交付建议（修正后）

| 优先级 | 切片 | 验收标准 | 复用 |
|---|---|---|---|
| P0 | Grounded 断言草稿接入产品 | 从需求/验收标准生成断言草稿，每条引用 `criterion_id`；UI 显示 diff 并需显式采纳；无来源断言拒绝保存；采纳后判定仍由 pytest exit code 决定；可回滚 | `orchestrator.author_test`、`CREATE_TEST` 的 validate+approval、`DecisionService` |
| P1 | 定位器之外失败类型的提案边界 | 断言/数据/环境类失败给出“不可自动修复 + 建议动作”，而不是报错即止；仍不自动改代码 | `FailureCategory`、`failure_workflow_service` 状态机 |
| P1 | 失败聚类 | classification + 错误特征 + DOM 相似度聚簇；簇级批量 reject、逐条 apply 仍走权限与状态机 | failure history、`AUTOMATION_EDIT` |
| P1 | 追溯矩阵 | 每条用例可回溯 criterion 与文件/行；无绑定标注“未自动化” | coverage + bindings + git diff |
| P2 | 缺陷单闭环 | 失败 → Jira 草稿（已有）→ 预览 → 确认发布 → 关联失败与审计；与聚类联动 | `JiraService.create_bug_draft/create_bug` |

约束：不新增平行的 Runtime/Agent/Provider/编排体系；外部写入一律先预览后授权；确定性 PASS/FAIL 不变。
