# S0 收口与下一阶段准备

日期：2026-10-29 · HEAD `0c0ab204960ab725958d6f97c6fcb82fc6a88609` · 分支 `main`

> 本文件是分析、设计和验证记录。没有修改产品代码。当前工作树中已有 M1/M2 产品改动与未跟踪内容，以下建议修复均须单独审批。

## 1. S0 结论与风险优先级

| 优先级 | 项目 | 分类 | 证据 / 当前状态 | 处置建议 |
|---|---|---|---|---|
| P0 | Automation Studio 缺失模块导致前端 typecheck/build 失败 | BLOCKER（前端可构建门） | `pnpm --dir apps/web typecheck` exit 2，TS2307；该 import 从 `245c00c` 起存在，模块未在该提交、当前树或已检索 git 历史中出现 | 独立前端修复；先查已有工作区文件命名/规则，再补最小 helper 和单元测试；不与 M2 合并 |
| P1 | Write/Repair 工作区 mode-nav 被遮挡 | MAJOR（桌面核心交互） | 基线 `d66c531` 和当前树复现；1280×720、1280×800、1440×900、1920×1080 的 DOM 探针均 `tabClickable=false`；Trace/PNG/HTML 已保留 | 独立 UI 修复；使用四视口矩阵，加上 1280×720 的点击回归 |
| P1 | Discovery `_update` 接收未知值并静默丢弃持久化 | MAJOR | 真实 SQLite 探针显示拼错的 `finishd_at` 被 setattr 到 ORM 实例，flush/commit 成功但 DB `finished_at` 仍 NULL | 在任何依赖该 helper 的新里程碑前做显式字段契约；最小精确预览见 §2 |
| P1 | M2 全量唯一失败属于上述既有前端缺陷 | BLOCKED/既有缺陷 | 最终 API 全量 923 collected：910 passed / 1 failed / 12 skipped，exit 1；失败在基线可复现 | 不重跑全量，按用户决定保留；mode-nav 单列缺陷 |
| P1 | PostgreSQL 16 当前不可用 | BLOCKED | WSL Docker CLI 目标不存在、Docker Desktop stopped、无 PG 服务；未安装工具 | 用现存 CI `backend-postgres` job；未有 CI 结果前所有结论保持 SQLite-only |
| P2 | Vite `_free_port()` 端口释放后的 TOCTOU | MINOR（测试稳定性） | 首轮全量真实日志显示 Vite `--strictPort` 启动冲突；申请端口后关闭 listener，存在竞态 | 把 launcher 改为绑定 socket 生命周期持有至进程启动并传递 fd，或让 Vite 选端口并读取实际监听端口；优先方案须适配 Vite/当前 server fixture。不得用额外 wait 或重试掩盖 |
| P2 | `version_id_col` 为状态检查和写入提供 DB 级冲突检测 | MINOR（实现机制关键） | 两个真实 SQLite session 同读同版本，第一笔提交，第二笔抛 `StaleDataError`；运行时定义 `version_id_col=version` | 加一条 ORM 版本检查锁定测试，并覆盖服务层旧状态条件失败不广播；PG16 再验证 |
| P2 | 终态持久化发出两次 UPDATE | MINOR（效率/可读性） | 实测每次 repo update 推进 version；现状同事务两次 ORM UPDATE，version 从 1→2→3 | 可把事件合并入第一次更新，减少写次数；先确认 SQLAlchemy flush/version 语义与失败回滚不变，非 M3 阻断 |
| P2 | 单进程锁外的跨进程并发 | BLOCKED（范围边界） | 并发用例持有进程内 asyncio lock；ORM versioning 能拒绝同版本过期写，但无多进程 Discovery 场景验证 | 不提前加 lease/fencing；M7 才做跨进程验证。本轮不能声称多实例安全 |
| P3 | M2 测试对 TestRun 错误日志未覆盖 | MINOR | TestRun 验证提交先于广播及终态持久化；未执行 worker 外层转换的日志断言 | 如验收要求仍保留，补最窄测试；不影响 DB 原子性结论 |
| P3 | 收尾状态守卫失败时依赖恢复路径 | MINOR | `_finish_locked` 在计算期间状态变化会放弃旧写入，返回不广播 | 保留当前保守语义；未来验证可观测性和恢复效果，不因收口而放宽守卫 |

### 1.1 四项 Architecture Critic 复核

1. **未知字段静默吞掉：MAJOR，已实证。** `.ai-runs/2026-10-29-arch-refactor-m1-m2/diagnostics/s0_repo_probe.py` 在隔离临时 SQLite 库中调用 `repo.update(..., finishd_at=...)`。结果：调用成功、实例拥有临时属性、映射列为空、数据库 `finished_at` 仍 NULL。`_update` 随后会把未知关键字传入 repository，因此它不会报错，也不会持久化。
2. **版本列并发保护：机制成立，覆盖仍有缺口（MINOR）。** 同一探针让两个 AsyncSession 读取同版本；第一笔 RUNNING 提交后，第二笔 PAUSED flush 得到 `StaleDataError: UPDATE ... expected to update 1 row(s); 0 were matched`，最终数据库保持 RUNNING。该证据证明 SQLAlchemy ORM 更新的乐观版本冲突，不证明所有状态检查都在 SQL WHERE 子句，也不证明跨进程恢复全流程或 PostgreSQL 行为。
3. **两次 UPDATE：确认属实（MINOR）。** 终态与事件目前在同一事务，但 `_update` 先 flush 状态，再更新 result/events 并再次 flush，版本递增两次。事务原子性不依赖两次 SQL UPDATE；可把事件追加应用于内存中的 row，再单次 flush。改动仍需比较失败注入和 SQL 语句/版本行为。
4. **进程内锁之外：仍未覆盖（对多实例为 MAJOR；本阶段标 BLOCKED）。** 现有测试的 asyncio lock 仅为服务实例内锁；版本列避免同版本 ORM 写入静默覆盖，但目前没有真实双进程 Discovery 收尾/恢复测试，也没有 PG16 证据。没有必要为 M3 预建租约系统；按路线留到 M7。

### 1.2 `_update` 静态字段契约预览（未实施）

建议把通用 `**values` 收敛为 ORM 可更新字段的 `TypedDict` 或显式关键字签名，且将控制参数与持久化字段分开。最低限度在 repository 中拒绝非映射列名；服务入口需要一个测试证明拼错字段会立即报错、且不写库。另应让终态路径要求 `persisted_event`，或提供专用终态写函数，防止“终态必有事件”只靠调用者惯例。

预期行为差异：未知字段从成功但未持久化变为 `TypeError`/明确 `ValueError`；无 schema 变化。精确签名需要先盘点所有 4 个调用点和动态字段类型再选定；本报告不修改代码，也不把方案伪装成已获批准。

## 2. M2 未完成项与修复预览

### 2.1 未完成项

- PostgreSQL 16 整体与迁移验证：BLOCKED；SQLite 证据不能替代 PG16。
- TestRun 广播失败的 worker 外层日志归因：PARTIAL。
- 跨进程 Discovery 收尾/恢复竞争与多副本安全：未覆盖，留待 M7；M2 不宣称通过。
- 更新 API 当前允许未知属性：已确认缺陷，待单独批准修复。
- 两次 UPDATE：性能/版本跳数问题，不影响同事务原子性；可选最小化。
- 最终全量测试 1 个基线 UI 缺陷、12 skips，退出码 1；用户已指示本阶段不要求立即全量重跑。

### 2.2 `_free_port()` 精确设计预览

现函数绑定 `127.0.0.1:0`、取端口后关闭 socket，Vite 稍后以 `--strictPort` 竞争同一端口。预期最小改法是在 `test_discovery_coverage_e2e.py` 的测试启动器里由 Vite 自己取得空闲端口（移除 `--strictPort`），再从 Vite 输出或 HTTP ready URL 获得实际端口；API 的 uvicorn 端口也要避免释放窗口，宜使用绑定 socket 的 uvicorn socket 接口。需要先确认 Windows/macOS/Linux 一致支持的方式，并测试端口冲突时错误可诊断。不要用 sleep、点击重试或降低断言作为修复。

影响面：发现 E2E、`test_studio_debug_ui_live.py` 和 worker 集成测试都实现相同 helper；不应机械一次改所有用例。优先修复有真实失败证据的 discovery E2E，其他 helper 只有各自需要时再改。

### 2.3 12 个 skip 的归因

最终日志没有 `-rs`，不能从该日志逐项恢复理由。对当前最终代码上的可定位 skip 点做了安全定向复跑（只运行 skip-prone 文件/用例）得到：

- 6 个 PG 专项：`test_postgres_integration.py` 3 个、`test_postgres_migrations.py` 1 个、`test_runs_and_failures.py` 1 个、`test_task_cancel_fencing.py` 1 个。理由统一为缺少 `AI_QA_TEST_DATABASE_URL`。这 6 个计数与完整套件一致。
- 2 个真实 Jev/Provider acceptance：需要 `AI_QA_RUN_LIVE_JEV_ACCEPTANCE=1` 与 `AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1`；不是本地确定性测试失败。
- 2 个 enterprise journey：需要 `AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1`。
- 1 个真实浏览器 agent acceptance：需要 `AI_QA_LIVE_BROWSER_E2E=1` 以及实际 AI/Jev provider 调用。
- 1 个真实 Studio/debugpy acceptance：需要 `AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1`。

确定性定向复跑证据：临时相关用例集 16 passed / 9 skipped，其中 9 个正是本次点名的 5 个 gated acceptance + 4 个 PG 专项文件；另一个 3 个用例集 5 passed / 1 skipped，唯一 skip 为 Studio gate。全量 12 skip 因此归因完整（6 PG + 6 opt-in live）。这不把 live acceptance 说成通过；它们未运行。

测试快照：全量最终日志采集 923 项，退出码 1；新加用例已纳入。全量运行后没有测试文件变更；随后仅执行与 12 skip 归因相关的定向只读 pytest 命令。全量未运行 Ruff/format，因此仅已有交接记录中的历史专项 Ruff 结果有效，不能称当前快照全仓 lint 通过。

## 3. 前端独立缺陷记录

### 3.1 Workspace mode-nav 被遮挡（已复现）

- 根因：`apps/web/src/index.css` 将 workspace shell 定为三行 `auto auto minmax(0, 1fr)`；`WorkspacePage.tsx` 在 Write/Repair 模式渲染四个直接子项（header、stage-nav、standalone mode-nav、grid），导航落入第三行并被压到 0–5.8px。网格头部覆盖 tab 命中区域。
- 模式范围：`workspaceModeForContext` 将 `view=cases/code` 映射 Write、`stage=failure` 映射 Repair；二者 `isWorkbenchHeader=false`，mode-nav 是独立子项。`debug/explore` 将导航放在 header 中，不走这个四子项情形。
- 基线矩阵：1280×720、1280×800、1440×900 的 rows 为 `68.6875px 72px 0px <grid>`；1920×1080 为 `68.6875px 36px 5.8125px 867.5px`。四种尺寸 `elementFromPoint` 命中 `.workspace-main-heading`，`tabClickable=false`。
- 唯一修改在隔离基线 worktree 中做过的候选 CSS 试验：将行模板增为 `auto auto auto minmax(0, 1fr)` 后，目标点击成功，测试继续到另一个缺陷；主工作区 CSS 未修改。
- 修复验收：至少覆盖 1280×720、1280×800、1440×900、1920×1080；保留 1280×720 和目标 E2E 点击证据；验证 Write/Repair 与 Debug/Explore 四模式导航/布局。不得使用 force click 或任意等待。

**候选单行 diff（预览，未应用）：**

```diff
-  grid-template-rows: auto auto minmax(0, 1fr);
+  grid-template-rows: auto auto auto minmax(0, 1fr);
```

建议缺陷级别 P1；独立于后端 M2 分支提交。

### 3.2 Automation Studio 缺失 helper（已证实）

`AutomationStudioPage.tsx` 从 `245c00c` 加入 `defaultWorkspaceTestFile` import 和调用；对应 `defaultWorkspaceTestFile.ts` 在该提交、HEAD 和已检查的 git 历史中都不存在。当前实际命令：`pnpm --dir apps/web typecheck`，exit 2，错误为 `TS2307: Cannot find module './defaultWorkspaceTestFile'`。缺陷早于 M1/M2；当前可能阻塞前端 typecheck 和 CI。

最小修复设计：从 `useWorkspaceFiles` 输出的 `string[]` 选取默认测试路径，优先使用 `tests/` 下 `test_*.py`，其次按稳定排序选择全路径中符合项目既有测试规则的 Python 测试文件；无候选返回 `null`。候选实现应匹配文件树的 `test_` / `_test.py` 约定并加单元测试（排序确定、无候选、非测试 Python 文件排除）。不得在本报告中补文件或修改产品代码。修复后至少跑 typecheck、Studio 定向测试和前端 CI 等价构建。

## 4. PostgreSQL 16 独立计划

本地仍为 **BLOCKED**：没有可用 Docker Engine、PG server 或 `AI_QA_TEST_DATABASE_URL`；未安装/启用任何组件。现存 `.github/workflows/ci.yml` 的 `backend-postgres` job 明确使用 `postgres:16`、独立 `aiqa_test` 数据库和 `uv run pytest apps/api -v`，可作为无需本机新增数据库的验证通道。

建议步骤：

1. 通过已批准的常规分支/CI 流程让当前所需提交进入 GitHub Actions 可运行的 ref；本机 `origin/main...main = 0 0`，无领先提交。触发 CI 属外部写入，需用户单独授权，本报告不触发、不推送。
2. 用 `gh run list/view` 读取 `backend-postgres` job 的确切 workflow SHA、日志、退出码和 pytest 收集摘要。验证它运行的是欲验收的工作树代码，而非旧 main。
3. 若 job 成功：只能把 job 实际覆盖范围标成 PG16 PASS；如果它只跑 API，应依据实际命令注明具体范围。PG16 lane 不证明双进程 Discovery、多副本或 E2E 浏览器兼容。
4. 若 job 失败/缺少 artifact：保留 BLOCKED 或 FAIL（以实际退出码和质量门定义判定），不推断原因；禁止用 SQLite 结果替代。

SQLite-only：当前服务/仓储 ORM 乐观锁局部探针、M2 的失败注入与事务行为、当前全量结果。依赖 PG16 才能关闭：M2 双库声明、PG16 migration/database parity、M3 全部工具重试策略的双库验收；M7 的多进程/所有权验收还要求额外 harness，不会因 CI PG job 成功自动转 PASS。

## 5. 按里程碑的变更与提交边界建议

当前 `HEAD=0c0ab20`，`main` 与 `origin/main` 0/0。以下是分类提案，不暂存、不提交；实际文件未必全属于一个整洁提交，应在获授权后逐路径复核。

| 边界 | 当前相关文件 | 建议 |
|---|---|---|
| Discovery 启动恢复修复 | `apps/api/app/repositories/quality_discovery_repo.py`、`apps/api/app/services/quality_discovery_service.py` 的 `recover_interrupted_runs` 与 `_event` 抽取、`test_discovery_task_runtime.py` 的两条恢复用例 | 单独代码 + 定向测试提交。服务文件同时含 M2 改动，需按 hunk 拆分；不能整文件归给任一里程碑 |
| M1 研究与基线 | `docs/architecture-research/01`–`07`、`README.md`、`docs/QUALITY_GATES.md`、`AGENTS.md`、`CLAUDE.md` | 研究/规范文档独立提交；检查 CLAUDE.md 的 `@AGENTS.md` 实际导入规则和 AGENTS 仅新增质量门一行 |
| M2 原子性 | `quality_discovery_service.py` `_finish_locked/_update` hunk、`test_discovery_task_runtime.py` 6 个 M2 测试、`test_runs_and_failures.py` TestRun 顺序测试、`08/09` 文档及 handoff 对应记录 | 后端 M2 代码和测试一笔，验收文档可单独一笔；PG16 与 E2E 不得写成 PASS |
| Claude Code agent config | `.claude/agents/{architecture-critic,qa-reviewer,research-scout}.md`、`CLAUDE.md` | 与产品源码分开，先确认只含角色规则，无凭据/运行数据；不纳入本次产品修复提交 |
| S0 缺陷分析/证据 | 本文、`diagnostics/s0_repo_probe.py`、typecheck log、E2E 截图/Trace/日志 | `.ai-runs/**` 和 `runtime/backups/**` 一律排除版本控制；如需长期留档，仅把去敏、可复核的结论放入 docs。当前 evidence 含本机路径，不应整目录加入 |
| UI 修复 | `apps/web/src/index.css` / 缺失 helper 文件 / 对应前端测试（尚未改） | 单独前端缺陷提交，与 M2 后端独立 |
| 端口 fixture 修复 | `test_discovery_coverage_e2e.py`（尚未改）及必要 fixture | 单独测试稳定性提交，不和产品修复混杂 |

凭据扫描：对即将建议提交的文档与配置做了快速字面审查；没有在本次新建 S0 文档或 probe 中写入 key/token/password 值。仓库 `.claude/worktrees/ui-v2/` 是既存的嵌套工作树，不能因路径匹配 `.claude/**` 就递归纳入；必须排除其 `.git`、依赖锁、运行报告和产品副本。`git status --short` 显示的 `.ai-runs/**`、`runtime/backups/**` 均保留、不暂存。

## 6. M3 定义、依赖与建议

路线 §M3 原文范围：工具注册表声明 `READ_ONLY` / `IDEMPOTENT_WRITE` / `EFFECTFUL`，改 `task_execution_orchestrator.py:374-392` 重试判定并加 jitter；解决按工具名白名单重试导致只读与生成类混杂；每个工具需测试瞬时错误、不可重试错误、用户取消，断言次数/退避区间/终态，Pytest 判定保持不变；无法分类的工具保留旧行为并标 `UNKNOWN`。前置仅 M2；M3 与 M4 可并行，且不得引入新 runtime/provider。

依赖评估：

- M2 的 SQLite 原子写与失败处理边界已实作，但整体验收 PARTIAL，PG16 BLOCKED；M3 的核心在任务工具重试，不等同 Discovery DB 事务，故 PG16 是整套质量模板/双库就绪条件，但路线 M3 文字没有单列 PG16 GO 门。建议 M3 设计先开始，不假称 PG16 通过；M3 最终双库验收继续 BLOCKED，直到现存 CI job 给出对应 SHA 的结果。
- `_update` 未知字段静默接受与 M3 主体不同域，但若 M3 会复用 Discovery 更新 helper，则它会造成落库遗漏；建议先做 S0 最小契约修正或把 M3 的文件/调用范围确认不触及此 helper。
- 前端两个缺陷不与 M3 代码冲突，可以独立修复；Vite 端口不稳定性会影响浏览器验收证据质量，建议先把对应 fixture 最小修复纳入独立测试项。
- 前置架构契约：工具副作用分类枚举与 UNKNOWN 默认行为、各工具是否具备幂等键/重复写影响、取消优先级、旧白名单兼容配置开关的生命周期、jitter 有界区间与确定性测试注入时钟/随机数。必须先从当前注册表与 orchestrator 源码逐项盘点，不扩成第二套注册表或第二套 runtime。
- 进度可独立：**设计准备可 GO**（只读盘点工具与当前重试路径，写 M3 设计附录）；**产品实现 NO-GO，等待用户批准**；PG16 结果作为验收子门并行追踪。此建议不重定义 M3，也不自动开始实施。

## 7. S0 收口决定

- M1/M2 保持 **PARTIAL**，可按现有用户决定收口；不宣称双库/多实例 PASS。
- 全量测试不立即重跑；已有最终快照证据明确为 923 collected、910 passed、1 failed、12 skipped、exit 1。
- PG16 走既有 CI lane；任何提交/推送/dispatch 均待明确授权。
- mode-nav、缺失 helper、端口 fixture 各自立项；候选 diff/设计已记录，没有修改产品代码。
- M3 只允许只读设计准备；实现继续停在审批门。
- S0 额外验证：局部 SQLite repo probe 复现未知字段吞掉及 StaleDataError 乐观锁冲突；`git diff --check` exit 0；相关 skip 定向归因。没有运行全项目 lint 或全量重跑。
