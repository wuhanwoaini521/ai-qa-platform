# AI QA Platform — Release Candidate 验收报告

- 分支：`agent/ui-workspace-redesign`（独立分支，未合并 main，未部署）
- 代码 SHA（本轮所有自动化验收所绑定的提交）：**`3cbd2a8`**（其父提交为已交付的 Round 8 `23e73ab`）
- main：`d8a2eef`（未改动）
- 报告与证据目录：`.ai-runs/rc-acceptance/`、`.ai-runs/ui-redesign/`（均未纳入版本库）
- 最终结论：**PARTIAL**

> 本报告不把 RC 验收 PASS 等同于企业生产就绪。本轮结论为 PARTIAL，因此也不构成生产就绪。

---

## 0. 与历史 PASS 的区分

历史报告（Round 3–8、`docs/agent-handoff.md`）记录的是各轮功能交付的**通过情况**。本轮不以历史 PASS 作为完成依据：所有结论均来自本轮在 `3cbd2a8` 上重新执行的命令、真实浏览器操作和真实数据库（PostgreSQL 18.6）。

---

## 1. 第一阶段：开发收尾与功能冻结分类

| 状态 | 内容 | 证据 |
| --- | --- | --- |
| **已实现且通过验收** | 项目级多租户 ACL（Round 7 主体 + Round 8 补齐 `git_pr`/`ai`/`test_designs`/`lifecycle`/`onboarding`/`runtime`） | `apps/api/tests/test_project_acl.py` 8 passed；`test_authorization_rbac.py`、`test_identity_rbac_security.py` 等 57 passed；越权访问统一 404（不泄露项目是否存在） |
| **已实现且通过验收** | Worker 真实进程集成（`python -m worker.main` 子进程 + 真实 FastAPI + 长轮询 claim） | `apps/worker/tests` 8 passed；`test_worker_process_integration.py` SQLite 4 passed / PostgreSQL 4 passed，附真实 `worker.log` |
| **已实现且通过验收** | API 契约（OpenAPI 导出与生成类型同步） | `scripts/export_openapi.py --check` → current, exit 0 |
| **已实现且通过验收** | 迁移 0013 在真实 PostgreSQL 上的 upgrade/downgrade 往返；0013 增加列存在性探测，修复“启动即崩”的历史缺陷 | `test_postgres_migrations.py`（全新库 + `alembic upgrade head` + `compare_metadata` 漂移检查）5 passed；`test_runtime_migrations.py` 6 passed（含 0013 容忍手工加列的回归测试） |
| **已实现且通过验收** | 工作台 IA 改造（Stage Rail 全流程保持上下文、底部 Dock 可拖拽/键盘调整、上下文列表过滤） | 真实浏览器验证：5 个 stage 切换保持 `requirementId/testDesignId/caseId/bindingId/nodeid/file`；Dock 32px→220px，`role=separator`，ArrowUp 220→236；滤镜输入 1 个、空态正确 |
| **已实现且通过验收** | Quality Discovery 实时观测引擎（后端事件流 + 视口帧 + 元素几何 + 高亮叠加 + 前端 Live 工作台） | `test_quality_discovery_live.py` 11 passed（SQLite ×2、PostgreSQL ×3）；`test_quality_discovery_live_e2e.py` 真实 Chromium 1 passed |
| **已实现但未验证** | 真实 AI Provider 的成功路径（需求分析、根因分析、补丁建议） | 本环境 Provider 不可达（见 §2 步骤 2、10），仅验证了**诚实失败**与降级路径 |
| **已实现但未验证** | 除 0013 外其余 12 个 revision 的 downgrade | 本轮只对 0013 做了往返 |
| **已实现但未验证** | 备份/恢复、CI/CD、发布与回滚 | 仅文档层面存在，本轮无演练证据 |
| **部分完成** | AI/Jev 修复工作流（提案→人工批准→写回→精确验证） | UI 存在，但本环境下无法产生提案；且发现 D1 死锁（见 §5） |
| **部分完成** | 调试体验（断点/调用栈/变量） | 调用栈与变量可渲染，但失败文件:行号只在「源码」页显示（D3） |
| **部分完成** | 录制器与 Studio 的衔接 | 录制器独立页面可用；Studio 工具栏无录制入口（D6） |
| **未实现/未关闭（P2）** | AIProviderRegistry 在未 `configure_runtime` 时静默回落到 fake provider | `packages/qa-core/qa_core/ai/registry.py`（`_build_provider` 默认 `provider: "fake"`，本轮复核仍存在） |
| **未实现/未关闭（P2）** | `ArtifactORM` 无 `project_id`，产物路由仍只按角色授权；审计字段不全；`POST /api/jobs/{id}/result` 竞态仍返回成功；API 与 Worker 产物根目录不一致会静默丢件 | 本轮复核：`grep project_id` 于 `ArtifactORM` = 0 |
| **未实现/未关闭（P2）** | 覆盖率存在多套计算实现（`quality_intelligence_service`、`task_execution_orchestrator`/`task_goal_service`、discovery projection） | 本轮复核确认仍多套并存 |

**冻结结论**：本轮不新增大规模功能；除下文 §3 的两个“真实不稳定”修复外，仅新增回归测试与加固。

---

## 2. 第二阶段：模拟真实 QA 工程师（UI 全流程）

环境：真实前后端（`127.0.0.1:5173` / `:8000`），账号 `admin@ai-qa.local`，种子项目 `proj_golden_shop_v1`「Northstar · Golden Demo Shop」，被测站点 `examples/demo-shop`。**全部步骤均通过前端完成**；API 仅用于诊断。总点击 16 次、URL 变化 9 次、整页加载 16 次。

| # | 步骤 | 结果 | 耗时 | 导航 | 障碍/缺陷 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 打开需求（REQ-001 + AC-001） | 成功 | 登录 4.1s + 2.0s | 1 | — | `j00_login.png` `j01_requirement.png` |
| 2 | 真实 AI 分析需求 | **诚实失败但过晚**：90s 内无任何失败提示，形同卡死；随后报 `AI provider unavailable`，**未伪造结果** | 91.1s | 1 | **D2** | `j02_requirement_ai.png` |
| 3 | 审核生成的用例 | 成功 TC-001…009 | 1.7s | 1 | — | `j03_cases.png` |
| 4 | 查看用例步骤/期望 | 成功 | 1.7s | 1 | — | `j04_case_detail.png` |
| 5 | Studio 打开真实脚本（目标 `add-to-cart`） | 成功；绿色 page object 用 `button[name="Add to cart"]`，红色文件保留已删除的 `legacy-add-cart` | 5.7s（Monaco 1.9s） | 1 | — | `j05_studio_file.png` |
| 6 | 在 Studio 运行脚本 | 成功 `run_90015e2152c5` PASSED 7.9s | 10.8s | 1 | — | `j06_run_from_studio.png` |
| 7 | 在 UI 查看运行结果 | 成功：Dock 0.48s 自动打开，30 条分步事件（`点击 · internal:role=button[name="Add to cart"] · 通过`） | Dock 终态 11.2s | 1 | D5 | `dock_after_run.png` `j07_run_result.png` |
| 8 | 制造可控 Locator 失败并查看证据 | 成功：`run_1953951cf4db` FAILED 3.4s；横幅、locator 文本、堆栈、截图预览可达 | 20.4s | 1 | 截图不在首个标签页 | `j08*.png` |
| 9 | 调试面：文件:行号 | **部分成功**：堆栈+变量可渲染，失败文件:行号只在「源码」页 | 3.8s | 1 | **D3** | `j09_debug.png` |
| 10 | 从 UI 触发 AI 故障分析 | 诚实失败可见（`AI provider unavailable`）；但记录卡死，刷新后显示「未启动」且**无任何按钮** | 触发 4.0s / 等待 200.8s | 1 | **D1** | `j10*.png` |
| 11 | 修复提案界面 | 占位文案「尚未生成代码补丁 Diff」，无批准/应用按钮（正确——本无提案） | 0.07s | 0 | — | `j11_repair.png` |
| 12 | 在隔离场景批准修复 | **无法执行**（无法产生提案） | — | 0 | 环境阻断 | `j11_repair.png` |
| 13 | 需求→用例→自动化→执行→结果关联 | 成功：Stage Rail 显示 用例 9 / 已绑定 8-9 / 结果 8/8，并带 id | 0.07s | 0 | 逐用例链接仅对选中用例 | `j13_linkage.png` |
| 14 | 统计 | 16 次点击、9 次 URL 变化、16 次整页加载；**必须回终端 0 次** | — | — | — | `journey.json` |

结论：**日常核心链路（需求→用例→脚本→运行→结果→失败证据）可以只靠 UI 完成**；涉及真实 AI 的环节本环境不可达，UI 的失败表达基本诚实，但存在 §5 的交互缺陷。

---

## 3. 第三阶段：连续稳定性验证

**核心链路 3 次独立重复（打开用例 → 运行脚本 → 查看结果）**

| 运行 | 状态 | Monaco 就绪 | 结果重复 | 状态丢失 | 浏览器泄漏 |
| --- | --- | --- | --- | --- | --- |
| 1 | PASSED `run_c70eab49c8a0` | 2.87s | 无（7→8） | 无 | 0 |
| 2 | PASSED `run_3c8f35e26e67` | 2.90s | 无（8→9） | 无 | 0 |
| 3 | PASSED `run_655c51971359` | 2.84s | 无（9→10） | 无 | 0 |

失败率：**意外失败 0/4**（唯一 FAILED 是按设计制造的红色用例）。Dock 在 5s 后仍保留状态，刷新页面保持 `test_shop.py`，无重复结果、无状态丢失、无浏览器泄漏（`pgrep` 计数回到基线）。

**本轮定位并修复的两个真实不稳定问题**

1. **Discovery 直播流的真实竞态（已修复）**：`quality_discovery_service.event_generator` 在订阅前做同步 DB 读取，订阅者可能在事件发布之后才入队，导致“已完成的运行”长时间挂住直到测试超时。修复：订阅先行 + `LIVE_STREAM_IDLE_TIMEOUT_S=3.0` 空闲收尾（`apps/api/app/services/quality_discovery_service.py`），并新增回归测试 `apps/api/tests/test_quality_discovery_live.py::test_live_stream_finishes_when_the_run_ends_before_the_viewer_attaches`。修复前：同一用例连续 5 次运行出现 1 次挂起；修复后：连续 3 次全量运行 0 次挂起（971 passed / 890 passed / 890 passed 样本）。
2. **迁移 0013 的启动崩溃（已修复）**：历史开发库已有 `projects.owner_id` 但 `alembic_version` 仍为 `0012`，导致 `ALTER TABLE ... ADD COLUMN owner_id` 报 `duplicate column name` 使 API 无法启动。修复：`0013_project_ownership.py` 用 `sa.inspect` 探测既有列/索引后只建缺失部分，并新增回归测试 `test_runtime_migrations.py::test_project_ownership_migration_survives_a_previously_unaltered_column`。

**未修复的真实偶发失败（如实记录）**：`apps/api/tests/test_browser_agent_e2e.py::test_browser_agent_checks_and_switches_to_popup_landing[selenium.dev-False-False]` 在全量套件（11 分钟、高负载）中失败 1 次，错误为 `playwright._impl._errors.TargetClosedError: Locator.count: Target page, context or browser has been closed`（测试第 1135 行路径）；单独运行为 **3/3 passed**。根因方向：弹窗关闭后仍对其计数（`apps/api/app/adapters/playwright/locator.py:30` 与 `apps/api/app/services/task_browser_executor.py:245` 的页面枚举）。本轮**未做盲目修补**，作为已知不稳定项移交。

其它检查项：并发测试互不干扰（无共享状态失败）、AI Provider 失败处理已被验证为“降级而非整轮失败”、Jev 决策可追溯（`result.decisions[]` 带 provider/model/confidence，且 UI 可见）、服务重启后数据完整（重启 API 后运行记录/证据仍可读）、取消/超时释放（`/stop` 路径与 `test_worker_process_integration` 的 cancel/timeout kill 用例通过）。

---

## 4. 第四阶段：企业级部署门禁

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| PostgreSQL 真实集成 | **PASS**（修复后） | PostgreSQL 18.6 @ `127.0.0.1:55432/aiqa_test`；`875 passed, 7 skipped in 448.83s`；`-m postgres` 显式运行 `5 passed`（证明非静默跳过） |
| Worker 真实进程集成 | **PASS** | 真实 `python -m worker.main` 子进程 + 真实 API：SQLite 4 passed / PG 4 passed；真实 worker.log（注册、并发 4、claim） |
| RBAC 与项目隔离 | **PASS** | `-m security` 16 passed（SQLite 与 PG 各一次）；ACL/RBAC 相关 5 个文件 57 passed；跨项目访问统一 404 |
| 安全负向测试 | **PASS** | 同上 16 条负向用例（越权、路径穿越、工作区隔离等） |
| API 契约 | **PASS** | OpenAPI 导出校验 current |
| 数据库迁移 | **PASS（0013）** | 全新库 `alembic upgrade head` + `compare_metadata` 无漂移；0013 往返可回滚 |
| 日志与审计 | **部分** | 审计表与不可变日志存在；审计字段不完整的已知 P2 未关闭 |
| 密钥保护 | **部分** | `.env` 不入库、日志脱敏存在；未见密钥轮换/托管演练 |
| 数据备份与恢复 | **阻断（无演练）** | 本轮只做了“迁移前备份开发库”的临时动作（`/tmp/ai_qa_platform.db.bak-*`）；无正式恢复演练 |
| CI/CD | **阻断** | 仓库内未验证 CI 流水线运行证据 |
| 发布与回滚 | **阻断** | 未部署，无发布/回滚演练 |

**明确阻断**：未经授权未做任何生产部署；备份恢复、CI/CD、发布回滚三项缺少真实证据，不得视为企业就绪。

---

## 5. 第五阶段：产品 UX 整改

本轮基于第二阶段真实操作记录，已修复并保留 Before/After 截图的项（`.ai-runs/ui-redesign/before/` 28 张完整页面，`.ai-runs/ui-redesign/after/`）：

| Before 问题 | After 结果 |
| --- | --- |
| 工作台左侧 Stage Rail 在切换流程时丢失选中上下文 | 5 个 stage 全流程保持 `requirementId/testDesignId/caseId/bindingId/nodeid/file`（真实浏览器断言） |
| 底部执行面板高度固定，不能调整 | Dock 由 32px 折叠可拖至 220px+，支持 `role=separator` 拖拽与键盘 ArrowUp/Down |
| 上下文列表在项目变大后不可控 | 新增过滤输入 + showMore + 空态 |
| `index.html` 请求 Google Fonts（本环境不可达）导致截图/排版静默降级 | 移除外部字体，改为系统字体栈（`--font-sans/--font-mono`），并加 `design-system.test.mjs` 防止回归 |
| 存在未声明 CSS 变量与裸字体栈（6 个 token、7 处字体栈、1 处非法 JSX `fontFamily: inherit`） | 全部修复并由 4 个设计系统测试守护 |

**仍未整改（按影响排序，均来自本轮真实操作）**

- **D1（高）AI/Jev 修复分析死锁**：连接中断后服务端 `status=RUNNING` / workflow `ANALYZING` / `allowed_actions=[]`；刷新后 UI 显示「未启动」且隐藏所有操作（无取消/重试/批准），**UI 与 API 矛盾**，普通导航即可触发。
- **D2（高）AI 分析 90s+ 无失败提示**：任务记录停留在 RUNNING，执行观察台可无限显示“运行中”。
- **D3（中）调试页缺失败文件:行号**（仅在源码页）。
- **D4（中）侧边栏 `/runs`、`/quality` 离开工作台**，丢失 stage rail 上下文。
- **D5（低-中）结果摘要过薄**：分用例详情只在 Dock/单独运行记录页。
- **D6（低）Studio 无录制入口**：录制器仍是独立页面，录制→脚本→编辑链路不连续。

正面确认：干净阻断形态（`allowed_actions=['START_ANALYSIS']` → UI 显示「重新分析」）的重试路径**可用**，说明 D1 是“卡死形态”而非“阻断形态”的问题。

---

## 6. 第六阶段：Release Candidate 最终验收（绑定 `3cbd2a8`）

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量回归（SQLite） | `uv run --no-sync pytest apps/api/tests packages -q -p no:randomly` | **1 failed, 870 passed, 11 skipped, 658.73s**（失败即 §3 的弹窗偶发项） |
| 后端全量回归（PostgreSQL） | 同上 + `AI_QA_TEST_DATABASE_URL=...aiqa_test` | **875 passed, 7 skipped, 448.83s** |
| 前端测试 | `pnpm --filter @ai-qa/web test` | **179 passed, 0 failed** |
| Typecheck | `pnpm --filter @ai-qa/web typecheck` | 0 errors |
| Lint（前端） | `pnpm --filter @ai-qa/web lint` | clean |
| Build | `pnpm --filter @ai-qa/web build` | 成功（29.8s） |
| i18n 一致性 | `uv run python scripts/i18n_check.py` | 25 namespaces / 2 languages / 3067 keys passed |
| OpenAPI 契约 | `scripts/export_openapi.py --check` | current |
| Playwright E2E | `-m e2e`（`test_quality_discovery_live_e2e.py` 真实 Chromium、`test_browser_agent_live_e2e.py`）+ `test_discovery_coverage_e2e.py`、`test_live_enterprise_journey.py`、`test_studio_debug_ui_live.py`（均在全量套件内） | passed（单文件 1 passed in 2.37s） |
| 真实 AI/Jev | UI 触发 + DB 取证 | **Jev = LIVE**（`provider=jev`, `model=jev-1.13.0`, confidence 0.96/1.0/1.0，3 条决策）；**AI 规划 Provider = BLOCKED**（20s 超时 → `ai.unavailable`，运行继续，states=3/actions=3/features=9） |
| Studio Debug | 真实浏览器 + 套件内 live 用例 | 通过（断点/调用栈/变量可达；文件:行号见 D3） |
| Failure Repair | UI 走查 | **部分**：入口与门禁存在，提案无法生成（D1 阻断） |
| Discovery → Coverage | `test_discovery_coverage_e2e.py` + UI | 通过 |
| 数据隔离 | `-m security` + ACL 套件 | 通过（跨项目 404） |
| PostgreSQL / Worker | 见 §4 | 通过（PG 修复后全绿）；备份/CI/CD 阻断 |
| UI 产品验收 | 22→28 张 Before + 5 张 After + 真实浏览器交互断言 | 通过（附 §5 缺陷） |

### 七问结论

1. **是否具备日常使用条件**：**部分具备**。单操作者、单项目的核心 QA 闭环（需求→用例→脚本→运行→结果→失败证据→调试入口）可以只靠 UI 完成；一旦涉及 AI 修复分析或多人协作，目前会踩到 D1 与未暴露的团队协作流程。
2. **哪些功能已可靠**：工作台 IA 与上下文连续性、Studio 编辑与运行、运行结果与分步事件、Step 级 locator 证据、录制器页面、Quality Discovery 实时浏览器观看与元素几何/高亮、项目级 ACL（单项目内）、Worker 真实执行、迁移 0013、API 契约。
3. **哪些仍不好用**：AI/Jev 修复分析（D1 死锁、D2 无失败提示）、调试页缺文件:行号（D3）、侧边栏离开工作台丢上下文（D4）、结果摘要偏薄（D5）、Studio 无录制入口（D6）。
4. **哪些严重缺陷尚未关闭**：D1（高）、D2（高）、弹窗 E2E 偶发 `TargetClosedError`（中，仅高负载下出现）；此外 `ArtifactORM` 无项目隔离、fake provider 静默回落、多套覆盖率计算仍为 P2。
5. **企业部署还缺什么**：备份/恢复演练、CI/CD 流水线证据、发布与回滚演练、密钥托管与轮换、完整审计字段、产物级项目隔离、把探索循环纳入 TaskRuntimeService（当前为进程内 `asyncio.create_task`，`quality_discovery_service._schedule`）。
6. **是否允许进入 Staging 试运行**：**允许（受限）**——用于单项目、单操作者、以真实浏览器执行与证据查看为主的试运行；**不得**作为生产/多租户环境使用，必须带着 D1/D2 与 §4 阻断项进入。
7. **推荐的下一版开发优先级**：① 修复 D1/修复分析状态机（含取消/重试/恢复）→ ② AI 失败提示与超时可视化（D2）→ ③ 调试页文件:行号与证据聚合（D3）→ ④ 真实 AI Provider 可达性验证（补上唯一无法自动验收的环节）→ ⑤ 产物级项目隔离与覆盖率统一 → ⑥ CI/CD + 备份恢复演练。

---

## 7. 最终结论

**PARTIAL**

理由：核心日常链路已可用且证据可复现（SQLite/PG 双后端、真实浏览器、真实 Worker 进程、真实 RBAC 负向测试），另有 7 项在此轮之前未记录的“已实现且通过验收/已修复”成果；但（a）真实 AI/Jev 的成功路径本环境不可达，仅验证了诚实失败与降级；（b）存在 1 个高影响 UX 死锁（D1）与 1 个高影响反馈缺陷（D2）；（c）仍有 1 个高负载下的偶发 E2E 失败；（d）备份恢复、CI/CD、发布回滚缺少真实证据。故不满足 PASS，也远未达到企业生产就绪。

**本 PARTIAL 结论不得被解释为企业生产就绪，也不得解释为 RC 验收 PASS。**

---

## 8. Round 11 复审（本轮，绑定 `be6ec64`）

> §6 与 §7 的结论只对被绑定的 `3cbd2a8` 有效。本节记录其后的 Round 11：`origin/main` 之上 17 个提交、3 个迁移（0013→0015），以及在这些提交上重新执行的验收。历史 D1–D6 与 §4 阻断项的逐条处置见下。

### 8.1 历史缺陷与阻断项的关闭情况

| 历史项 | 现状 | 证据 |
| --- | --- | --- |
| D1 分析卡在 RUNNING/ANALYZING | **关闭** | `5eb2376`+`7aac715`+`7b82832`：分析改由服务自持任务运行、持久化行是权威来源、SSE 只做跟随；取消走真实端点。真实浏览器：刷新后仍显示「运行中」并有「取消分析」，取消后 `CANCELLED`+原因，重试后 `COMPLETED`+根因。`.ai-runs/d1-d2-lifecycle/{browser-acceptance.json,screenshots/00-before-*,00b-after-*,02,03,04}` |
| D2 九十秒无明确反馈 | **关闭** | 分层预算 `repair.analysis_timeout_seconds=300`（`packages/platform-config`）+ 阶段进度事件（`model.progress` 每秒级）；超时→`TIMEOUT`+`ANALYSIS_TIMEOUT`+可重试；回归测试 `test_analysis_timeout_ends_the_run_with_an_explicit_retryable_error` |
| D3 调试页缺失败文件:行号 | **关闭** | `6a851ac`：迁移 0014 持久化 `failure_records.source_file/source_line`（来源是真实失败帧），前端记录优先、正则/断点兜底；测试断言 `tests/test_failing.py:4` 经 API 返回 |
| D4 离开工作台丢上下文 | **关闭** | `c74789f`：侧栏与路由带 `projectId`，`/runs?...&runId=` 深链选中该 run；`.ai-runs/context-continuity/browser-acceptance.json` |
| D5 结果摘要偏薄 | **未处理** | 本轮未改；仍为已知可用性问题 |
| D6 Studio 无录制入口 | **部分** | `507c59d` 把录制步骤与可编辑 Case 关联（Studio 上下文栏显示录制步骤+证据，重录不再 409）；**仍未**在 Studio 常规工具栏加入口（入口仍只在未绑定空状态） |
| 高负载弹窗 `TargetClosedError` | **关闭** | `ffa7ad2`：活动页关闭时收养同上下文存活标签页，只有浏览器断开或没有可用页才判 CRASHED；`apps/api/tests` 全量 724 passed（含浏览器用例） |
| 真实 AI/Jev 成功路径不可达 | **关闭（含需诚实标注的细节）** | `POST /api/ai/test-connection` → `connected=true, status=AVAILABLE, latency_ms=24722`；真实失败分析 `status=COMPLETED`（16.9s，含真实根因与候选定位器）。**细节**：本环境 Jev 评分调用大量以 `FALLBACK` 收尾（`error_type` 为 `invalid_request`/`confidence_missing`），定位器决策实际由确定性回退产生，报告与 UI 不得将其描述为真实模型决策 |
| AI 长生成超时（新发现） | **关闭** | `df4d709`：请求级超时不再只能下调，长结构化生成用 90s 预算；同一 gap 动作由 502/129.2s 变为 200/61.1s |
| 探索循环未纳入 TaskRuntimeService | **关闭** | `e1f3fdb`：`EXPLORE_PRODUCT` 任务的 `discovery.run` 步骤驱动既有边界循环，run 行记录 `result.runtime_task_id`；SIGTERM → `STOPPED`（含原因）、SIGKILL → 重启后 `PAUSED`+说明并可 `resume`（`.ai-runs/discovery-live/{restart-recovery.json,crash-recovery.json}`）；代价（占用调度器 2 个并发槽之一）已写入 `docs/QUALITY_DISCOVERY.md` |
| 无页面对象时缺引导 | **关闭** | `2d642e3`：草稿生成返回 `page_objects`（`pages/*.py` 等），空草稿的错误里附下一步引导，前端与 i18n 同步 |
| 观察体验（当前操作/高亮/网络/步骤证据） | **关闭** | `edcde0a`：`state.observed` 携带 url/network/evidence_ids，实时视图新增网络面板与「查看证据」；`.ai-runs/discovery-live/screenshots/01-live-observation.png`（网络 `2xx 2 / 失败 0`） |
| `ArtifactORM` 无项目隔离/审计字段 | **关闭（审计为部分）** | `19f7e33`：迁移 0015 增 `project_id`/`created_by`，读接口按资源归属鉴权（无归属的历史行仅管理员）、写接口记录来源；`test_artifact_access_is_project_scoped` 覆盖跨项目 404。其他表的审计字段此前已具备 |
| 多套 Coverage 口径 | **关闭** | `31450a3`：`/quality` 与生命周期面板只渲染 `/api/quality/coverage` 的数字，前端重复实现删除；差异说明写入 `docs/QUALITY_INTELLIGENCE.md` |
| 迁移 upgrade/downgrade 证据不足 | **关闭** | `test_runtime_migrations.py` 断言脚本 head 并覆盖 0014/0015 的 upgrade→0013→upgrade；整链钻练习 `.ai-runs/migrations/drill.log`（`downgrade base` 保留 36 张表是 `0001_baseline` 的刻意设计） |
| 备份恢复演练 | **关闭** | `bf8aa31`：SQLite 在线快照 + 可指定恢复目标；演练逐表行数一致、`integrity_check=ok`（`.ai-runs/ops/backup-restore.log`） |
| 密钥轮换 | **关闭（重启式）** | 平台不提供在线换钥（`AISettingsService.save()` 直接拒绝），演练为改配置 + 重启：错误密钥 → 健康检查通过且 `connected=false`、密钥不外泄；换回后 `connected=true`（`.ai-runs/governance/key-rotation-drill.json`） |
| CI/CD 运行证据 | **BLOCKED** | `.github/workflows/ci.yml` 存在，但 `main` 领先 `origin/main` 且从未推送 → 流水线从未运行。以本地等价检查替代（ruff/format、`export_openapi.py --check`、i18n 校验、web typecheck/lint/test、pytest） |
| 部署与回滚演练 | **BLOCKED** | 本环境无容器运行时（`docker`/`docker compose` 均不存在），`scripts/deploy.sh` 与回滚路径无法执行 |
| 产品级前后对比与移动端 | **关闭** | 9 个核心页面 × 桌面 1440x900 / 移动 390x844 巡检：横向溢出 0、控制台错误 0；Before（RC 轮 49 张）与 After 对照见 `.ai-runs/final-acceptance/before-after.md`、`viewport-sweep.json` |

### 8.2 最终回归

在最终代码 `89eb5ed`（含评审两轮修复）上重跑，日志 `.ai-runs/final-acceptance/regression-final-r2.log`：

| 检查 | 结果 |
| --- | --- |
| 后端全量（`uv run pytest -q`，SQLite） | **892 passed / 11 skipped / 60 warnings / 810.49s（13:30）** |
| Ruff check / format | `ruff check .` → All checks passed；`ruff format --check` → 445 files already formatted |
| OpenAPI 契约 | `scripts/export_openapi.py --check` → OpenAPI contract is current |
| i18n | `scripts/i18n_check.py` → 25 namespace(s) / 2 language(s) / 3080 keys |
| 前端 typecheck / lint / 单测 | `tsc --noEmit`、`eslint .` 无输出；**188 pass / 0 fail** |
| 真实浏览器连续旅程（最终代码） | **8/8 断言通过**、控制台错误 0（`.ai-runs/final-acceptance/journey.json`）：运行结果→持久化分析（非“未启动”）→人工批准/已应用门禁→根因文本→`/runs` 保留项目上下文→`/quality` 覆盖率数字→失败页 `shop.py` 源位置 |
| 视口走查（9 页 × 桌面/移动） | 横向溢出 0、控制台错误 0（`viewport-sweep.json`、`before-after.md`） |

### 8.3 本轮结论

**PASS（达到日常可用标准）。** 判定依据与 §7 的 PARTIAL 不冲突：§7 只对被绑定的 `3cbd2a8` 有效，本轮在其后修完了全部有证据的问题。

- P0 已关闭且有真实证据：D1/D2 分析生命周期（刷新后仍为“运行中”、取消真停、超时/失败有原因且可重试）、高负载 `TargetClosedError` 根因修复（弹窗关闭后收养存活标签页）；真实 AI Provider 成功路径实测（`/api/ai/test-connection` → `connected=true`，失败分析 `COMPLETED`）。
- 核心链路在最终代码上用真实浏览器逐步验收：发现→需求草稿/用例/自动化草稿、录制→Studio（含录制定位器与页面证据）、运行→失败定位（文件:行号）、人工批准→应用→精确复测（`run_59160b44fca1b9316267281a01df87e6` PASSED）、`/runs` 与 `/quality` 上下文连续。
- 工程治理：迁移 0013→0015 双向演练、备份/恢复逐表一致、密钥轮换（重启生效）实测、产物项目级隔离与按资源鉴权。
- 独立评审：两轮（首轮 PARTIAL → 修复 `be6ec64` → 复评 PASS → 复评新增 4 条已修于 `89eb5ed`），最终回归在修复后的提交上重跑。

**明确标记为 BLOCKED（不计入 PASS）**：CI/CD 流水线（本轮提交从未推送，`.github/workflows/ci.yml` 未运行，以本地等价检查替代）；部署与回滚演练（本机无容器运行时）；PostgreSQL 通道（本机无 PG）。**需诚实标注**：本环境 `discovery_candidate_score`（`jev-1.13.0`）50/50 以 `FALLBACK` 收尾（`error_type=invalid_request`），定位器决策由确定性回退产生，不得描述为真实 Jev 模型决策。**仍存的历史 UX 项**：D5 结果摘要偏薄；D6 录制入口仍只在 Studio 未绑定空状态。

