# Request

> 将 LocatorRepair 从 failure workflow 的 trace 字段提升为强类型持久化状态机，并提供漏斗指标：新增 LocatorRepair 表及可升降级的 Alembic 迁移，兼容旧数据；状态转换集中在一个类中，并测试非法转换；修复审计 P2 第 4 条，GET 读取路径不得写状态；新增 `GET /api/quality/repair-funnel`，返回各阶段计数及阻断原因分布；漏斗数字须能与 AI invocation 记录对账。

- Task: new persistence/API feature plus read-path correctness fix.
- Risk: HIGH.
- Repository: `/Users/hans/Code/github/ai-qa-platform`, branch `main` tracking `origin/main`.
- Initial working tree contained many pre-existing uncommitted changes, including previous Locator Repair snapshot and Jev signal work. Preserve them; do not stage, commit, or push.
