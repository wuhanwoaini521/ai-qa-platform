# 初始工程审计

审计范围：当前 `main` 工作树中的 API、Web、Worker、共享包、测试、配置、CI、架构及工作流文档。审计优先追踪真实调用关系；未证明无用的代码保留。

## 工作区与工具

- 初始分支：`main`，HEAD `3a379c5`（`fix(workspace): scope manual analysis to active failure`）。
- 初始工作区仅有用户已有修改：`mise.toml` 新增 `rtk = "latest"`。该文件不属于本任务改动，后续不会覆盖、暂存或提交。
- RTK：PATH 可用，版本 `0.51.0`；能用于 tree/read/find/rg/test 等代理命令。检查配置为默认设置；`rtk init --agent pi --dry-run` 表明可选 Pi 扩展尚未安装。本任务直接显式调用 RTK，不改 Pi 或项目集成配置。
- Ponytail：本次环境中有 Pi skill/extension 源目录，且会话已加载 Ponytail full 规则；没有 `ponytail` 可执行命令。实际使用已注入的 skill，不宣称 CLI 已安装。
- agent-browser：版本 `0.39.0` 可用；已读取此版本 core workflow。开始审计时 API、Vite、生产 Web 端口均未监听。
- `.env`、`runtime/`、已有 `.ai-runs/` 含配置/运行数据；不读取或覆盖用户数据。`.ai-runs/refactor-audit/` 起初不存在，目标报告不会覆盖既有任务记录。

## 当前结构与调用关系

- `apps/web`：React 19 / TypeScript / Vite，SPA 路由在 `src/app/routes.tsx`；页面/feature 通过 `src/api/client.ts` 的共享 API 模块访问 REST。共享错误封装在 `api/errors.ts`，SSE 帧与流处理在 `api/eventStream.ts`/`api/client.ts`。
- 浏览器 WebSocket 分布于 Recorder、Runtime Failure Workspace、Python Language Client、Debugger；它们是各自长连接/协议生命周期，不是普通 REST fetch 的重复实现。不要仅因 `new WebSocket` 分散就删除或机械合并。
- `apps/api`：FastAPI 主应用在 `app/main.py`，统一注册约 30 个 router；Router → Services → Repositories/RepositoryScope 已有边界测试。持久化、异常 envelope、授权、BrowserRuntime adapter、Task Runtime、AI/Decision/Jev 等均已有真实模块和大量测试。
- `packages/project-model` 与 API Pydantic DTO 对外暴露数据；前端 `src/types/index.ts` 手工维护相应 TS 类型。OpenAPI 由 FastAPI 提供，但目前没有发现 OpenAPI→TypeScript 生成流程；目前 architecture test 只显式对 `FailureRepairWorkflow` 做前后端字段/enum 对照。
- `RuntimeProjection` 是有意允许的只读 SQL/query 投影，架构测试明确豁免它；不能按“服务层直接 SQL”简单删除。Task Browser Executor、Failure Workflow、Quality Discovery 等文件虽大，但存在调用者与广泛测试，不属于可确认无用代码。
- `apps/worker`、`packages/qa-core`、`packages/integrations` 分别承载 Worker、QA/AI 合约与第三方适配。没有发现可安全删除的包或依赖。
- `scripts/task.py` 是跨平台 dev/setup/test/lint 的统一入口；CI 包含 SQLite 后端、Postgres 后端、Windows、前端测试/类型检查/lint/build。真实 AI/Jev acceptance 为显式 opt-in 测试。
- 文档规定的边界以实际代码为准；`docs/ROADMAP.md` 第 0 节是本任务必须遵守的安全不变量。

## 审计候选与发现

| 文件/模块 | 目前用途与依赖 | 删除/重构理由 | 风险 | 验证方式 |
|---|---|---|---|---|
| `apps/api/app/services/failure_workflow_service.py`（自动路径）、`apps/api/app/services/test_run_service.py`（失败后调度）、`packages/platform-config/platform_config/models.py`（repair AUTO 配置）、相关 tests | 失败后可按 `AUTO` 配置触发 AI/Jev 分析；在可信 proposal 生成后，workflow 会直接调用 `apply_repair()` 写回 workspace，再自动启动验证，并可能自动重试；回滚 monitor 会处理失败结果。调用路径由 TestRunService → FailureWorkflowService → FailureService → WorkspaceService。 | **确认的安全不变量冲突**：ROADMAP 0.2 明确要求每个补丁经人工批准；当前自动路径能够在没有人工确认请求时写源码。自动 apply 测试（`test_ai_resolved_locator_classification_enters_jev_and_verified_patch_pipeline`、live acceptance）把该行为当成功预期。必须改为 proposal-only 并保留人工 Apply/Verify。候选修复不能删掉 AI/Jev 分析、补丁预览、审核后写回、精确测试或回滚能力。 | **P1 / 高**：可能未经批准写入用户工作区源码。 | 新增/调整服务测试证明 `AUTO`/自动触发只生成 proposal、不改文件、不创建验证 run；显式 `apply_repair` 后才写入；对失败修复、状态机、RBAC、live acceptance 做回归。真实 Provider 测试必须 opt-in，不能把 Fake/Mock 当真实成功。 |
| `apps/web/src/types/index.ts` 与 `apps/api` DTO/OpenAPI | 手工 TS 类型服务 54 个 API-client 调用来源；FastAPI OpenAPI 暴露 schema。已有专项 DTO contract test，但未见全量生成/一致性校验。 | 这是解耦风险而非删除候选：Schema 漂移可能直到某个工作流才被发现。需要核对已有测试后补足轻量契约校验；当前不引入第二套 client/codegen，也不盲删类型。 | **中**：跨端字段漂移可能造成运行时错误。 | 检查 OpenAPI 生成选项/CI；增加实际公共 DTO 对照测试后运行 API contract tests 与 TS typecheck。 |
| `apps/web/src/api/client.ts`（约 1,553 行）、`apps/web/src/types/index.ts`（约 1,771 行） | 统一 REST DTO、请求、鉴权、Blob、stream-ticket/SSE 工具与 API 函数；大量页面依赖其导出。 | 大文件是可读性/职责风险，但不是“未使用”；若拆分必须维持统一入口和运行行为。暂不做大规模移动，以免引入 import 破坏和额外抽象。 | **中**：公共导出变化可能影响几十个调用模块。 | TS 引用搜索、前端测试、typecheck、lint、build；必要时逐项模块化。 |
| `apps/api/app/api/*`、`apps/api/app/services/*`、`apps/api/app/repositories/*` | 约 219 路由操作与 262 API Python 文件组成现有业务边界；有 architecture tests 检查 API 无 DB 依赖、服务使用 Repository、浏览器生命周期集中等。 | 不是清理候选；模块/文件名和规模不能证明冗余。需按行为和消费者审计后再改。 | **高**：公共 API、数据库、长任务/浏览器生命周期广泛受影响。 | 当前 architecture-boundary tests、API regression、OpenAPI schema、目标 workflow tests。 |
| `apps/web/src/app/routes.tsx` 中 `/tasks`、`/recorder`、`/failures`、旧 tab routes | 将旧 URL 迁移到 workflow/workspace；README/文档和书签/历史链接可能消费。 | 兼容跳转是有效消费者，不删除；检查是否有失效入口时需保留重定向契约。 | **中**：移除会破坏深链/书签。 | 路由测试、浏览器直接打开旧 URL 并验证最终路由与项目上下文。 |
| `apps/web/src/features/automation-studio/pythonLanguageClient.ts`、`useDebugSession.ts`、`RuntimeFailureWorkspace.tsx`、`pages/RecorderPage.tsx` | LSP、Debugger、Recorder 与 Runtime 各自管理 WebSocket 协议/生命周期；API client 负责相关 URL/ticket 获取。 | 不视为重复 HTTP client。可检查断线/恢复逻辑，但不统一成误用的 REST abstraction。 | **中**：长任务/调试/录制状态与认证可能中断。 | 对应 socket API tests、断连/重连测试、浏览器工作流。 |
| `.env`、`runtime/`、现存 `.ai-runs/`、`reports/` | 本地凭据、数据库、workspace、执行证据与历史交付记录。 | 用户数据/配置，不是清理候选；禁止读取秘密明文、删除或覆盖。 | **高**：凭据/用户数据损失或泄露。 | `git status` 与 `git diff`；测试只用 fixture/临时 DB/workspace。 |

## 重要差异与验收边界

- `docs/ROADMAP.md` 第 0 节要求“人工批准后才改源码”，与目前 `mode=AUTO` 中自动写回并自动复测的实现/测试预期矛盾。以规范与实际代码比对后，这是需要修复的真实违规，不是删除业务能力。
- 前后端在进程/包结构上已独立，REST/SSE/WebSocket 对外；但 TS DTO 主要为手工维护，不能仅凭目录边界宣称契约完整。
- 普通执行和失败证据已有真实运行服务代码及自动化测试；本机尚未启动应用。AI/Jev 是否可真实调用需要用当前配置安全地尝试 opt-in acceptance，配置内容不写入报告；不可用时记录客观阻塞。
- 本轮尚未进行 UI 修改；如选择 UI 修改，必须先用隔离数据打开真实页面并保存 Before 截图，再保存 After 截图、比较桌面/窄屏并操作真实控件。若不改 UI，不伪造截图前后对比。

## 当前清理判断

截至本次审计，没有确认可安全删除的函数、类、组件、API、依赖或配置。已确认的实质性问题是自动源码写回违反人审约束；优先修复此安全根因并让公开 HTTP API/前端 workflow 继续保持兼容。超大模块与手工 DTO 类型仅标记为重构/契约风险，未证明无用，保留。
