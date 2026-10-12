# Implementation

- 扩展既有 pytest/live-browser plugin：失败时收集 URL、a11y、脱敏 DOM、失败 locator、上次成功元素指纹；未观察到基线时显式记为 `MISSING`。storage state 使用每次运行的 Fernet 临时密钥加密后才进入事件流；文本、DOM 与状态大小有界。
- 在 API 本地 pytest 与 worker 的现有 `PytestRunner` 路径接收快照。执行端用平台密钥再次加密状态，新增 `browser_sessions` 快照/密文/过期时间字段及 Alembic `0008_failure_snapshot_storage` 迁移。公开 DTO 只包含脱敏快照元数据，不包含密文。
- Locator Repair Verification 优先把解密后的 storage state 传给现有 `BrowserRuntime.create_session(storage_state=...)`，再导航至捕获 URL。记录恢复成功/失败/部分状态与原因；不自动重放浏览器动作，并列出未重放的副作用步骤。现场证据缺失时以 `INSUFFICIENT_EVIDENCE` 阻止 locator 验证。
- 同步 Python/TypeScript workflow DTO；增加 worker 传输、TTL、缺失证据、超限/无效事件及受保护页面恢复测试。
- 保留既有工作区改动；本次未提交或推送。
