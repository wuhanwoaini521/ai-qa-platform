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

`apps/api/app/api/authz.py` 有全局角色权限和路由策略：`authorize_request` 在 `apps/api/app/main.py:171` 应用，
`required_permission(method,path)` 匹配路径/方法；`require_permission(Permission.X)` 提供路由级细化。
这些控制只回答“该用户角色能否执行这类动作”，不回答“这个项目/资源是否属于该用户”。

**重要缺口（跨项目隔离未实现）**：`ProjectORM` 无 owner/team 关系；`User` 只有全局 role；`TeamMemberORM` 只关联 team/user，
没有 project 关联或 team→project 权限映射（`apps/api/app/persistence/models.py:100-121,624-655`；
`packages/project-model/project_model/models.py:1381-1480`）。因此中央规则中的 `PROJECT_READ`、`RUN_EXECUTE` 等权限对所有项目相同。
部分服务主动核对相关项目 ID，但不能由此推断所有 path/query/body/opaque-ID 资源都经过同样验证。
`runs/{run_id}`、workspace files, failures/repair, tasks/artifacts, discovery-run IDs, streams 等必须先解析拥有项目，不能只看 URL 的 `project_id`。
D5 refresh 路由单独限制为 run requester/Admin，但这不等于系统级 project ACL。

审计能力是存在的真实后端（`apps/api/app/api/audit.py` 与 `apps/api/app/repositories/security_audit_repo.py`），但当前审计查询主要按 actor/action，
尚未形成以 project_id 为核心的访问审计。

> 不应新建第二套全局 RBAC。安全实现应扩展现有策略：先定义 project/team membership、角色映射与 legacy project 兼容规则，再集中解析/校验资源所属项目，涵盖 project-id 和 opaque-ID 路由、列表查询、websocket/stream、写请求的关联 ID 一致性与后台任务。未完成该完整闭环前，不要只给少数路由加 ACL 并声称隔离完成。

## 4. 主要架构风险（未修复，记录在案）

| 级别 | 风险 | 位置 | 说明 |
| --- | --- | --- | --- |
| P0（企业多项目部署 blocker） | 无 project/resource-level ACL | `ProjectORM`, `User`, `TeamMemberORM`, central authz | 全局角色权限不与项目绑定；query/list 与 opaque resource ID 路由缺少统一 owner resolution。需要跨 API 完整设计与迁移，不能靠单路由补丁假装隔离 |
| P2 | Studio 前端 chunk 4.03 MB | `apps/web/src/features/automation-studio/monaco.ts:1`（`import * as monaco from 'monaco-editor'` 拉入全部语言） | 构建产物告警；也是构建内存峰值的主要来源。改为按需引入 `esm/vs/editor/editor.api` + 需要的语言可同时降低包体与构建内存，但对 Studio 有回归风险，需配浏览器验收 |
| P2 | 33 个 service 文件直接使用 `session.execute/text(` | `apps/api/app/services/` | 部分查询绕过仓储层，一致性由测试保障；长期应收敛到仓储 |
| P3 | 健康探针预算与各 provider 请求超时的对齐是逐组件手写的 | `platform_health_service._probe_timeouts` | 本轮已修 `ai`（见 implementation-log），`jev`/`browser` 仍为常量 |
| P3 | 无远程 worker，`worker` 组件恒为 `LOCAL_EXECUTION_AVAILABLE` | `platform_health_service` | 分布式执行链路未验证 |

## 5. 结论

架构评分：分层/运行时边界 **B+**；企业安全隔离 **PARTIAL / P0 阻断**。Runtime 与层次边界健康，但当前 RBAC 是全局角色模型，缺 project membership/owner resolution；跨项目 API 数据隔离不能宣称完成。
主要后续工作：完整 project ACL 与 legacy migration/backward-compat policy；其次 Studio 打包体积和少量绕过仓储的查询。
