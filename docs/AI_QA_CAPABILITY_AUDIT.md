# AI QA 能力盘点（2026-10-02）

当前能力地图、真实 AI/Jev 验收、架构清理、测试和未验证范围见 [升级与清理验收](ARCHITECTURE_CLEANUP_ACCEPTANCE.md)。本文替代此前 LSP 为 MISSING 的过时盘点。

| 能力 | 当前实现与边界 |
|---|---|
| Python 编辑与语言服务 | Monaco + basedpyright；真实补全、Hover、定义/引用、语义诊断；限本工作区 |
| QA Assistant | ProductionQAOrchestrator 与共享 AI 执行治理；版本化 prompt、有界上下文 |
| AI Test Copilot | Tasks：Case、Python/API 或 URL → 生成 → 审批 → 落盘 → 真实运行 → 绑定 |
| 失败分析 | 当前异常分类、统一证据、真实 AI；阶段、耗时、来源与历史；支持 UI/API/Python |
| Locator / Healing | 观察候选 → Jev/本地选择 → Playwright 验证 → 人工应用 → 原失败用例精确复测 |
| Recorder | Studio 浏览器模式；原始/优化稿独立；重新生成替换当前稿；实际运行前标记待验证 |
| Browser Agent | 有界安全观察；危险动作独立阻断；可观察文本条件有明确边界 |
| Live Execution | 实时画面、步骤、console、network、AI；细粒度 telemetry 限同步 Playwright |
| Settings / Usage | 真实 Provider 状态、预算、调用记录；未知 tokens 与 fallback 明示 |
| Fake | 显式模拟与测试；不能冒充真实 AI 或已验证代码 |

代码存在、单元回归和真实外部服务验收是不同证据。PostgreSQL、异步 Playwright telemetry、优化稿跨会话持久化等限制详见验收报告。
