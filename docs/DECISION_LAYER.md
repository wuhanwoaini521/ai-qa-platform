# Decision Layer

Decision Layer 提供与具体业务模块和模型供应方解耦的结构化选择接口。业务调用方提交一个状态对象、指令和动态候选项；服务层返回候选项、置信度、概率、模型信息及是否触发回退。当前首个实现为 Jev/System One。

## Jev 配置

设置页中的 **Jev 决策提供方** 可启用服务、配置 API Key、模型、API 地址、请求超时和最低置信度。默认关闭，模型为 `jev-1.13.0`，API 地址为 `https://api.typesafe.ai/v1/systemone`，超时 20 秒，最低置信度 0.60。连接测试使用一次真实的结构化选择请求；Playground 可验证状态、动态候选项及回退响应。

API Key 只发送到服务端，并由 Fernet 认证加密后保存在数据库。响应只含“是否已配置”状态和掩码，不含明文密钥。加密密钥由 `APP_SECRET_KEY` 派生，因此部署时必须将其设置为长期、随机且受保护的值；更改它会使之前保存的 Jev Key 无法解密，需要重新配置 Jev Key。也可在首次启动时用 `JEV_API_KEY` 及 `JEV_ENABLED`、`JEV_MODEL`、`JEV_BASE_URL`、`JEV_TIMEOUT`、`JEV_MINIMUM_CONFIDENCE` 设置环境默认值。

设置和决策接口仅限具有 `SECURITY_ADMIN` 权限的用户调用。启用后，正常选择请求会在 Jev 不可用、超时或置信度低于阈值时回退；若候选项含 `unknown` 则选择它，否则返回空选择，调用方应按未决结果处理。调用元数据写入 AI invocation 记录，不保存决策状态正文。

## 常规 AI 提供方

Settings 页面中的“常规 AI 提供方”单独配置 QA 助手、需求分析、用例生成和失败诊断使用的 Fake 或 OpenAI-compatible provider。它有独立的数据库配置记录与加密 API Key，不会读写 Jev 决策设置；首次配置前可继续使用 `.env` 中的 `QA_AI_*` 默认值。常规 AI 设置由安全管理员保存，保存后即时生效并在 API 重启时从数据库恢复。密钥加密依赖 `APP_SECRET_KEY`；轮换该值后需要重新保存 AI API Key。

## API

- `GET /api/decision/settings`：读取非敏感设置。
- `PUT /api/decision/settings`：保存设置。传入新 `api_key` 可替换；空值保留原密钥；`clear_api_key: true` 清除密钥。
- `POST /api/decision/test-connection`：用当前已保存密钥或本次传入的密钥测试真实 Jev 连接，不自动保存传入设置。
- `POST /api/decision/choose`：通用结构化选择接口。

`choose` 请求示例：

```json
{
  "name": "release_risk",
  "state": { "open_critical_bugs": 0, "coverage": 0.94 },
  "instructions": "根据发布风险选择一个结果。",
  "options": [
    { "key": "ship", "description": "允许发布" },
    { "key": "block", "description": "阻止发布" },
    { "key": "unknown", "description": "信息不足，交由人工判断" }
  ]
}
```

后续录制器、Case 执行诊断、失败分类和自动修复可依赖 `DecisionProvider` / `DecisionService`，而不直接依赖 Jev 协议。
