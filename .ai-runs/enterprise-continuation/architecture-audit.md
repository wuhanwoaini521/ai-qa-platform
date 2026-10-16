# Architecture Audit — 风险导向全仓审查

审查方式：结构扫描 + 分层依赖检查 + 不变量核对（非仅看本轮 71 个文件）。
数字均为在本机对当前 `d8a2eef` + 本轮修复代码实际统计得到。

## 1. 分层与依赖

| 层 | 位置 | 文件数 | 结果 |
| --- | --- | --- | --- |
| HTTP / 契约 | `apps/api/app/api/` | 39 | 只做参数校验与编排，无业务规则 |
| 应用服务 | `apps/api/app/services/` | 85 | **不 import fastapi**（已验证 0 命中） |
| 仓储 | `apps/api/app/repositories/` | 35 | **不 import fastapi**（已验证 0 命中） |
| 端口 / 适配器 | `apps/api/app/ports/` (6)、`apps/api/app/adapters/` | — | BrowserRuntime / DatabaseHealth / RepositoryScope / UnitOfWork 均为端口 |
| 组合根 | `apps/api/app/container.py` | — | 依赖注入集中在此，路由通过 `Depends(get_*)` 获取 |

**结论：分层健康。** 业务逻辑没有回耦合进 React 页面，也没有把 FastAPI 依赖下沉到服务层。
前端通过 `apps/web/src/api/client.ts` 单一客户端访问 REST，OpenAPI 由 `scripts/export_openapi.py` 导出并由 lint 强制同步。

## 2. 架构不变量核对（AGENTS.md 第 0 节 / ROADMAP）

| 不变量 | 核对方式 | 结果 |
| --- | --- | --- |
| 只有一套 Runtime / Agent / Provider | `AIProviderRegistry` 仅一处（`packages/qa-core/qa_core/ai/registry.py:14`）；BrowserRuntime 仅一处实现（`apps/api/app/adapters/playwright/browser_runtime.py:111`） | **保持** |
| AI 不决定 PASS/FAIL | 决策结果由 `DecisionService` / Jev provider 输出，执行结论来自 `Run`/`TestResult` 状态机；未发现 AI 输出直接写 PASS/FAIL 的路径 | **保持** |
| 不经人工批准不改代码 | 修复链路要求 `APPLY` 动作 + `allowed_actions` 校验（`failure_workflow_service` / `locator_repair_state_machine`） | **保持**（链路 B 验收覆盖） |
| 外部写入先预览 | Studio 保存走工作区文件 API；PR / Jira / TestRail 集成有独立审计表 | **保持**（静态核对） |
| 无无人值守循环 | `quality_discovery_execution` 有显式状态机与进度；未发现无界重试 | **保持**（静态核对） |

## 3. 授权模型

`apps/api/app/api/authz.py` 提供两级控制：

1. **应用级**：`authorize_request`（`authz.py:214`）挂在主路由
   `apps/api/app/main.py:171` 的 `dependencies=` 上，对每个非公开请求
   （`is_public_path`）做完认证后按中央策略表 `required_permission(method, path)` 校验。
2. **路由级**：`require_permission(Permission.X)`（`authz.py:250`）用于需要更细粒度控制的端点。

39 个 router 中 14 个显式声明了权限依赖，其余由中央策略表覆盖 —— **这是有意的设计，不是漏洞**；
`test_authorization_rbac.py` 覆盖策略表。

审计能力已存在且是真实后端：`apps/api/app/api/audit.py`（`/audit/integrations`、`/audit/security`）
+ `apps/api/app/repositories/security_audit_repo.py`。

> 因此「RBAC / 审计日志」**不应再新建第二套**，后续如需扩展应扩展现有策略表与审计表。

## 4. 主要架构风险（未修复，记录在案）

| 级别 | 风险 | 位置 | 说明 |
| --- | --- | --- | --- |
| P2 | Studio 前端 chunk 4.03 MB | `apps/web/src/features/automation-studio/monaco.ts:1`（`import * as monaco from 'monaco-editor'` 拉入全部语言） | 构建产物告警；也是构建内存峰值的主要来源。改为按需引入 `esm/vs/editor/editor.api` + 需要的语言可同时降低包体与构建内存，但对 Studio 有回归风险，需配浏览器验收 |
| P2 | 33 个 service 文件直接使用 `session.execute/text(` | `apps/api/app/services/` | 部分查询绕过仓储层，一致性由测试保障；长期应收敛到仓储 |
| P3 | 健康探针预算与各 provider 请求超时的对齐是逐组件手写的 | `platform_health_service._probe_timeouts` | 本轮已修 `ai`（见 implementation-log），`jev`/`browser` 仍为常量 |
| P3 | 无远程 worker，`worker` 组件恒为 `LOCAL_EXECUTION_AVAILABLE` | `platform_health_service` | 分布式执行链路未验证 |

## 5. 结论

架构评分：**健康（B+）**。分层清晰、依赖方向正确、不变量保持、授权与审计是真实后端实现。
主要技术债集中在 Studio 打包体积与少量绕过仓储的查询，均非阻断项。
