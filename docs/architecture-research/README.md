# Architecture Research & Refactor Design

Status: `[M1/M2 PARTIAL — SQLite]` · Started 2026-10-29 · Baseline commit `d66c531` · **Architecture Gate: NOT PASSED (M1/M2 可按 PARTIAL 收口；M3 实现仍需逐项批准)**

本目录是重构研究的**唯一新增产物**。它不修改产品代码、不新增迁移、不引入框架依赖。
所有结论都标注证据来源；无法验证的内容标 `UNKNOWN` 或 `BLOCKED`，不写成结论。

## 文档索引

| 文件 | 内容 | 状态 |
|---|---|---|
| [01-inheritance.md](01-inheritance.md) | 研究成果继承矩阵：可继承 / 需验证 / 已过时 / 未完成 / 与 main 不一致 | 完成 |
| [02-current-architecture.md](02-current-architecture.md) | 真实调用链、状态流、缺陷与代码证据 | 完成 |
| [03-framework-learnings.md](03-framework-learnings.md) | LangGraph / Browser Use / Skyvern 机制学习与映射 | 完成 |
| [04-target-architecture.md](04-target-architecture.md) | A/B/C 方案对比与推荐目标架构 | 完成 |
| [05-refactor-roadmap.md](05-refactor-roadmap.md) | 7 个可独立验收的里程碑与 GO/NO-GO | 完成 |
| [06-review-gate.md](06-review-gate.md) | 独立架构评审、QA 验收矩阵、Architecture Gate 结论 | 完成 |
| [07-m1-baseline.md](07-m1-baseline.md) | M1 基线：状态映射、事件语义、39 个工具副作用草案、测试矩阵 | 完成 |
| [08-m2-terminal-atomicity.md](08-m2-terminal-atomicity.md) | M2：Discovery 终态与事件单事务；TestRun 原子性复核与验收 | 完成（SQLite）/ PG16 BLOCKED |
| [09-final-acceptance.md](09-final-acceptance.md) | M1/M2 最终质量门：判定、全量测试、E2E 归因、评审结论、关闭条件 | 完成 |
| [10-s0-stabilization.md](10-s0-stabilization.md) | S0 风险复核、缺陷预览、PG16 计划、变更边界与 M3 就绪建议 | 分析完成；产品修复待审批 |

## 研究来源

| 来源 | 类型 | 使用方式 |
|---|---|---|
| 当前 `main` 源码（`d66c531`） | 一手 | 所有架构发现必须能指向文件与行号 |
| `research/autonomous-rd-2026-10-28`（`645bc20`） | 一手历史研究 | 继承、修正或标注过时 |
| LangGraph / Browser Use / Skyvern 官方文档与源码 | 一手外部 | 只学机制，不安装、不运行 |
| `docs/ROADMAP.md` §0、`docs/QUALITY_GATES.md` | 项目规范 | 判定与边界依据 |

## 判定口径

遵循 `docs/QUALITY_GATES.md`：

- 单项检查：`PASS` / `FAIL` / `BLOCKED` / `UNKNOWN` / `N/A`
- 交付结论：`PASS` / `PARTIAL` / `FAIL`
- 就绪结论：允许 `BLOCKED`

本目录中的「已验证」只表示**源代码层面确认**，不等于运行时验证。
运行时证据必须附命令、环境、退出码；没有执行过的项目一律写 `UNKNOWN` 或 `BLOCKED`。

## 本轮不做什么

- 不修改产品代码、测试、迁移或 API。
- 不安装 LangGraph / Browser Use / Skyvern，不运行它们。
- 不做跨域 schema 迁移，不做事件/证据契约的落地实现。
- 不重做 UI；Graphite 桌面方向保持不变。
- 不提交、不推送、不合并。

## 下一步

本目录完成后停在 Architecture Gate，等待人工批准。批准后才进入
`05-refactor-roadmap.md` 的 M1。
