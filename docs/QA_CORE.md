# QA Core 领域边界

`packages/qa-core` 提供不依赖 FastAPI 和数据库的领域模型、执行适配和 AI 协议；应用服务负责身份、持久化和用户审批。

| 模块 | 职责 |
|---|---|
| execution | PytestRunner、执行模型、同步 Playwright live plugin |
| onboarding | 项目与运行时合约、collection、共享 pytest JSON report plugin |
| failure | 当前异常分类、脱敏、FailureEvidenceBundle |
| healing | 候选排序与只提案、不写文件的 Locator 修复 |
| ai | Provider/Registry、结构化请求、预算、上下文、事件、动作风险 |
| author | 知识约束的生成、规格与 AST 校验 |
| orchestrator | 组合已有领域能力；不重复维护 UI、工作流或数据库状态 |
| prompts | 已注册且有版本的 prompt |

旧根级 `contracts.py`、`fake_adapters.py` 及只使用它们的旧模拟测试已删除。真实模块使用领域合约，禁止重新隐式引入旧 Fake QA Runner。FakeAIProvider 保留用于明确模拟，Usage 记录真实来源。
