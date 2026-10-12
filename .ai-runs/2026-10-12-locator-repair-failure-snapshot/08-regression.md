# Regression

- 风险按 HIGH 处理：跨越 live plugin、API/worker runner、数据库迁移、Locator Repair 和传输 DTO，并涉及认证状态密文。
- 回归覆盖：完整 API 测试 **557 passed / 8 skipped**；qa-core live-browser telemetry **7 passed**；worker **8 passed**；web typecheck、全仓 lint、迁移测试、compileall、锁文件与 diff 检查通过。
- 关键功能证据：本地受保护页面 fixture 在失败后通过加密 `storage_state` 恢复登录并由 Playwright 验证候选；缺少现场页面证据时工作流明确报告不足且不调用 locator 决策。
- 尚未覆盖：外部真实 Jev 服务与独立人工/agent review；PostgreSQL 专用集成环境未单独启动。隔离项目解释器缺少 `cryptography` 时状态会显式不可用，不会明文降级。
- 未观察到本次改动导致的其他 API/worker 回归。
