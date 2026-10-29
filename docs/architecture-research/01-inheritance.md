# 研究成果继承矩阵

基准：当前 `main` @ `d66c531`（2026-10-29）；研究分支 `research/autonomous-rd-2026-10-28` @ `645bc20`。
研究分支基于 `origin/main` 的 `245c00c`，而 `main` 已比该基点多 45 笔提交——**这是所有「过时」项的根因**。

处置分类：

- **继承**：结论仍然成立，可直接复用。
- **需验证**：方向成立，但版本/环境/数字需要重新取证。
- **过时**：与当前代码或事实冲突，不得再引用为现状。
- **未完成**：当时就没做完，本轮也未完成。
- **不一致**：研究分支的记录与当前 `main` 的实现形态不同。

---

## 1. 可以直接继承

| ID | 结论 | 来源 | 当前验证 |
|---|---|---|---|
| I-1 | ROADMAP §0 六条不变量（AI 不判定、人工批准、确定性、预览后写入、无无人值守循环、单一 Runtime/Agent/Provider） | `docs/ROADMAP.md:9-17` | 当前文件逐条核对一致 |
| I-2 | 现有分层（router → service → repository → ORM）与边界测试约束 | `current-state.md` §2；`apps/api/tests/test_architecture_boundaries.py:24-112` | 边界测试仍在，规则未变 |
| I-3 | `TaskRuntimeService` 是组合入口，`TaskSchedulerService` 管 claims/lease/恢复 | `current-state.md` §4；`task_runtime_service.py:19-57` | 源码一致 |
| I-4 | `BrowserRuntime` 是唯一 Playwright 生命周期所有者，端口不含 Playwright 导入 | `current-state.md` §5；`ports/browser_runtime.py:1-6,46` | 源码一致 |
| I-5 | Pytest 退出码是测试判定唯一权威 | `current-state.md` §4；`test_run_service.py:1149-1161` | 源码一致 |
| I-6 | ADR-002：保留现有所有权，DEFER 框架集成 | `engineering-knowledge/decisions/ADR-002` | 结论仍成立 |
| I-7 | 架构辩论结论：A 为当前基线，B 条件性，C 无证据支持 | `architecture-debate-2026-10-28.md` | 结论仍成立 |
| I-8 | 迁移原则：expand-only、双读、特性开关、可回滚 | `migration-plan.md` Principles / Data migration procedure | 原则仍适用 |
| I-9 | 框架元数据：LangGraph 1.2.18 MIT、Browser Use 0.13.14 MIT、Skyvern v1.0.56 AGPL-3.0 | `framework-p0-verification-2026-10-28.md` | 来源已核对；决策前需刷新 |
| I-10 | 本地 Discovery 恢复修复：状态条件保护 + 状态/事件同事务 + 提交后通知 | 研究分支代码；当前工作区实现 | SQLite 15 项、PG16 19 项定向测试通过（本会话） |
| I-11 | 质量门概念（证据标准、BLOCKED 不等于通过、AI 边界） | `.pi/team/QUALITY_GATES.md` | 已裁剪并入 `docs/QUALITY_GATES.md` |

---

## 2. 需要验证后引用

| ID | 结论 | 为什么需要验证 | 建议验证方式 |
|---|---|---|---|
| V-1 | 三个候选框架的版本/许可证/依赖上限 | 元数据会变化；Skyvern 的 FastAPI `<0.137` 与本项目 0.141.1 冲突 | 决策前用官方 release/tag 重新核对，记录日期 |
| V-2 | 「PostgreSQL 16 通道 BLOCKED」 | 本会话已用隔离 PG16 跑通 19 项定向测试 | 对具体声明重新取证；全量与多进程仍未跑 |
| V-3 | PoC 的 8 个测试结果（6 passed / 8 passed） | 研究文档记录的是历史运行 | 重新执行同一命令，记录当前 SHA 与耗时 |
| V-4 | Browser Use 与 Playwright 1.62.0 的兼容性 | 研究只核对了顶层 manifest，未解析传递依赖 | 一次性隔离环境做依赖解析；不安装到项目 |
| V-5 | 「Task Runtime 无自动重试」 | 当时基于源码与测试的推断 | 复核 `task_execution_orchestrator.py` 的异常分类 |
| V-6 | 「Discovery 事件只是有界 JSON 数组」 | 当前实现有 `discovery_evidence` 表与 live hub | 核对 `QualityDiscoveryRunORM.result` 与 `DiscoveryEvidenceORM` 的职责划分 |
| V-7 | 服务模块数量（86 个等） | 计数随提交变化 | 需要时重新统计，不作为质量结论 |

---

## 3. 已过时（不得再作为现状引用）

| ID | 旧结论 | 当前事实 | 证据 |
|---|---|---|---|
| O-1 | 「Workflow Canvas 只是观察器，没有工作流编排能力；无 React Flow 等编辑器依赖」 | 已有 Workflow 定义/版本/发布/编译/启动，并由 Task Runtime 执行 | `persistence/models.py:822-846`；`workflow_definition_service.py:208-343`；`api/workflow_definitions.py:163-211`；迁移 `0019`、`0023` |
| O-2 | 「Alembic 迁移链 0001…0015」 | 当前 head 为 `0023_workflow_task_execution` | `apps/api/alembic/versions/` |
| O-3 | 「Python 3.13.15 / uv 0.12.17」 | 当前 Python 3.13.16 / uv 0.13.1 | 本会话环境检查 |
| O-4 | 「PostgreSQL 验证完全不可用」 | Docker 可用，已跑隔离 PG16 | 本会话 `docker run postgres:16` + 19 passed |
| O-5 | 研究分支的 Discovery 恢复实现（移除 600 秒陈旧判定） | 当前实现保留 600 秒陈旧判定，避免误暂停仍活跃的 run | `quality_discovery_service.py:887-912` |
| O-6 | 研究分支的 `.pi/team`、`.pi/agents` 可被直接使用 | 当前 `main` 没有 `.pi/`；角色已改用 Claude Subagents 格式 | `git ls-tree`；`.claude/agents/` |

---

## 4. 尚未完成

| ID | 缺口 | 状态 | 影响 |
|---|---|---|---|
| U-1 | 跨域事件/证据统一契约（候选 B 的核心） | 仅设计，未实现 | 跨 Task/Run/Discovery 的回放与溯源仍需适配器 |
| U-2 | Browser Use / Skyvern 同任务对比实验 | 未运行 | 无法判断是否需要外部浏览器 Agent |
| U-3 | 多 API 实例所有权（TestRun / Discovery） | 未实现 | API 横向扩容不安全 |
| U-4 | 真实 provider 的人工批准闭环（QA-003） | BLOCKED | AI 修复链路的真实成功路径未验收 |
| U-5 | Skyvern 法务评估 | 未开始 | AGPL 约束未定 |
| U-6 | 不可信 Pytest 代码的 OS/容器隔离威胁模型 | 未开始 | 多租户部署风险 |
| U-7 | 成本/延迟/资源基线 | 未测量 | 无法量化重构收益 |

---

## 5. 与当前 main 不一致之处（需在阅读旧文档时注意）

1. **Workflow Studio 已从「只读投影」演变为「可发布执行」**：`WorkflowDefinitionORM` → `WorkflowDefinitionVersionORM` → `compile_plan` → `TaskRuntimeService.commands.create_workflow` → `TaskORM`。旧文档对此的描述已失效。
2. **迁移链已推进到 `0023`**，包含 `0020_task_lease`、`0022_task_cancel_request`、`0023_workflow_task_execution`。旧文档的租约/取消描述可能不完整。
3. **Discovery 恢复实现与分支不同**：分支移除了陈旧判定，主线保留。
4. **治理文件位置不同**：研究分支用 `.pi/team/*`，当前主线用 `CLAUDE.md` + `docs/QUALITY_GATES.md` + `.claude/agents/*`。
5. **旧文档中的测试计数与耗时不可复用**：代码已前进 45 笔提交。

---

## 继承结论

- 旧研究的**方向性结论仍然有效**：不要整体替换架构，不要引入第二套 Runtime。
- 旧研究的**事实性描述必须按当前代码重读**，尤其是 Workflow、迁移链、版本号和多实例状态。
- 旧研究的**未完成项**没有因为时间推移而完成：U-1 至 U-7 仍然成立。
- 本轮新增的结论全部基于当前 `main` 源码，见 `02-current-architecture.md`。
