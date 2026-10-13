# 第二轮架构边界重构

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

## Original Request
重构 ai-qa-platform 前后端架构边界：前端仅通过公开 API 契约通信，统一 API Client、错误和请求状态，核对 OpenAPI 与 TypeScript 类型并清理重复封装；将 Router 业务逻辑下沉至 Service、Repository 保持纯数据访问；厘清 BrowserRuntime、TaskRuntime、Debugger、AI、Jev 职责，避免重复运行控制、生命周期管理与任务状态。

必须完成：A) 不改后端，独立调整一个核心前端组件并验证功能；B) API 契约不变，重构一个后端内部实现、不改前端并验证功能；检查 API 合约、SSE/任务状态/错误响应/重连，验证前后端可独立启动，运行相关测试，分类提交；记录本轮架构变更、依赖关系和测试证据于本目录。

## Resolved Scope
- 前端：RuntimeDetail 使用共享加载/错误状态组件；把 artifact 下载重复 HTTP 封装收敛到统一 API Client（保留兼容 API 方法）；对照运行时 DTO、OpenAPI 与生成 TypeScript 并验证一致性。
- 后端：将 Quality Discovery 创建 pytest draft 所需的 TaskCommandService 移入服务组合；由 composition root 提供 TaskRuntime 生命周期，Router 不再从另一 Router 导入 Task 服务；公开路由、响应和契约保持不变。
- 明确各运行时和状态所有权，避免目录级大重构；只对实际发现的边界改动。现有 Runtime TypeScript DTO 仍手写；本轮核对其字段与 OpenAPI 生成类型，但暂不改写该 DTO，避免扩大本轮组件改动范围；后续可将它切换为生成类型别名以防漂移。
- 保留人工批准、安全检查及用户已存在的未提交改动；不改 `.env`、`runtime/` 或现有开发服务。

## Repository / Branch / Initial Git Status
- Repository: `/Users/hans/Code/github/ai-qa-platform`
- Branch: `main...origin/main [ahead 1]`
- 初始工作区有多处 API、Web、配置、CI、测试及 `.ai-runs` 未提交改动；暂存区为空。`mise.toml` 的既有改动明确排除在本轮提交外。
- 本轮计划触碰的后端实现、对应测试、Runtime Web 类型/组件均在开始时干净；`apps/web/src/api/client.ts` 已有既存改动，仅在独立 hunk 可安全分离时才做有限修改。
