# Fixes During Verification

1. 首次并发工作流回归发现 SQLite `database is locked`：新加的过期清理曾对全部 browser session 执行更新。移除读写路径上的全表清理，改为只在读取当前快照且已过期时清除对应密文。随后并发用例及完整 API 回归通过。
2. 首次完整 API 回归的 3 个失败中，1 个是 workflow DTO 增加字段后 TypeScript contract 未同步；另 2 个是既有测试仍期待无现场页面证据时继续调用 Jev。同步 TypeScript 类型，并将测试改为断言 `INSUFFICIENT_EVIDENCE`（保持阻止 locator 验证的验收要求，不放宽行为）。再次完整回归全部通过。
3. 审查发现可配置 DOM 上限大于 DTO 字段上限时可能丢弃快照；plugin 现在将快照文本限制到 20,000 字符，并补充超限/无效传输的韧性测试。
