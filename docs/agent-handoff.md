# Agent 交接文档 / Agent Handoff

> 规则：每个可验证里程碑完成后更新本文件。后续 Agent 必须先阅读本文件、核对 Git 状态与真实测试结果，再继续开发。
> 禁止把聊天记录或未跟踪的临时日志作为唯一进度来源。

**2026-10-29 Discovery recovery milestone:** 基线 Git commit 为 `d66c531`。在现有 `QualityDiscoveryRunORM.version` 乐观并发控制上修复启动恢复竞态：仍只扫描超过 600 秒未更新的非终态 run；恢复时以扫描到的状态作条件保护，并将 PAUSED 状态、错误和 `run.paused` 持久化事件放在同一事务中，提交后才发布 live 通知。没有 schema/migration 或 Runtime/Agent/Provider 所有权变更。LangGraph 学习映射：持久化 run/result/events 对应 checkpoint，人工 pause/resume 对应 interrupt/resume；恢复时可能重跑的节点必须让外部副作用幂等。本修复只提供单行乐观并发与原子持久化，不提供多 API 实例 lease/fencing，也不自动重放有歧义的浏览器副作用。验证：SQLite `test_discovery_task_runtime.py` **15 passed**、`test_worker_process_integration.py` **4 passed**；隔离 PostgreSQL 16 两文件合跑 **19 passed**（该结果来自此前的 macOS + Docker 环境；当前 WSL2 环境无可用 Docker/PG，**不可复现，也不得作为 M2 双库证据**）；改动文件 Ruff check、Ruff format check、`git diff --check` 全通过。PostgreSQL 16 证据仅覆盖该定向测试范围，不代表多实例 fencing 验收。后续可用命令：`uv run pytest apps/api/tests/test_discovery_task_runtime.py apps/api/tests/test_worker_process_integration.py -q`；PostgreSQL lane 需先启动隔离 PostgreSQL 16 并设置 `AI_QA_TEST_DATABASE_URL`。本轮代码与文档保持未提交；保留 `.ai-runs/**`、`runtime/backups/**`。

**2026-10-29 architecture research milestone (docs only, Architecture Gate NOT PASSED):** 基线仍为 `d66c531`，分支 `main`。新增 `docs/architecture-research/`（`README` + `01`–`06`），未改产品代码、测试、迁移或 API。内容：研究分支继承矩阵（I-1..I-11 / V-1..V-7 / O-1..O-6 / U-1..U-7，纠正「Workflow Canvas 只是观察器」「Alembic 0015」等过时说法，实际 head 为 `0023`）；基于源码的调用链与 F1–F9 缺陷（每条含问题/证据/根因/影响/改进/验证）；LangGraph 1.2.18、Browser Use 0.13.14、Skyvern v1.0.56 的机制学习（**均未安装、未运行**，Skyvern 为 AGPL-3.0 且 `playwright==1.56.0`、`fastapi<0.137` 与本项目冲突）；A/B/C 对比后推荐 **B′（现有边界内约束性重构）**，拒绝统一事件/证据契约层；7 个里程碑 M1–M7 与 GO/NO-GO；Architecture Critic 与 QA Reviewer 的独立评审记录。结论：研究维度 PASS/PARTIAL 混合，**总体 PARTIAL**，Gate **NOT PASSED**；仅批准 M1/M2 的设计与实施准备，需人工批准后才能改产品代码。未执行验证项一律标 UNKNOWN/BLOCKED（多进程 claim、跨进程迟到写、PG16 全量、框架运行行为、Skyvern 法务）。本轮未 commit/push/merge/reset/clean，未安装依赖。

**2026-10-29 M1/M2 refactor milestone (user-approved bounded work):** 基线仍为 `d66c531`（未创建提交）。M1 只读盘点完成：`docs/architecture-research/07-m1-baseline.md` 记录三域状态枚举→7 类展示映射（唯一待人工确认项：TestRun `SKIPPED` 归 `UNKNOWN`）、事件语义（仅 Task 有可游标寻址的持久事件；TestRun 无持久事件表；Discovery 为有界 JSON + 进程内 hub）、39 个注册工具的副作用分类草案（识别 11 项重试白名单中 `browser.verify`、`tests.resolve_requirement` 属边界工具的风险点，留待 M3）、11 个测试文件→里程碑矩阵。M1 机器验收：`uv run python scripts/export_openapi.py --check` PASS（exit 0）；PG16 基线 **BLOCKED**（本 WSL2 环境无 docker/postgres，无 5432 监听，上一轮 macOS+Docker 结果不可移植）。M2 实现：`quality_discovery_service.py::_finish_locked` 改为单次 `_update(..., expected_statuses=(row.status,), persisted_event=("run.<status>", message))`，终态/错误/`finished_at`/终态事件同一事务，`_publish_event` 与 `live.publish` 移到提交后；状态守卫防止覆盖并发更新，守卫失败时 `return` 不广播。TestRun 侧复核为**已原子**（`transition_run_status` 单条带守卫 UPDATE，与 `close_running_sessions` 同一 commit，`RUN_FINISHED` 为提交后 SSE），未改产品代码，仅加顺序回归测试。新增 7 个测试（6 个 Discovery + 1 个 TestRun）：Discovery 成功原子性、广播失败不回滚、事件写失败回滚且无广播、并发改状态不覆盖、TestRun 提交后广播。验证：`test_discovery_task_runtime.py` 21 passed；`test_runs_and_failures.py`+`test_discovery_task_runtime.py`+`test_quality_discovery.py`+`test_worker_process_integration.py` 148 passed / 1 skipped（skip 原因 `requires AI_QA_TEST_DATABASE_URL pointing at PostgreSQL`，`test_runs_and_failures.py:573`）；`test_task_lease.py`+`test_task_cancel_fencing.py`+`test_architecture_boundaries.py`+`test_workflow_execution.py` 合跑 72 passed / 1 skipped；Ruff check/format、`git diff --check`、OpenAPI 全通过。PostgreSQL 16 通道 BLOCKED，只能声明「SQLite 通道完成」。结果文档 `docs/architecture-research/08-m2-terminal-atomicity.md`。M3+ 仍需逐项批准；未 commit/push/merge。 全量套件首轮（921 收集，非最终测试文件）为 **1 failed / 908 passed / 12 skipped / 1013.87s / exit 1**，失败原因是 `API/Vite servers did not become ready; Vite exit=1`（Vite `Port 46847 is already in use`，`_free_port()` 的 TOCTOU 夹具不稳定）；最终测试文件上重跑（923 收集）为 **1 failed / 910 passed / 12 skipped / 685.42s / exit 1**，失败为浏览器 E2E `test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e` 的点击拦截，根因是 `apps/web/src/index.css:914-918` 给 `.workspace-shell` 只定义 3 行网格而 shell 现有 4 个子元素，mode-nav 落入 `minmax(0,1fr)` 行被压成 0px（1280×720 与 1280×800 实测 `gridTemplateRows=68.6875px 72px 0px ...`），被 `.workspace-main-heading` 覆盖后点击被拦截。已在隔离 worktree `/tmp/aiqa-baseline-d66c531`（`d66c531`，Python 3.13，独立 SQLite/动态端口/独立证据目录/全新浏览器上下文）复现为同一失败，判定 **EXISTING DEFECT**，非本轮回归；证据 `.ai-runs/2026-10-29-arch-refactor-m1-m2/`（`e2e-current-tree.log`、`e2e-baseline/probe-failure.json`、`probe-failure-1280x800.json`、`probe-trace.zip`、`probe-failure.png`）。全量套件启动早于最后 2 个测试写入（收集 921，当前可收集 923），已单独补跑相关文件为 21 passed。PostgreSQL 16 仍 **BLOCKED**：WSL 内 docker 为悬空符号链接，Windows `docker.exe desktop status` 为 stopped，`docker.exe ps` 返回 `Docker Desktop is unable to start`，无本地 PG/5432。红/绿证据：同一失败注入断言在 `d66c531` 旧两事务路径上得到 `assert 'COMPLETED' == 'RUNNING'`（`.ai-runs/.../e2e-baseline/red-evidence-d66c531.log`），在新代码上回滚通过。独立架构评审结论 CONDITIONAL、无 BLOCKER；保留项（`_update` 参数静默吞掉、并发用例仅进程内、双 UPDATE、版本列依赖）已记入 `docs/architecture-research/08-m2-terminal-atomicity.md` §5.1。 最终质量门报告：`docs/architecture-research/09-final-acceptance.md`——M1/M2 均判 **PARTIAL**（可关闭）；PostgreSQL 16 与跨进程仍 BLOCKED；前端 mode-nav 为既有缺陷；当前未授权进入 M3。

**2026-10-29 S0 stabilization analysis:** HEAD `0c0ab204960ab725958d6f97c6fcb82fc6a88609`, branch `main`, `origin/main...main=0/0`. Added `docs/architecture-research/10-s0-stabilization.md` and updated the research index; no product code was modified. Independently reproduced the Quality Discovery repository's unknown-keyword bug in an isolated temporary SQLite database (`finishd_at` was accepted as an instance attribute but did not persist); a two-session stale-version probe confirmed the second ORM writer raises `StaleDataError` after the first commits. Mapped all 12 full-suite skips from existing gates: 6 PostgreSQL-only, 6 opt-in live/provider acceptances. Current frontend `pnpm --dir apps/web typecheck` exits 2 with TS2307 because `AutomationStudioPage.tsx` imports `./defaultWorkspaceTestFile`, absent since commit `245c00c`; this predates M1/M2. Baseline DOM probe confirms the Workspace mode-nav defect at 1280×720, 1280×800, 1440×900, and 1920×1080; a candidate CSS fix was tried only in the isolated baseline worktree and made the click succeed. The final API suite remains 923 collected / 910 passed / 1 failed / 12 skipped / exit 1; no rerun requested. PG16 remains BLOCKED locally; proposed the existing `.github/workflows/ci.yml` `backend-postgres` job as the independent lane, but did not trigger external CI. M3 remains design-prep GO only; product implementation awaits approval. `git diff --check` exit 0. S0 evidence probe and typecheck log are under `.ai-runs/2026-10-29-arch-refactor-m1-m2/diagnostics/`; do not stage `.ai-runs/**` or `runtime/backups/**`. Product-code previews and proposed commit boundaries are in the S0 document; no commit/push/merge/reset/clean/stash was performed.

**2026-10-29 company-PC handoff synchronization:** Pending commit/push work is on `handoff/company-pc-2026-10-29`, forked from `main` at `0c0ab20`. Categorized commits: backend recovery + M2 atomicity (`f9b2a64`), research/handoff (`db93e60`), shared quality gates (`060a6f2`), Claude Code roles (`8146a3a`). The final remote-reference verification record is captured below on the independent UI handoff branch; the primary handoff branch is independently remote-verified at its exact SHA. `main` itself equals `origin/main` at `0c0ab204`; no 45-commit main backlog exists in this checkout. Local research branch equals `origin/agent/autonomous-rd-2026-10-28` at `645bc20`. Local branches `agent/discovery-live-engine` (`d8b332d`), `agent/ui-workspace-redesign` (`15abcf8`), and `agent/wsl-continuation` (`b6bb5fc`) are already ancestors of main. The separate `worktree-ui-v2` branch at `9a2e702` has three commits beyond its merge base and diverges from current origin/main (5 ahead / 3 behind); it is being preserved under a separate handoff branch, without merging. GitHub GraphQL metadata returned 404, while `git ls-remote origin` successfully listed the expected repository's refs; main protection could not be inspected, so no direct main push is planned. Excluded from upload: all `.ai-runs/**` (about 2.8 GB, including test DBs/screenshots/traces), all `runtime/backups/**` (about 64 MB, including SQLite backups and a Git bundle), the baseline worktree's CSS prototype and temporary probes, and UI worktree `.ai-runs/ui-v2-audit/**` plus probe files/node_modules. Local run data and worktrees were not deleted. `pnpm --dir apps/web typecheck` returned exit 2 (existing missing `defaultWorkspaceTestFile`, TS2307); no broad tests were run. M1/M2/S0 remain PARTIAL; PG16 BLOCKED; resume with review of the handoff branch and existing CI PostgreSQL 16 lane before any M3 implementation.

## 1. 当前任务目标

**2026-10-24 categorized local baseline:** Starting HEAD was `e7b90175e04022a489f04407e6a9165a54d2e2ed`; backend commit `0ac8b67` contains the Task Runtime/workflow/canvas changes. Current HEAD before the remaining Web + handoff commit is `0ac8b67`. The older continuation entry below names `a732cb1e4895fcf580ee430c1126e4fd7510af54`, which does not match this checkout. The pending version contains Task Runtime lease/artifact safety and published workflow execution changes, workflow-canvas discovery filtering, and Workflow Studio/editor UI changes. User authorized categorized local commits, but not push/merge/deploy. Verification run on this tree: API focused tests **129 passed, 1 skipped** (plus `test_openapi_contract.py`: **1 passed**); web **227 tests passed**, typecheck, lint, and production build passed; Ruff and `git diff --check` passed. OpenAPI-types generation exposed two missing WorkflowCanvas fields; regenerated `apps/web/src/api/generated-schema.d.ts`, then confirmed byte-identical regeneration and typecheck. Production build reports the existing large-chunk warning. Browser inspection of the latest editor UI was not run in this session; preserve `.ai-runs/**` and `runtime/backups/**` as uncommitted artifacts. After the baseline commits, the user plans to start another UI refactor.

**2026-10-23 continuation update:** F11–F13 fixes are implemented in the existing WorkflowDefinitionService / Task Runtime path. Independent review found malformed persisted graph summary/checksum cases and a concurrent omitted-version replay race; these fixes have focused regressions. Final independent review also identified checksum blindness to declaration reorder when that reorder changed tie-break execution order; preserve the historical order-independent checksum contract and make execution ordering deterministic by node key, with a regression asserting both are invariant to reorder. Focused Workflow tests after all three review-fix rounds: 33 passed / 12 warnings. Final full SQLite rerun including these fixes passed: **1048 passed / 12 skipped / 74 warnings / 738.79s / exit 0**; the preceding 1043 passed / 12 skipped / 72 warnings / 600.67s run is historical. Frontend: 227 passed; typecheck, lint, build, Ruff, format, OpenAPI, i18n and diff checks passed. Real Chromium 151 with Playwright 1.62.0 used the dedicated `/tmp/aiqa-f11-f13-chromium.db`: created/published/launched a project-owned `failure.collect` Workflow; task `3904cb6436e1430ebfb8ba3f29baf5d7` and its step completed, with PytestTraceback evidence visible; page and console errors were empty. Screenshots: `.ai-runs/rc-hotfix2-live-acceptance/screenshots/f11-f13-workflow-published.png` and `f11-f13-execution-tree.png`. PostgreSQL 16 remains BLOCKED (no isolated server/runtime/test URL); overall verdict remains PARTIAL. Independent review confirmed no remaining actionable findings after the deterministic execution-order fix. Current HEAD remains `a732cb1e4895fcf580ee430c1126e4fd7510af54`; F11–F13 and acceptance updates are uncommitted; existing user changes, `.ai-runs/**`, and `runtime/backups/**` are preserved. Do not push, merge, or deploy.

**当前活动轮次：RC Hotfix 2 + F11–F13 remediation（实现、定向/全量 SQLite 回归、独立复评完成；PostgreSQL 通道 BLOCKED；待按 Finding 边界提交）。** 复用既有 Task Runtime、scheduler、lease/cancel/recovery 与 Execution Trace；没有新增 Runtime/Agent/Provider/Workflow 节点。基线 HEAD `a732cb1e4895fcf580ee430c1126e4fd7510af54`；工作树含此前 RC 改动和本轮修复。F1–F13 均有实现/回归映射；F11–F13 复评状态见 `.ai-runs/rc-hotfix2-live-acceptance/finding-registry.md`。上一轮 SQLite 全量（最终 reviewer edge fix 之前）**1043 passed / 12 skipped / 72 warnings / 600.67s / exit 0**，输出 `.ai-runs/rc-hotfix2-live-acceptance/sqlite-f11-f13-final.log`；前端 **227 passed**，typecheck、ESLint、production build、Ruff、411-file format、i18n（25 namespaces / 3398 keys）、OpenAPI、`git diff --check` 通过。真实 Playwright 1.62.0 / Chromium 151 UI 使用专用 `/tmp/aiqa-f11-f13-chromium.db`：创建、保存、发布并启动 `failure.collect` Workflow；Execution Tree 显示 task `3904cb6436e1430ebfb8ba3f29baf5d7` 与 collector 步骤完成及 PytestTraceback evidence，page/console errors 为空。截图在 `.ai-runs/rc-hotfix2-live-acceptance/screenshots/f11-f13-*`。PostgreSQL 16 因无隔离服务/runtime/test URL 而 BLOCKED，整体判定 PARTIAL。保留既有工作、`.ai-runs/**` 和 `runtime/backups/**`；不得 push/merge/deploy。

**上一轮：RC Freeze（用户任务 m07860，记录见 §3.23，报告 `.ai-runs/overnight-delivery/RC-BASELINE.md`）。**本轮零产品改动，只做冻结/审计/交接：确认冻结树（代码 `b8958e2`、HEAD `279ccd2`、35 笔未推送）、把每个数字对应到 revision 与证据文件、扫描新增行里的凭据（只有两处演练/本地一次性口令）、实跑备份→恢复（44/44 表一致）与迁移往返（空库 → `0021` / 44 表、基线 downgrade 有意不清空、逐级降级才是受支持路径）、建立本地可恢复标记（tag `rc-2026.10.22` + `runtime/backups/aiqa-rc-2026.10.22.bundle`）、列出三个发布阻断（B1 DAG 执行路由、B2 cancel 未 fencing、B3 远端 CI 与部署回滚）与下一阶段最小修复清单。该轮在冻结树复跑前端 227 pass 与真实 Chromium 24/24。五级判定：核心产品 PASS、Studio PASS、DAG 执行 BLOCKED、多实例 BLOCKED、发布候选 BLOCKED。最终工程收尾见 §3.22。

**上一轮：最终工程收尾（用户任务 m07699，记录见 §3.22）。**给后端套件加挂死防护（`pytest-timeout` 2.4.0，默认 180s / `timeout_method = "thread"`，真实浏览器 e2e 单测标 900s），并用真实耗时（最慢 166.82s）决定阈值，双向验明：10.9s 的用例在 `--timeout=2` 下被终止，168.8s 的 e2e 在 `--timeout=30` 下靠自带标记存活。同时判定并只修一个**测试侧**竞态（0.5s 预算在 setup 阶段就被耗尽 → 无东西可取消，产品侧 `run.timeout`/TIMEOUT/`ANALYSIS_TIMEOUT` 全部正确），预算改 5s、等待改 10s。最终代码上双通道全量：SQLite **996 passed / 11 skipped / 890.37s / exit 0**，PostgreSQL 16 全量（与 SQLite 同范围 `apps/api/tests packages`）**999 passed / 8 skipped / 2066.93s / exit 0**；旧回归记录已按真实 revision 分类，中断/参数错误的记录标为无效。五级判定不变：核心产品 PASS、Studio PASS、DAG 执行 BLOCKED、多实例 BLOCKED、发布候选 BLOCKED。上一轮 Round 17 复核审计见 §3.21。

**Round 16（上一轮，用户任务 m03748，记录见 §3.13，设计文档 `docs/DISCOVERY_INTELLIGENCE.md`，真实验收 `.ai-runs/e2e-round16/acceptance.json`）。** 本轮在 Round 15 的结构化证据之上，只让 AI/Jev 分析确定性规则无法判定的场景（`CANDIDATE_GAP` / `UNDETERMINED` / 显式重分析），把结果作为独立、可审核的建议层写入 `discovery_suggestions`，不覆盖 `discovery_scenarios` 的规则判定；虚构 evidence_id 或 case_id 直接拒绝并留原因，Provider 降级不落任何建议文本，人工批准才生成用例。真实 Chromium 验收 28/28、真实 provider（`mimo-v2.6-flash`）与真实 Jev（`jev-1.13.0`，score 0.505 / confidence 0.90）均走通；后端/前端全量见 §9。

**Round 15（上一轮，用户任务 m02941，分支 `audit-remaining-blockers`，记录见 §3.12，数据契约 `docs/DISCOVERY_EVIDENCE.md`，真实验收 `.ai-runs/e2e-round15/acceptance.json`）。** 本轮把 Discovery 从「探索并生成结果」升级为「采集结构化事实 → 确定性去重/关联 → 增量对比 → 证据到候选场景到用例的追踪」，并把指标接进既有画布节点详情；不新增执行能力、不做 AI 判定。5 笔代码提交 + 本文档提交；真实 Chromium 21/21、`console_errors: []`；前端 201 pass；后端全量见 §9。

**Round 14（上一轮，用户任务 m02243，分支 `audit-remaining-blockers`，记录见 §3.11，真实验收 `.ai-runs/e2e-round14/canvas-acceptance.json`）。** 本轮在既有 Workspace 内用 React Flow 把真实记录投影成一条只读流水线（发现 → 录制 → 编辑 → 运行 → 失败 → 分析 → 人工批准 → 精确验证），不新增执行能力、不改 Recorder/Studio/修复链。2 笔提交（`9fd04df` 后端投影层、`bf9b5c2` 前端画布）+ 本文档提交；真实浏览器 16/16、`console_errors: []`。

**Round 13（上一轮，分支 `audit-remaining-blockers`，记录见 §3.10，Before/After 实测数据 `.ai-runs/e2e-round13/{before,after}/audit.json`）。** 本轮不新增产品能力、不重构既有闭环，只在已通过的闭环上修用户体验与一致性：同一个“完成”在不同页面表达一致（修复链统一）、录制器与录制步骤可从可见 UI 到达、跨页面上下文不丢、消除重复/矛盾信息。共 4 笔提交（`0cc6abd`、`800bc5d`、`99a2509`、`32f22a3`）。审计口径：同一个 Playwright 脚本 `.ai-runs/e2e-round13/audit.py` 在改动前后各跑一次（Before 1/5（4 项 FAIL）→ After 6/6 PASS，控制台错误 0）。

**Round 12（上一轮，分支 `audit-remaining-blockers`，记录见 §3.9，独立报告 `.ai-runs/e2e-round12/audit-report.md`）。** 本轮目标不是堆砌新功能：先逐项复核五项「声称已完成」的能力（D1/D2 分析生命周期、Recorder→Studio 真实数据、Discovery 进程内任务、真实 AI Provider 成功路径、密钥轮换恢复演练），再只修被证实的缺陷（3 笔提交：用户停止探索落 `BLOCKED`、`ai_invocations` 永久 `RUNNING`、开发启动器被 `TIME_WAIT` 骗着换端口），最后在最终代码上用真实 Chromium + 真实 AI/Jev 跑通 `Discovery → Recorder → Studio → Save → Run → Debug → AI 分析 → 人工批准 → 精确验证`（旅程 A 16/16、B 17/17、C 10/10，控制台错误 0）。判定：核心用户路径 **PASS**；多实例一致性、部署/回滚、CI、PostgreSQL 仍为 **BLOCKED**（不计入 PASS）。

**Round 11（上一轮，用户任务 m00041，分支 `main`，记录见 §3.8）。** 本轮目标不是堆砌新功能，而是让平台达到“日常可用、核心流程连续、错误可恢复、结果可验证”。已完成：D1/D2 统一分析生命周期（持久化状态为权威、可取消/可重试/有界超时/重启收敛）、高负载 `TargetClosedError` 根因修复、Recorder→Studio 数据级集成、运行/质量页上下文连续、失败文件:行号持久化、Discovery 接入 TaskRuntimeService、无页面对象引导、产物项目隔离、覆盖率口径统一、迁移往返与备份恢复/密钥轮换演练；其中 D1/D2 的分析结论已从“后端上下文即可复现”升级为 真实浏览器 + 真实 AI Provider 的实测证据（§3.8）。

**结论与未完成项**：见 §9（最后执行的测试）与 §3.8“本轮未解决 / 边界”。

**纠正历史漂移（重要）**：本文档 §3.4–§3.7、§7、§8 中大量“系统级 project ACL 未完成 / P0 ACL 缺失 / `ArtifactORM` 无 `project_id` / 覆盖率两套口径 / ArtifactORM 未隔离”的记载均为 **2026-10-19 之前的历史状态**，现已被：`b6bb5fc`（ACL 第一版 + 迁移 `0013_project_ownership`）、Round 7 的补齐（`test_design` 解析器、`resource_query_access`、git 路由、stream-ticket）以及本轮 `19f7e33`（制品级 `project_id`/`created_by` + 资源访问守卫，迁移 `0015_artifact_ownership`）与 `31450a3`（覆盖率唯一口径）**取代**。仍待产品/安全决策的只是 **legacy ownerless project 的认领规则**（当前策略：管理员可见，不静默分配 owner）。后续 Agent 请以本节与 §3.8 为准，不要把历史段落当成现状。

Round 10（用户任务 m01913，质量发现“生成用例/需求/脚本”可用性修复）已交付，明细见 §3.7。

Round 9（用户任务 m01734，Release Candidate 与真实 QA 产品验收）结论 **PARTIAL**，报告见 `docs/RC_ACCEPTANCE.md`（绑定 SHA `3cbd2a8`）；其中 D1–D6 与本轮的对应关系：D1/D2 已在 Round 11 修复（§3.8），D3（文件:行号）已修（`6a851ac`），D4（上下文丢失）已修（`c74789f`），D5（结果摘要薄）与 D6（Studio 无录制入口）属 UX 取向项，本轮只完成了 Recorder→Studio 的数据级集成，未重做摘要层。

Round 8（用户任务 m01373，全平台 UI/UX 工作台改造）已交付为 `23e73ab`（分支 `agent/ui-workspace-redesign`，未合并 main），结论 PARTIAL，明细见 §3.5。

Round 7（用户任务 m00227，Quality Discovery 实时可视化探索引擎）已提交至 `d8b332d`（分支 `agent/discovery-live-engine`，未合并），仅剩最终 A–F 报告与三项未验证验收项；详细进度见 §3.4。

Round 6（用户任务 m06679）结论 **PARTIAL** 保持有效，是本分支的起点基线（§3.3）。用户任务 m00001/m00002 与 m01734 为同一份「Release Candidate 与真实 QA 产品验收」六阶段验收任务；它曾因 m00227 暂停，现已由 m01734 重新下发并处于**活动**状态。

历史（Round 3，用户任务 m00157）：已完成本轮可交付范围：审计发现/需求/场景/用例/自动化/执行/覆盖关联，修复已证实的状态与项目绑定缺陷；用受控 loopback 网站、真实 Chromium/BrowserRuntime、真实 Playwright worker、临时 API/Vite 与实际 UI 点击验收 Discovery → Quality Map → 风险/场景 → 用例 → binding → Run → coverage。新证据位于 `.ai-runs/night-continuation/round-3/evidence/`。旧 Studio/Round-2 成果为历史，不重复实施。

仍需独立排期的 P0：平台全局 project-resource ACL 缺失（已在 Round 7 分支实现第一版，见 §3.4；legacy ownerless project 认领策略仍需产品/安全决策）。

## 2. Git 状态

| 项 | 值 |
| --- | --- |
| Round 14 起点 | `c756994 docs(handoff): record the case-to-recorder entry in the Round 13 audit`（Round 13 收尾） |
| Round 15 起点 | `1b19ca1 fix(canvas): keep the pipeline legible instead of shrinking it to fit`（Round 14 收尾） |
| Round 16.5 起点 | `254a41e docs(handoff): record the Round 16 evidence-driven suggestions and their acceptance numbers`（Round 16 收尾） |
| 当前 HEAD | `53b7276`（R22 发布候选）→ `0f11fa3`（R17 复核审计修 P1）→ `460cf3e`（PG 记录修正）→ `b8958e2`（最终工程收尾）→ `279ccd2`（冻结最终回归记录）→ `a17275d`+`6e2705b`（RC Freeze：验收复跑 + 基线报告）→ `9785688`（RC Hotfix 1：取消请求/终态分离）+ 本文件提交 |
| 未推送提交 | `origin/main..HEAD` = 39 笔（含 Hotfix 1 代码 + 文档）（本任务默认不 push；RC Freeze +2、Hotfix 1 = 代码 + 本文件） |
| RC 标记 | annotated tag `rc-2026.10.22`（指向 RC Freeze 基线，**不动**）+ 另建 `rc-2026.10.22-hotfix1` 标在本轮提交上（仅本地）；可恢复副本 `runtime/backups/aiqa-rc-2026.10.22.bundle`（自包含 git bundle，62 MB，`git bundle verify` → "The bundle records a complete history"，脱离远端也能恢复） |
| 迁移 | `0019_workflow_definitions`（R17）→ `0020_task_lease`（R18）→ `0021_artifact_actor_width`（R20）→ `0022_task_cancel_request`（Hotfix 1，`agent_tasks.cancel_requested_at/by`，可逆） |
| 本轮证据目录 | `.ai-runs/overnight-delivery/`（`plan.md`、`status.json`、`decisions.md`、`blockers.md`、`rounds/`、`regression/`） |
| Round 16.5 HEAD（历史） | `ec5bae8`（Round 16.5 的 3 笔：`23cdb71` 执行轨迹契约与只读投影、`4dba380` 前端执行树、`ec5bae8` 契约与数据缺口文档；本文档提交在其后） |
| Round 16.5 提交数 | 3（`23cdb71`、`4dba380`、`ec5bae8`）+ 本文档提交 |
| Round 16 关键提交（历史） | `c4075a1` 及前 6 笔（`b6d635a` 分析与分级、`8af0de4` 画布视图、`84b2163` 通用 locator 修正、`a7bbaf4` 设计文档、`7fb03d3` 画布测试、`582f5c9` OpenAPI 导出） |
| Round 16 提交数 | 6 代码/文档提交 + 本文档提交 |
| Round 15 提交数 | 5（`8fd6160` 证据层、`d2af796` 画布指标、`e9f2951` 元素链接修正、`589e6ab` 采集会话收进仓储、`6e8709b` 文档） |
| Round 14 提交数 | 2（`9fd04df` 后端只读投影层、`bf9b5c2` 前端画布）+ 本文档提交 |
| 历史起点（Round 12/13） | `5849b5f docs(handoff): record the Round 11 final regression and its verdict` |
| Round 13 提交数 | 4（`0cc6abd` 统一修复链、`800bc5d` 录制入口与录制步骤、`99a2509` 上下文与文案一致性、`32f22a3` 用例把上下文交给录制器） |
| 工作树 | 干净；仅未跟踪的 `.ai-runs/**` 验收证据与 `runtime/backups/`（保留、不暂存、不提交；`.ai-runs/overnight-delivery/` 例外，作为本任务交付证据入库） |
| 迁移 | `0016_discovery_evidence`（Round 15）→ `0017_discovery_suggestions`（Round 16）→ `0018_ai_invocation_step`（Round 16.5，只加 `ai_invocations.step_id` + 一个索引，可降级） |
| Round 16 关键提交 | `b6d635a` AI 分析 + Jev 分级 + 审核 API（迁移 0017）；`8af0de4` 画布 Evidence Intelligence 视图；`84b2163` 通用 role locator 不再当作覆盖证据 |
| Round 14 关键提交 | `9fd04df` 只读投影层 + ACL + 截断；`bf9b5c2` 阶段列画布、节点详情与证据、窄视口从第一阶段起、URL 指定文件优先于未绑定空态 |
| Round 12 关键提交 | `860f4f2` 用户停止探索 → `CANCELLED`（原 `BLOCKED`）；`abe6a2a` 启动时回收死进程留下的 `RUNNING` AI 调用；`2eb6901` 启动器不再把 `TIME_WAIT` 当端口占用（新增 `test_dev_launcher_ports.py`） |
| Round 11 关键提交（历史） | `5eb2376` 分析收敛到持久化终态；`7aac715` 失败页恢复/取消/说明；`e460213` SQLite WAL（长 SSE 不再阻塞写者）；`7b82832` 工作台跟随/取消分析；`32a5b19` 生命周期回归测试；`ffa7ad2` 浏览器会话在标签页关闭后存活；`6a851ac` 失败源文件:行号（迁移 0014）；`c74789f` 工作台外上下文连续；`507c59d` 录制步骤进入 Studio；`e1f3fdb` Discovery 接入 TaskRuntimeService；`2d642e3` 无页面对象引导；`df4d709` 长生成超时；`19f7e33` 产物项目隔离（迁移 0015）；`edcde0a` 探索网络请求观察；`31450a3`/`2ab2874` 覆盖率口径统一；`bf8aa31` 恢复脚本目标库与快照；`62a2f06` 文档；`be6ec64` 评审三条 finding 修复；`89eb5ed` 暂停任务回队列 + 暂停运行无副作用（评审复评 A/B/D） |
| 迁移链 | `0013_project_ownership` → `0014_failure_source_location` → `0015_artifact_ownership`（本轮新增后两者，均连续、可升降） |
| 远程 main | Round 13 收尾已推送（`d8a2eef..c756994`，非 force）；Round 14 的 3 笔（`9fd04df`、`bf9b5c2`、`bfffa2f`）**未推送**，未合并 |
| CI | `.github/workflows/ci.yml` 存在；最近一次运行在 `d8a2eef` 上失败 4 条后端用例，那 4 条在当前 HEAD 本地重跑 **14 passed**；本轮修订从未在 CI 上运行（任务禁止推送）→ 记为 BLOCKED，改以本地等价门禁取证（见 `.ai-runs/governance/deploy-ci-evidence.json`） |

历史轮次提交基线（Round 3–10）见 `git log` 与 §3.1–§3.7；上一轮验收绑定 SHA 为 `3cbd2a8`，Round 8 交付于 `23e73ab`，Round 7 位于 `b6bb5fc`→`d8b332d`。
| 更早基准 | `02c5f3c` |
| D5 实现提交 | `6b56261 feat(discovery): refresh coverage after test execution` |
| Round-2 D5 final-report/handoff commit | `7cac0be`（历史基线；详见 `git log`） |
| Project-ACL architecture-audit commit | `7ca6e19 docs: record project ACL blocker and next stage` |
| Studio 本轮基点 HEAD | `7cac0be55118992b551c72ad184cb236dbe29699` |
| Studio 源码/测试提交 | `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5` (`fix(studio): restore responsive debug workspace`) |
| 最近 AI Disabled 修复提交 | `1720bf3 fix(ai): keep read APIs available when provider is disabled`，父提交 `1ffbaf6` |
| 当前工作分支 | `main` 已合并 `agent/ui-workspace-redesign`（fast-forward，main 现为 `15abcf8`；`origin/main` 仍为 `d8a2eef`，**尚未 push**） |
| main 合并 | `15abcf8`（fast-forward，无 merge commit；合并后 main 工作树与已验证分支树 `31297f9` 完全一致） |
| Round 9（RC 验收）验收 SHA | `3cbd2a8 test(discovery): assert the frame origin, not the exact start URL`（本轮所有自动化门禁在此提交上重跑） |
| Round 8 提交 | `1fb35a5`（设计系统强制测试与字体/变量修复）、`2f69d34`（工作台上下文筛选与 pane resize）、`f77c046`（Studio 底部 Dock 可拖拽/键盘）、`23e73ab`（handoff 记录） |
| Round 7 分支 | `agent/discovery-live-engine` 停在 `d8b332d`，未合并 |
| Round 7 起点 | `b6bb5fc feat(security): scope API access to a caller's own or shared projects`（P1 project ACL 第一版，含迁移 `0013_project_ownership.py`） |
| Round 7 后端提交 | `534c252 feat(discovery): live observation stream, viewport frames and element geometry` |
| Round 7 前端提交 | `6567f43 feat(web): live Quality Discovery workbench` |
| Round 7 本轮收尾 | E2E 验收测试 + 文档 + 格式化/OpenAPI 修正（提交见 `git log` 顶部；仍未 push） |
| Round 7 文档 | `docs/QUALITY_DISCOVERY.md`（新增，`[CURRENT]`）、`docs/SECURITY.md` §5、`docs/README.md` 索引 |
| 另一本地分支 | `agent/wsl-continuation` 仍在 `b6bb5fc`，未合并 |
| 当前工作树 | Round 6 代码已本地提交（`f2dd186`）；`docs/agent-handoff.md` 在本次提交后更新；`.ai-runs/night-continuation/` 证据为本地未跟踪文件，保留且不暂存。 |
| Round6 本轮提交 | `f2dd186 fix(ui,integrations,audit): surface async failures and stop simulated publish successes` + 本轮 handoff 提交（仍未 push） |
| Round5 本轮提交 | `71f6f14 fix(db,worker,security): make PostgreSQL migrations and worker recovery reliable` + `a8c21a1`/`e1496c3` |
| Round6 验收报告 | `.ai-runs/night-continuation/final-report.md`（15 节；判定 PARTIAL）、`round-6/`（审计原文、错误面截图、页面矩阵） |
| Round4 本轮提交 | `38a89cb fix(failures): surface the assertion detail in the failure summary`、`01518a2 test(e2e): capture round 4 route, viewport and interaction evidence` |
| 本轮 Studio evidence | `.ai-runs/night-continuation/round-1/attempt-19/`（真实 Chromium/debugpy acceptance、响应式截图与日志） |
| Round4 evidence | `.ai-runs/night-continuation/round-4/evidence/{before,after}/`（本地未跟踪） |
| 远程 main | 未修改、未合并 |
| 远程 | 已 fetch，无本地领先/落后意外差异（工作分支为新增本地骨架） |

## 3. 当前开发阶段

Round 11（2026-10-19，用户任务 m00041）：核心工作流收敛与稳定性整改 —— P0（D1/D2 分析生命周期、高负载 `TargetClosedError`）、完整工作流贯通（Recorder→Studio、上下文连续、精确源定位、人工批准修复链路）、Discovery 接入 TaskRuntimeService 与观察体验、工程与安全治理（产物隔离、覆盖率口径、迁移往返、备份恢复/轮换演练）、最终产品级验收。**详细记录见 §3.8**（本轮不再有“待启动”的阶段）。

Round 10（2026-10-19，用户任务 m01913）：质量发现“生成用例/需求/脚本”可用性修复，见 §3.7。

Round 5（2026-10-17，用户任务 m05655）：企业级可靠性、PostgreSQL、Worker 与安全整改，详见 §3.2。

Round 4（2026-10-17，用户任务 m01676）：全局 QA 工作台 UX 复核与证据化改造，详见 §3.1；Round 3 成果与结论保持有效，未回退。

Round3 接管（2026-10-17）：初始 HEAD `e6734c7`；保留既有 Round2 代码与 `.ai-runs` 证据并纳入实现提交 `f64f711`。审计覆盖 `Requirement → TestDesign/TestScenario → TestCase → AutomationBinding → TestRun/TestExecution → Discovery Coverage`；现有实体能表达链路，无需重复 schema。修复 latest execution projection、foreign-workspace binding、Discovery draft 风险/结构化场景、case navigation/selection；并完成继承的 verification freshness/rollback recovery（durable `ROLLBACK_PENDING`、proposal identity match、rollback-event dedupe）。

最终验收（commit `f64f711` 后源码未再修改）：`python scripts/task.py test` → **834 passed / 10 skipped / 55 warnings / 474.19s**；Web **160 passed**，typecheck、ESLint、build 均通过；`python scripts/task.py lint` → Ruff、428-file format、i18n（25 namespaces/3025 keys）、OpenAPI、ESLint 全通过。最后单独重跑实际 Chromium E2E → **1 passed / 13.32s**。受控 loopback 站点探索、UI 草稿/场景审阅/用例生成与选中、UI 手工 ACTIVE binding、UI 发起真实 Playwright PASS、Quality Map 刷新重载 VERIFIED、项目切换隔离均有证据。Independent final review found no remaining blocker; ACL/PostgreSQL limits见 §8。实现已本地提交，不推送、不提交 `.ai-runs`。
历史基线：Automation Studio Round-1 attempt 19 已提交于 `63ae3027ec1632b0dbaa3e8e1298147247d4e4b5`；本节以上 Round3 测试结果是其后最新结论，旧 Round-2 的 17 个主流程 + 14 个失败/幂等检查不能代替本轮证据。

本轮修复/完善：
- `apps/api/tests/conftest.py` 的 client fixture 使用 teardown 恢复 workspace path；opt-in UI test 的 AI/Jev health probes 在测试期显式 disabled，并在 `finally` 恢复全局 config/runtime，避免外部请求和测试污染。
- `apps/web/src/index.css` 与 `apps/web/src/features/workspace/workspace.css` 修复 debug 页面 flex sizing；Monaco 编辑器从 5px 高恢复为桌面 161px、平板/手机至少 140px。
- `DebugPanel` 在手机改为纵向可滚动详情；桌面/平板保留三栏。测试覆盖手机滚动到调试控制台且无 document 横向溢出。
- 新增 `apps/api/tests/test_studio_debug_ui_live.py`：真实 Vite/Uvicorn/Chromium/Playwright 1.62.0 和 debugpy DAP，无 DAP mock。真实编辑/保存、断点、Step In/Over/Out、Continue、重复会话、Pause/Stop 和真实失败 Run 均验收通过。

最新 opt-in acceptance attempt 19：**2 passed / 32.10s**；3 个 debug sessions 均 `CLOSED`，合成 Playwright 失败 Run 为 `FAILED` 且 trace 保留，API/console errors 为空。真实 Python 语义：Step Out 停在 `calculate:11` 时 assignment 尚未存入 `intermediate`；再 Step Over 后才断言 `intermediate == 41`。Before/after、断点、桌面/平板/手机、手机 console 截图位于 `.ai-runs/night-continuation/round-1/attempt-19/screenshots/`。

Reviewer 发现的 config/workspace teardown、手机布局和 document-width assertion 均已修复；attempt 19 与最终全仓回归通过。最终复审确认无其他 finding；Round-1 reports 已更新，本地 commit 待完成。历史 D5/ACL/Docker/PostgreSQL/Worker 状态见 `.ai-runs/enterprise-continuation/round-2/`。

## 3.1 Round 4（全局 UI/UX 评审与改造，m01676）

范围：复核既有 IA（`apps/web/src/app/routes.tsx`、`apps/web/src/app/navigation.ts`、`apps/web/src/features/workspace/WorkspacePage.tsx`）并用真实 Chromium 逐页巡检；不新增第二套 Runtime/Agent/Provider，未替换既有功能。

证据（本地未跟踪，保留不提交）：

- 基线：`.ai-runs/night-continuation/round-4/evidence/before/`
- 改造后：`.ai-runs/night-continuation/round-4/evidence/after/`（75 个文件；`page-matrix.json` 61 条 = 14 条路由 + 40 条响应式 + 7 个需求标签页）
- 视口 1920×1080 / 1440×900 / 1366×768 / 390×844；每个视口断言 `scrollWidth <= innerWidth`。

真实交互（非纯截图）：侧栏「项目管理」点击导航、需求知识关系图搜索空态/类型筛选/适配画布/节点聚焦/来源文档展开、Failure「查看原始错误」展开、Studio 通过 `?file=` 打开绑定文件、Failure 深链启动真实 debug 会话（`POST /api/debug/sessions` 200，返回 `workspace_id`/`nodeid`/`failure_id` 与 fixture 一致，状态 `STARTING`）。

本轮唯一产品修复（独立 reviewer P2）：失败概览此前只显示「测试断言未通过。」，真实断言文本只能展开原始详情才看得到。现在断言类失败在通用标签下追加一行 `实际错误：<error_message 最后一行>`（>180 字符截断），分类、诊断信任策略和后端行为不变。

- `apps/web/src/features/failures/failureWorkspaceModel.ts`：新增 `failureErrorPreview()`
- `apps/web/src/features/failures/FailureOverview.tsx`：仅 `assertion` 摘要渲染该行
- `apps/web/src/i18n/locales/{zh-CN,en}/failures.json`：`summary.errorDetail`
- `apps/web/src/index.css`：`.failure-error-detail` 与 `.failure-root-cause` 同排版
- `apps/web/tests/failure-workspace-model.test.mjs`：多行取末行、超长截断、纯空白返回空串

reviewer 另一条（Studio「工作区尚未初始化」死路）**无法复现**：1440 截图与 API 都显示文件树完整、绑定文件 `tests/test_discovered_search.py` 在 4 个视口均渲染真实源码，因此不改该状态，只记录结论。

E2E 巡检 harness（`apps/api/tests/test_discovery_coverage_e2e.py`）稳定性改动：

- `ROUND4_SCREENSHOT_PHASE=before|after` 选择证据目录，避免覆盖基线截图。
- `_goto_app()`：Vite 冷启动偶发空白壳时重载（最多 3 次）。
- `_shot()`：全页截图偶发卡在 Playwright 的 `waiting for fonts to load`，同图重试 3 次。
- 浏览器 context 阻断 `fonts.googleapis.com` / `fonts.gstatic.com`：本机网络不可达会让 `document.fonts.ready` 永不完成；阻断后字体回退，截图确定。这是测试环境限制，不是产品缺陷。
- 断言改为比较 `.view-lines` 的 `textContent` 并去掉全部空白：390px 下 Monaco 自动换行会让 `innerText` 插入换行，旧断言因此误判「文件未渲染」。
- debug 会话监听移到真正导航的 `page`；响应式巡检的 debugger 使用不带 `nodeid` 的 URL，避免每个视口各起一个 debugpy 并拖死 teardown。
- 失败 fixture id 缩短到 35 字符内（原合成 id 触发 API 校验失败，debugger 深链因此报 `Request validation failed.`）。

## 3.2 Round 5（企业级可靠性、数据库、Worker 与安全整改，m05655）

范围：真实 PostgreSQL 兼容性、Worker 任务可靠性、后端安全加固、CI/WSL 约束与能力缺口评估。要求「先证据、后结论」，不得用 SQLite 结果冒充 PostgreSQL 验收，不做纯 UI 的"企业功能"，不新增第二套 Runtime/Agent/Provider。

### Part 1 — PostgreSQL（不再是 BLOCKED）

本机无系统 PostgreSQL / Docker，但通过 **隔离的本地开发实例** 完成了真实 PostgreSQL 验收，未做任何系统级安装或配置修改：

```bash
test -d /tmp/sock-aiqa || mkdir -m 700 /tmp/sock-aiqa
uv venv /tmp/pgvenv --python 3.13 && /tmp/pgvenv/bin/pip install embedded-postgres==18.6.3
/tmp/pgvenv/bin/python -c "import embedded_postgres as ep; ep.initdb(['-U','postgres','-D','/tmp/pgdata-aiqa','-A','trust','-E','UTF8'])"
/tmp/pgvenv/bin/python -c "import embedded_postgres as ep; ep.pg_ctl(['-o','-p 55432 -k /tmp/sock-aiqa -c listen_addresses=127.0.0.1','-l','/tmp/pg55432.log','-w','start'], pgdata='/tmp/pgdata-aiqa')"
# 测试库必须放在名字含 test 的数据库：conftest 的 reset_test_schema 会 DROP SCHEMA public，非 test 库直接拒绝运行
/tmp/pgvenv/bin/python -c "import embedded_postgres as ep; ep.psql(['-h','127.0.0.1','-p','55432','-U','postgres','-d','postgres','-c','CREATE DATABASE aiqa_test'])"
AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test uv run pytest apps/api -q
```

PostgreSQL 18.6 监听 `127.0.0.1:55432`（datadir `/tmp/pgdata-aiqa`，socket `/tmp/sock-aiqa`，trust 认证，用户 `postgres`，测试库 `aiqa_test`）。抛出的 `/tmp/pgvenv` 与 datadir 都是临时目录，仓库 lockfile 与系统未变。CI 的 `postgres:16` service job（`.github/workflows/ci.yml` → `backend-postgres`，本轮已把它的 `POSTGRES_DB`/URL 改为 `aiqa_test` 以配合下面的防护）仍未在本地跑过，本地验收针对 18.6。

修复的真实兼容性/迁移缺陷：

1. **PostgreSQL 无法迁移（阻断级）**：Alembic 建 `alembic_version.version_num VARCHAR(32)`，而 3 个 revision id 超长（`0004_one_running_failure_analysis` 33、`0005_raise_ai_request_preflight_budget` 38、`0010_locator_repair_state_machine` 33），`alembic upgrade head` 直接 `StringDataRightTruncationError`。SQLite 不校验声明长度所以本地一直看不见。修复：`apps/api/app/persistence/migrations.py` 新增 `ensure_version_column_capacity()`（SQLite 直接返回；否则 `CREATE TABLE IF NOT EXISTS` + `ALTER COLUMN ... TYPE VARCHAR(128)`），由 `upgrade_database()` 与 `apps/api/alembic/env.py` 调用。
2. **测试库初始化在 PG 上不可用**：`Base.metadata.drop_all()` 对循环 FK（`test_runs.origin_failure_id ↔ failure_records.run_id`）抛 `CircularDependencyError`。`apps/api/tests/conftest.py` 新增 `reset_test_schema()`：PG 用 `DROP SCHEMA public CASCADE`/`CREATE SCHEMA public`，SQLite 仍用 `drop_all`；同时把 Alembic head stamp 改成两种后端都执行（否则 PG 上 `/api/health/ready` 报 `not_ready`）。
3. **PG 集成测试自身漂移**：`apps/api/tests/test_postgres_integration.py` 缺少真实 ACTIVE `AutomationBinding`，`executed_cases_recent` 永远为 0；已补真实 binding 并修正分类预期（`FailureService.get_recurrence` 按**存储**分类分组，而 failure payload 由确定性分类器覆盖，两者故意不同）。

新增回归护栏 `apps/api/tests/test_postgres_migrations.py`：起一个临时库 `aiqa_migrations_<hex>`，用 `AUTOCOMMIT` 引擎执行真实 `upgrade_database`，断言 `alembic_version == ScriptDirectory...get_current_head()`，并用 `compare_metadata(MigrationContext.configure(...), Base.metadata)` 断言无 schema drift（只忽略一个已定位的假阳性：`Enum(native_enum=False)` 反射回 `VARCHAR(32)`），最后 `DROP DATABASE ... WITH (FORCE)`。它会在任何未来 revision 与模型漂移时直接失败。

`apps/api/tests/test_backend_parity.py`：`test_platform_sqlite_engine_enforces_foreign_keys` 在 PG 全量运行里失败（同一 `MetaData` 先为 PG 建表后，SQLAlchemy 不再把循环 FK 交给 SQLite 的 `create_all`，因为 SQLite 不能 `ALTER TABLE ADD CONSTRAINT`）；已改为在 PG 下 `skip` 并新增基于真实迁移的 SQLite 级联测试 `test_migrated_sqlite_schema_enforces_project_cascade`（SQLite 生产库由 Alembic DDL 建立，不受该限制影响）。

### Part 2 — Worker 可靠性（真实 worker 进程）

代码修复（`apps/api`）：

- `app/repositories/job_repo.py`：`update_job_status()` 改为单条条件 UPDATE + 回读（`WHERE id=:id AND status NOT IN ('COMPLETED','FAILED','CANCELLED')`）。原读-改-写会让收尾 worker 覆盖取消结果，或把一次判定的 `duration_ms` 和另一次判定的 `error_message` 拼在一起。新增 `list_abandoned_run_ids()`：ASSIGNED/RUNNING 且 `updated_at` 超时、且（无 assigned worker / worker 不存在 / `last_heartbeat_at` 超时）的 run。
- `app/services/job_queue_service.py`：`cancel_job()` 除了取消 job，还会对 QUEUED/ASSIGNED/RUNNING 的 job 调用 `TestRunService.cancel_run(run_id)`。此前 `POST /api/jobs/{id}/cancel` 只改 job 行，Run 永远停在 RUNNING。
- `app/services/test_run_service.py`：新增 `DEFAULT_WORKER_OFFLINE_SECONDS = 600.0`；`recover_stale_runs()` 现在把本地 stale run 与 `list_abandoned_run_ids()`（死 worker 遗弃的 run）合并恢复，逐个 `cancel_active_run` + `cancel_active_jobs_for_run`，并发布 `RUN_CANCELLED`。原实现只扫 `runner_types=["LOCAL"]`，worker 崩溃后 run 永久 RUNNING。

新增两个测试文件：

- `apps/api/tests/test_job_reliability.py`（4 个测试，SQLite 2.71s）：取消 job 必须取消 run；终态不可被覆盖（`asyncio.gather` 同时写 COMPLETED(1500ms) 与 FAILED("worker crashed")，断言不出现字段混搭）；心跳过期 1h 的 worker 遗弃 job 在 `recover_stale_runs(stale_after_seconds=0)` 后 run+job 都 CANCELLED；心跳 5s 的活跃 worker 不被误回收。
- `apps/api/tests/test_worker_process_integration.py`：**真实 worker 子进程**验收（不是 fake httpx），由测试自己起临时 Uvicorn + 真实 `python -m worker.main`：submit → 认领 → 真实 pytest 执行 → 结果持久化 → 状态上报；同时覆盖干净取消（job 取消后子进程停止、Run CANCELLED）、超时击杀、崩溃后恢复、重复请求不重复执行、临时目录与子进程回收。

### Part 3 — 安全加固（真实负向测试）

- 审计确认无系统级 project ACL（见 §8），本轮不假装完成授权，只修可验证的真实缺陷：
- **artifact 任意文件读取**：`app/services/artifact_storage_service.py` 的 `read_artifact_bytes()` 直接打开 `ArtifactORM.storage_path`，没有 containment 校验（`stored_artifacts` 表没有 project_id，任何能写该行的人都能读到进程可读的任意文件）。已加入解析后必须位于 storage root 内的校验；`apps/api/tests/test_security_hardening.py::test_artifact_download_refuses_a_path_outside_the_storage_root` 用真实篡改行断言下载返回 404 且响应体不含文件内容，metadata 仍可读。
- **AI 修复缺审计**：apply/rollback 会写用户仓库，却只有认证/用户/团队操作写审计。`app/api/failures.py` 现在把当前用户传给服务，`app/services/failure_workflow_service.py` 在 apply/rollback 时写 `SecurityAuditRepository`（`REPAIR_APPLY` / `REPAIR_ROLLBACK`，actor + failure/analysis 目标）。`test_security_hardening.py::test_applying_a_repair_is_recorded_in_the_security_audit` 走真实 HTTP apply + rollback，并从 `GET /api/audit/security` 读出两条审计。
- `config/config.yaml`：worker 的 `workspace_storage_dir`/`artifact_storage_dir` 支持 `AI_QA_WORKER_WORKSPACE_DIR`/`AI_QA_WORKER_ARTIFACT_DIR` 覆盖，`pytest.timeout_seconds` 支持 `AI_QA_PYTEST_TIMEOUT_SECONDS`（默认值不变；仅这样测试才能把执行目录指向临时目录、把超时压到秒级）。
- 仍然存在且未修的 P0：见 §8（无 project ACL；`read_artifact_bytes` 之外的 `storage_path` 写入方均已有 sanitize；pytest 子进程非 OS 沙箱）。

### Part 4 — CI / WSL

- CI（`.github/workflows/ci.yml`）已有 `backend`（SQLite）、`backend-postgres`（postgres:16 service）、`windows`、`frontend` 四个 job，本轮未改 CI 定义；新增测试自然进入 `uv run pytest` 两条 lane。
- WSL 内存 7.9 GB：全量 pytest / Playwright E2E / 前端 build 必须串行执行，并行会 OOM；本轮所有重负载测试都是串行跑的。
- 未升级任何依赖；Playwright 仍固定 1.62.0。
- Windows：worker 子进程测试在非 POSIX 平台走 `process.kill()`（POSIX 用 `os.killpg` 杀进程组），未在 Windows 实机执行 → Windows lane 结果由 CI 给出，本地未验证。

### Part 5 — 能力缺口评估（结论，不改代码）

只评估、只在「已有能力实现不完整」时修复，不新增纯 UI 企业功能：

| 能力 | 现状/证据 | 结论 |
| --- | --- | --- |
| 权限/审计 | 全局 RBAC + 审计表已存在且本轮扩展了修复审计；无 project ACL | 缺口=project 级 ACL（P0，需产品决策） |
| 环境管理 | worker 按 workspace 用自己的 venv（`.qa-platform-runtime`），无宿主机安装 | 已够用，不做 |
| 测试数据 | 无独立数据管理；fixture/DB 隔离已有 | 不做 |
| 并发调度 | `max_concurrency` + 原子 claim；无 lease/heartbeat based requeue | 本轮已修「死 worker 遗弃」；lease 属下一轮 |
| 质量趋势 | Quality Map/覆盖已有，无时间序列 API | 不做（无需求证据） |
| Flaky test | 无检测/重试策略字段被使用 | 未实现，评估为独立需求 |
| AI 预算 | `max_steps`/`max_runtime_seconds` + preflight 预算已有 | 已够用 |
| 运行监控 | run/job 状态、事件、日志、worker 心跳已有；无 metrics/告警 | 不做（无需求证据） |
| CI/CD | 见 Part 4 | 已够用；仅缺 Playwright browser E2E job |
| 扩展机制 | integrations 包预留；无插件生命周期 | 不做 |

### 独立评审（read-only reviewer `del_mvcarjds_lqgs`）

评审覆盖本次全部未提交改动，提出的问题已修复：

- **P1** 修复审计只有两个 analysis 维度路由传了 actor，兄弟路由 `POST /failures/{id}/apply-repair`、`POST /failures/{id}/rollback-repair` 仍记 `actor=system` → 四条路由全部传 `user = Depends(get_current_user)`。
- **P2** `POST /api/runs/recover-stale?stale_after_seconds=-86400` 会把 cutoff 推到未来，把还在跑的 LOCAL run 全部 CANCELLED → 参数改为 `Query(7200.0, ge=60)`。
- **P2** 审计写入失败会把已成功的 apply 变成 500（且因 `PATCH_APPLIED` 状态无法重试）→ `_audit_repair` 改为 log-and-continue；中断恢复分支（patch 已写盘）现在也补写 `REPAIR_APPLY`；rollback 只在真正恢复文件（`FailureService.rollback_repair` 新增 `restored` 字段）时写 `REPAIR_ROLLBACK`，不再为“只对齐状态”的重试记假审计。
- **P2** `reset_test_schema` 会对 `AI_QA_TEST_DATABASE_URL` 指向的任意库 `DROP SCHEMA public CASCADE` → 现在库名不含 `test` 时直接拒绝；CI 的 `POSTGRES_DB`/URL 同步改为 `aiqa_test`。
- **P3** worker `last_heartbeat_at` 为 NULL 时 `NULL < ts` 永远不为真，死 worker 的 run 仍会卡 RUNNING → 改用 `func.coalesce(..., datetime.min)`；`ensure_version_column_capacity` 改为只在 `postgresql` 上执行；新增测试里三个永真的安全断言已修正，终端状态用例补了一个确定性的“二次上报不得改写”断言。

有意未修（记录为剩余风险，不声称完成）：job 状态抢输一方仍拿到赢家行（无法区分“我赢了”与“我输了”，外部 HTTP 契约不变）；`stale_after_seconds` 的 600s floor 使 `DEFAULT_WORKER_OFFLINE_SECONDS` 默认下不生效（保守，人工可调）；修改 `app.artifact_storage_dir` 与 `AI_QA_WORKER_ARTIFACT_DIR` 可以使 worker 产出被 API 静默丢弃（配置脚枪，日志会告警但不会失败）；artifact 路径为相对路径时依赖进程 CWD（历史行为）；启动时的建表/拓宽列在双实例并发启动下可能报重复对象；审计目标未记录文件路径，`ip_address` 仍是硬编码。

## 3.3 Round 6（全系统独立验收、最后整改与最终交接，m06679）

角色：独立验收方（不采信前五轮自述结论）。两份只读审计原文：`round-6/audit-integrity-backend.txt`（跨阶段完整性）、`round-6/audit-integrity-frontend.txt`（前端完整性）。

修复的真实缺陷（提交 `f2dd186`）：

- 四个前端 P1「异步失败被静默」：运行列表加载失败与「没有运行记录」无法区分（`RunsPage.tsx`）；失败队列加载失败显示为空队列（`FailuresPage.tsx`）；发布创建/门禁评估失败无任何提示（`QualityPage.tsx`）；安全页 9 处静默 catch 使 403 表现为空表（`SecurityPage.tsx`）。全部改为 `role="alert"` 可见错误 + 重试。
- 两个后端 P2：`integrations.testrail.enabled: false` 时 Fake 适配器把发布记为审计 `SUCCESS`（现为 `DRY_RUN` + `details.simulated` + `[simulated]` 消息前缀）；登录审计 IP 硬编码 `127.0.0.1`（现在取 `Request.client.host`）。新增 2 条测试，`test_jira_testrail_endpoints.py` 6 passed。

证据：4 个强制失败的真实浏览器错误面（截图 + `round6_error_surfaces`）见 `round-6/evidence/`；全页面矩阵 `page-matrix.json`（61 条：14 路由 × 视口 + 7 需求页签）。

关键验收结果（冻结代码，详见 §9 与 `final-report.md`）：

- 真实浏览器 E2E：**1 passed / 105.49s**，`round6_error_surfaces=["runs","failures","security","release-create"]`，Discovery→Coverage `VERIFIED`，隔离项目未被污染，4 视口无横向溢出。
- Studio Debug 真实验收：**2 passed / 32.65s**（编辑/断点/暂停/继续/停止 + 真实失败证据 + 四视口布局）。
- 真实 AI/Jev：需求→执行→证据链路 **PASSED**（`mimo-v2.6-flash` + `jev-1.13.0`，含低置信度 0.54 的 fallback 阻断）；同时间窗 provider 健康检查超时（`TIMEOUT`，5034ms），因此自动修复被 `_runtime_readiness` 按设计阻断、浏览器内修复未 settle、Live Browser Agent 因 Jev 置信度 0.06 被 `TaskBlocked` → 全部记 **BLOCKED**，未使用 Fake 顶替、未重复烧配额。
- 确定性回归：SQLite **850 passed / 11 skipped / 573.82s**；PostgreSQL **699 passed / 7 skipped / 424.33s**；前端 161 passed + typecheck + build 31.34s；lint 全通过；OpenAPI 契约 current。

本轮未修（记录，见 §8 与 `final-report.md` §13）：P0 project ACL；覆盖率两套口径；浏览器内失败修复链路待 provider 恢复后单次复验；审计字段不完整；job 结果竞态仍以成功响应返回。

## 3.4 Round 7（Quality Discovery 实时可视化探索引擎，m00227）

分支 `agent/discovery-live-engine`（从 `b6bb5fc` 起）。设计原则：不新建第二套浏览器/Agent/Provider，复用 `BrowserRuntime`、`DecisionService`(Jev)、`EventBus`/SSE、stream ticket、`ArtifactStorageService`。新文档：`docs/QUALITY_DISCOVERY.md`。

已实现并已本地提交：

- **P1 project ACL 第一版**（`b6bb5fc`，迁移 `0013_project_ownership`）：`ProjectORM.owner_id/team_id` + 路由资源解析守卫，非成员一律 404（不暴露项目存在性），admin 全通过。新增 `test_project_acl.py`（6 条），并按新语义修正 `test_authorization_rbac.py`（VIEWER 读项目改判 404，新增 `_assign_owner` 预置）。已知迁移影响：QA_LEAD/QA_ENGINEER 不再能访问既非自己拥有也无 team 的项目。
- **实时观测流 + 帧 + 元素几何**（`534c252`）：`app/services/quality_discovery_live.py`（`DiscoveryLiveHub` 只做 fan-out，`result["events"]` 仍是唯一事实来源）；`GET /api/discovery/runs/{run_id}/stream`（SSE，复用 `event_frame` 与 stream ticket，新增 `discovery` kind + `is_stream_route`/`stream_ticket_scope` 分支）；`BrowserRuntime.capture_frame`（仅视口 JPEG q55/1s 超时，只在有订阅者时抓帧，绝不阻塞动作）与 `paint_highlights`（页内 `HIGHLIGHT_SCRIPT` 叠加层）；`collect_controls` 现返回 `bounding_box`/`in_viewport`/`visible_ratio`；`element.inventory`/`action.planned` 等事件；`live_frame_interval_ms` 配置（默认 1000）。
- **AI 降级**（同一提交，关闭 Round 6 遗留 P2）：`AIProviderError` 不再把整轮探索判为 FAILED——记录 `ai.unavailable`、规划降级为中性计划、Jev 仍从真实观测到的候选里决策，页面/几何/证据全部保留；绝不静默切 Fake、不编造 AI 结论。
- **前端实时工作台**（`6567f43`）：`apps/web/src/features/workspace/DiscoveryLiveView.tsx` + `discoveryLive.ts`（`foldLiveEvent`/`initialLiveState`）+ `quality-discovery.css`，左实时浏览器（帧 + 元素框 + 分类开关）／右实时智能（当前动作、Jev 决策与置信度、元素清单、证据链接）／底部 DevTools 式事件时间线；i18n 双语文案。

本轮收尾新增：

- `apps/api/tests/test_quality_discovery_live_e2e.py`：**真实 Chromium** 验收。本地站点把控件放在已知绝对坐标，断言实时元素清单的 `bounding_box` 与页面相差 ≤8px、流里的帧就是真实 adapter 产出的 JPEG 字节、页内高亮确实被绘制、运行在测试结束前必须收敛到终态。
- 文档：`docs/QUALITY_DISCOVERY.md`（架构/事件契约/几何与高亮/AI 降级/安全边界/UI 指南/配置/验证/未完成项）、`docs/SECURITY.md` §5（探索边界与已知缺口）、`docs/README.md` 索引。
- 门禁修正：`ruff format`（5 个文件此前未格式化）、`scripts/export_openapi.py`（`/stream` 路由使 OpenAPI/生成类型自 `534c252` 起过期），两者都是真实门禁失败，不是外观问题。

测试证据（本轮实跑）：

- `pytest test_quality_discovery.py test_quality_discovery_live.py test_quality_discovery_live_e2e.py test_discovery_coverage_e2e.py -q` → **78 passed / 179.79s**。
- 真实浏览器验收单跑 `test_quality_discovery_live_e2e.py` → **1 passed / 2.37s**。
- `ruff check apps/api packages` → All checks passed；`ruff format --check .` → 441 files already formatted。
- 前端 `pnpm --filter @ai-qa/web test|typecheck|lint|build` → **172 passed**、typecheck/lint 无错、build 30.05s。
- `scripts/i18n_check.py` → 25 namespaces / 2 languages / 3062 keys passed；`export_openapi.py --check` → current。
- 全量后端回归（评审修复后重跑）：`uv run --no-sync pytest apps/api/tests packages -q` → **869 passed / 11 skipped / 599.96s**。
- Before/After UI 截图：`.ai-runs/discovery-live/screenshots/before-discovery-form.png`（旧：表单 + 数字计数器 + 文字日志 + 状态图）与 `after-live-discovery.png`（新：真实浏览器画面 + 3 个绿色元素高亮框 + 元素清单 + DevTools 式事件时间线，`naturalWidth=1280`、`boxes=3`）。委派 `del_mvcof1z7_ufyh` 超时（30m）但交付物已产出并已由本人复核。

### 真实 provider 现场证据（2026-10-18 通过真实 UI 启动两次探索，DB `/tmp/discovery-live/ai_qa_platform.db`）

证据文件：`.ai-runs/discovery-live/evidence/ai-degradation-live.txt`。

- **Jev 真实在线可用**：`decisions` 里 `provider=jev, model=jev-1.13.0`，confidence `0.96 / 1.0 / 1.0`，动作按 Jev 选择真实执行并 `action.verified`。
- **AI 规划 provider 真实超时**：`ai.unavailable`（`"AI Provider 在 20 秒内未返回结果（已重试 0 次）"`，`code=timeout`）——运行**没有**变 FAILED，继续以确定性候选策略 + Jev 决策推进（`states=3, actions=3, features=9`），截图/DOM 证据全部保留。这正是 §9 要求的降级行为，且是在真实 provider 失败下验证的。
- 因此修正上一版结论：**Jev 链路为真实通过**；**AI 规划 provider 的成功路径仍为 BLOCKED**（超时），不得把降级通过当成 AI 验收通过。

### 独立评审与整改（reviewer `del_mvcozbwq_mbiv`，报告 `/tmp/acp-delegate/del_mvcozbwq_mbiv.out`）

评审结论：Quality Discovery 功能本身无 P0，但分支捆绑的 ACL 不完整 + live hub 内存泄漏必须修；已全部整改并重跑全量（上述 869 passed）：

- **P1（已修）**：`git_pr.py` 挂在同一 `/workspaces/{workspace_id}` 前缀却没有项目守卫，任何持有 `AUTOMATION_EDIT` 的 QA_ENGINEER 都能对别的项目工作区 `git commit/push`。已加 `workspace_access`；同类缺口一并补齐：`/ai/requirements|test-designs/*`、`/test-designs/*`、`/lifecycle/projects/{id}/*`、`/onboarding/{id}/*`、`/runs/{id}/runtime`（新增 `test_design` 解析器、`resource_query_access`、`enforce_resource_access`）。新增两条 ACL 测试（台工作区 git 路由、发现流 ticket 不得成为存在性探测器）。
- **P2（已修）**：`DiscoveryLiveHub` 的 `_frames` 在「查看者先断开、运行后结束」时永久残留 → 新增 `release()`，在 `_finish_locked` finally 与最后一个订阅者离开时释放，并删除死代码 `latest_frame()`；每个查看者各起一个抓帧泵 → 改为每 run 单个共享泵，并在 finalization 里 `cancel + gather`。
- **P2（已修）**：`/api/auth/stream-ticket` 的 `discovery` 分支只查存在性 → 现在按项目 ACL 判定（非成员 404）。
- **P3（已修）**：live-only 事件 `seq` 不再是重复值（新增 `_live_seq`，与持久化事件共享单调计数）；`_stop_events` 在 finalization 释放；`HIGHLIGHT_SCRIPT` 返回真实绘制数量（`slice(0,50)` 之后）；`test_project_acl.py` 里那条“用 requirement id 当 failure id”的空洞断言改为真实 `test_executions → failure_records` 链；`docs/QUALITY_DISCOVERY.md` 中与代码不符的帧生命周期描述已修正。
- **P3（未修，已知）**：`collect_controls` 仍先 `evaluate_all` 再 `slice(0,100)`（恶意大 DOM 成本，历史行为）；`DiscoveryLiveView` 的 effect 依赖只有 `[runId]`（eslint 未启用 exhaustive-deps），若流断开时状态转终态不会自动停。
- **OSS 调研 BLOCKED**：Skyvern/Stagehand/browser-use/agent-browser/playwright-mcp/crawl4ai/firecrawl 的调研委派因网络超时（30 分钟上限）无产出；未引入任何 OSS 代码或依赖，报告中不得声称研究/采用过这些项目。
- 安全缺口（`docs/QUALITY_DISCOVERY.md` §7 已写明）：允许域名只匹配 host，无私有 IP/link-local/CIDR 与端口限制；探索循环仍是进程内 `asyncio` 任务，未纳入 `TaskRuntimeService`，重启不存活。
- 发现→Requirement/TestCase/Automation 的关联目前是 id 级与测试断言，未做 schema 级 provenance。

## 3.5 Round 8（全平台 UI/UX 工作台改造，m01373，分支 `agent/ui-workspace-redesign`）

目标：不是换皮，而是让核心链路（需求 → 用例 → 自动化 → 执行 → 结果 → 失败调试 → AI/Jev 修复 → 验证）
在一个连续工作台上下文内完成；布局/交互参考 VS Code、Playwright Trace Viewer、DevTools、Linear、n8n 等
产品，但未引入任何外部依赖与外部代码。

### 已交付（未合并 main）

1. **环境缺陷 P1（已修）**：`apps/web/index.html` 原先引用 Google Fonts；该域名在本环境不可达，被拦截的
   webfont 使 `document.fonts.ready` 永不 resolve，Playwright 截图永久挂起
   （`Page.screenshot: Timeout 90000ms exceeded`）。已移除全部外部字体请求，`src/index.css` 改用
   本地/系统字体栈 `--font-sans` / `--font-mono`，离线与内网部署、自动截图因此可用。
2. **设计系统单一来源 + 机器强制**：`apps/web/tests/design-system.test.mjs`（4 条）强制
   ① `index.html` 无任何外部 URL ② 核心 token 已声明 ③ 所有 `var(--token)` 均可解析
   ④ 字体只能来自 `var(--font-sans/mono)`。首次运行即抓出 6 个未声明 token 与 7 处硬编码字体栈
   （含 `ProblemsPanel.tsx` 中 `fontFamily: inherit` 的非法 JSX）。`docs/UI_DESIGN_SYSTEM.md`
   合并为单一规范（token / 语义色 / 字体策略 / 布局原语 / 组件规则 / IA 规则 / 强制手段 / 已知缺口）。
3. **工作台上下文列表可用**：`WorkspacePage.tsx` 新增 `WorkspaceContextList`（筛选框 + 「+N 更多 / 收起」
   + 空结果提示），替换左栏三处静默截断（12/10/5 条）。
4. **Studio 底部执行/调试 dock**：复用既有 `.studio-bottom-panels`，接上统一面板缩放原语
   `apps/web/src/features/workspace/usePaneResize.ts`（指针拖拽 + 方向键 + Home/End + localStorage 记忆
   + `role="separator"`）；折叠时面板保持挂载，不丢运行输出/调试会话。
5. **迁移漂移加固**：`0013_project_ownership` 在「列已存在但 `alembic_version` 未推进」的库上会让 API 无法启动
   （本机 dev DB 真实发生：`duplicate column name: owner_id`）。迁移改为先 inspect 再按需创建，并新增回归测试
   `test_project_ownership_migration_survives_a_previously_unaltered_column`。
6. **真实不稳定修复（重要）**：`apps/api/tests/test_quality_discovery_live.py` 在整套回归中偶发失败/挂起
   （5 次隔离运行 1 次 120s 挂起）。根因是真实竞态：`event_generator` 先读 run 状态、后订阅；若 run 在两者之间
   结束，终态事件在没有订阅者时被发布且抓帧任务已被 finalize 取消，观看者永久等待。已加入有界空闲兜底
   `LIVE_STREAM_IDLE_TIMEOUT_S = 3.0`（超时重读 run 行并补发 `run.finished`）+ 回归测试
   `test_viewer_attaching_after_finalization_is_not_left_waiting`；修复后 9 次运行 0 挂起。
7. **Before/After 真实截图**：`.ai-runs/ui-redesign/before/`（22 张，改造前）与 `.ai-runs/ui-redesign/after/`。
   工作台 5 个阶段跳转实测保留全部上下文参数（projectId / requirementId / testDesignId / caseId /
   bindingId / nodeid / file 全部保留），Studio dock 折叠/展开/键盘缩放/刷新记忆全部实测通过。

### 本轮验证（真实输出）

- 前端：`pnpm --filter @ai-qa/web test` → 179 passed（新增 design-system 4 + pane-resize 3）；`typecheck`、
  `eslint`、`build`（29.9s）全部通过；`scripts/i18n_check.py` → 25 namespaces / 2 languages / 3067 keys。
- 后端：`uv run --no-sync ruff check apps/api packages` 通过；`ruff format --check .` 通过；
  `pytest apps/api/tests packages -q -p no:randomly` → 见 §9 本轮最终数字。
- 浏览器（真实 Chromium，阻断 fonts.googleapis.com/fonts.gstatic.com 以免截图挂起）：
  `/tmp/ui-baseline/before-workflow.py`、`/tmp/ui-baseline/after-workflow.py`、`/tmp/ui-baseline/after-verify.py`。

### 未完成（诚实记录，下一轮优先级）

- 全站 IA 只收敛了第一刀：侧边栏「运行」→ `/runs`、「质量洞察」→ `/quality` 仍会离开工作台并丢失项目上下文，
  这是当前对「连续性」影响最大的缺陷；Studio 工具栏仍无「录制」入口（录制只能从 `/recorder` 进入）。
- Studio 首屏可用时间实测 12–17s（Monaco 懒加载），期间无进度反馈。
- Recorder / Debugger / AI 修复面板尚未逐一改造；`.ai-runs` 之外的截图只覆盖主要页面。
- 组件级 UI 回归测试仍缺失（最大结构性风险，详见 `docs/UI_DESIGN_SYSTEM.md` §已知缺口）。

## 3.6 Round 9（Release Candidate 与真实 QA 产品验收，m01734）

验收绑定 SHA：**`3cbd2a8`**，已于用户明确指示下 fast-forward 合并进 `main`（main 现为 `15abcf8`；其后仅文档/证据提交，代码树未变）。完整报告（已入库）：`docs/RC_ACCEPTANCE.md`；同内容证据副本：`.ai-runs/rc-acceptance/RC-REPORT.md`；UI Before/After 截图：`.ai-runs/ui-redesign/{before,after}/`；UI 走查原始证据：`.ai-runs/rc-acceptance/{journey.json,repeatability.json,fixpath.json,screenshots/}`（均未跟踪，不提交）。

### 本轮真实结论（PARTIAL）

- **日常链路**：需求 → 用例 → 脚本 → Studio 运行 → 结果 → 失败证据 → 调试入口，全部可只经 UI 完成（16 次点击 / 9 次 URL 变化 / 0 次回终端）；真实 AI 环节因 Provider 不可达而只验证了诚实失败与降级。
- **门禁结果**：SQLite 全量 `1 failed, 870 passed, 11 skipped, 658.73s`；PostgreSQL 全量 `875 passed, 7 skipped, 448.83s`；前端 179 passed / typecheck 0 / lint clean / build 29.8s；i18n 3067 keys passed；OpenAPI current；`-m security` 16 passed（SQLite+PG 各一次）；Worker 真实进程 SQLite 4 / PG 4 passed；迁移 0013 在 SQLite 与 PG 均 upgrade/downgrade 往返成功。
- **现场真实 Provider 证据**：**Jev = LIVE**（`provider=jev`, `model=jev-1.13.0`, confidence 0.96/1.0/1.0，3 条决策，且 UI/`result.decisions[]` 可追溯）；**AI 规划 Provider = BLOCKED**（20s 超时 → `ai.unavailable`，降级继续，states=3/actions=3/features=9，未伪造结果）。证据：`.ai-runs/discovery-live/evidence/ai-degradation-live.txt`。
- **本轮新增的真实修复**：(1) 迁移 0013 启动崩溃（手工加列 + 旧 `alembic_version` → `duplicate column name`）——改为 inspector 探测 + 新增回归测试；(2) Discovery 直播流订阅/发布竞态——`event_generator` 订阅先行 + `LIVE_STREAM_IDLE_TIMEOUT_S=3.0` 空闲收尾 + 新增回归测试。

### 未关闭缺陷（下一轮优先级）

- **D1（高）**：AI/Jev 修复分析在使用者中途离开后卡在 `status=RUNNING` / `ANALYZING` / `allowed_actions=[]`，重载后 UI 显示「未启动」且隐藏全部操作；UI 与 API 矛盾。
- **D2（高）**：AI 分析 90s+ 无失败提示，任务可无限显示「运行中」。
- **D3（中）**：调试页无失败文件:行号（仅源码页有）。**D4（中）**：侧边栏 `/runs`、`/quality` 离开工作台丢上下文。**D5（低-中）**：结果摘要偏薄。**D6（低）**：Studio 无录制入口。
- **偶发失败（中）**：`apps/api/tests/test_browser_agent_e2e.py::test_browser_agent_checks_and_switches_to_popup_landing[selenium.dev-False-False]` 在高负载全量套件中偶发 `TargetClosedError: Locator.count: Target page, context or browser has been closed`；单独运行 3/3 passed。根因方向见 `apps/api/app/adapters/playwright/locator.py:30` 与 `apps/api/app/services/task_browser_executor.py:245` 的已关闭弹窗枚举；本轮**未做盲目修补**。
- **企业部署缺口**：备份/恢复演练、CI/CD 证据、发布/回滚演练、密钥托管轮换、审计字段完整性、产物级项目隔离（`ArtifactORM` 无 `project_id`）、探索循环纳入 TaskRuntimeService。

## 3.7 Round 10（质量发现「生成用例/需求/脚本」可用性修复，m01913）

用户在真实使用中报告：Discovery「需求与覆盖差距」里生成测试用例不好用，且发现结果整体难以继续生成需求 / 用例 / 自动化脚本。本轮按代码级根因定位并修复，全部有现场证据。

### 根因与修复

1. **策略阻止的缺口淹没可用信息**（`apps/api/app/services/quality_discovery_projection.py`）：每个被安全策略阻止的探索目标都生成一条 `BLOCKED_BY_POLICY` gap，该 run 因此有 **154 条** gap，用户看到的是卡片墙。改为**按页面聚合**：一条 gap 携带 `blocked_count` 与 `targets`（最多 25 个），标题为「安全策略阻止了 N 个探索目标」。现场复算后 gap 从 **154 → 33**（其中策略阻止 2 条）。新增回归测试 `apps/api/tests/test_quality_discovery.py::test_blocked_policy_gaps_collapse_per_page`。
2. **「生成自动化草稿」按钮被完全隐藏**（`apps/web/src/features/workspace/QualityDiscoveryPanel.tsx`）：条件含 `test_case_ids.length`，没有用例时按钮不存在，用户无法得知原因。改为始终渲染按钮，仅在缺前置条件时禁用，并**显示一行可见原因**（新增 `.qd-gap-hint`）：需先生成/关联需求草稿、或需先生成测试用例。
3. **失败原因不可读**（`apps/api/app/services/automation_binding_service.py`）：AI 返回说明性文本而非代码时统一抛 `No grounded real-AI draft is available...`。现在区分「Provider 不可用/降级」与「模型给出了说明」，后者把模型原话（截断 400 字）带回 UI。现场验证：点击生成后用户看到的是模型解释为何无法生成（项目证据中没有百度页面对象与选择器）。
4. **缺成功反馈**：动作成功后新增 `role=status` 提示（已创建需求草稿 / 已生成 N 条测试用例 / 已创建自动化草稿），默认筛选改为「需处理缺口（不含策略阻止）」。

### 证据

- `uv run --no-sync pytest apps/api/tests/test_quality_discovery.py -q -p no:randomly` → **67 passed in 26.26s**（含新增 1 条）。
- `pytest apps/api/tests/test_automation_binding.py apps/api/tests/test_quality_discovery_live.py apps/api/tests/test_discovery_coverage_e2e.py -q -p no:randomly` → **13 passed in 155.71s**。
- 前端：`pnpm --filter @ai-qa/web test` → **179 passed**；typecheck / eslint / build 均通过；`scripts/i18n_check.py` → 25 namespaces / 3073 keys。
- 真实 UI 走查（Chromium，run `qd_c92fb0a21d2644c7`）：gap 卡片 **31**、`BLOCKED_BY_POLICY` 卡片 **0**、自动化按钮 **8**（7 个禁用且各带原因）、可见提示 12 条、页内错误 0。截图：`.ai-runs/gap-ux/after-gaps-default.png`、`after-gap-card-with-hint.png`、`after-automation-action.png`、`after-requirement-draft-note.png`（未跟踪）。
- 走查副作用（记在明处）：验证过程中在该演示项目里真实创建了 2 个需求草稿、1 个测试设计（8 条用例），未删除。

### 尚未处理

- 生成自动化仍依赖工作区里存在对应页面对象/页面证据；模型无依据时不编造（这是 `ROADMAP` §0 的既定边界，不是缺陷），但工作区「无页面对象」的场景仍缺引导（例如从发现页面直接生成页面对象骨架）。

## 3.8 Round 11（核心工作流收敛与稳定性整改，m00041）

**本轮起点**：`origin/main` = `d8a2eef`，本地 `main` 在其之上新增 61 笔提交，**全部未推送**。**本轮结论**：见 §1 与 §9（最终全量回归在 `89eb5ed` 上重跑；此后只有文档提交，无代码变更）。

### 第一阶段：P0 阻断修复（D1/D2 统一生命周期）

**根因（不是两个孤立的 UI Bug）**：`apps/api/app/services/failure_workflow_service.py` 的 SSE 生成器自己 `asyncio.create_task(analyze())`，并在 `finally` 里 `task.cancel()` —— 换句话说，**分析任务的所有者是 HTTP 响应的生命周期**。前端 `WorkspaceRunResult.tsx` 在卸载或失败切换时 `abort()`，于是刷新/关页即杀死分析，数据库行永远停在 `RUNNING`、修复行停在 `ANALYZING`（其 `allowed_actions` 为空，界面上一个按钮都没有）；而重连分支 `if start_new_analysis is False:` 只回放历史就 `return`，从不等待在途分析。D2 是同一缺口的另一面：全链路没有任何总预算，也没有 `TIMEOUT` 这个终态。

**修复后的契约**（提交 `5eb2376`、`7aac715`、`7b82832`、`32a5b19`）：

- **服务端持久化状态是唯一权威**，SSE 只是跟随者：`stream()` 先 `_prepare_analysis` / `_schedule_analysis`，再回放持久化事件（按 `event_id` 去重）并轮询到终态，不再拥有任务。
- 分析跑在服务自持的任务里（模块级 `_ANALYSIS_TASKS` / `_ANALYSIS_SUBSCRIBERS`，因为每个请求都会新建服务实例），`_run_analysis` 用 `asyncio.timeout(budget)` 强制总预算；超时 → `TIMEOUT` + `run.timeout`，取消 → `CANCELLED` + `run.cancelled`（shield 写终态后重新抛出），异常 → `FAILED`。
- 终态写入走 `failure_analysis_repo.finalize()` 的 `UPDATE ... WHERE status='RUNNING'` 原子守卫，重复回调/幂等重放无法覆盖赢家；`ANALYSIS_TERMINAL_STATUSES = {COMPLETED, FAILED, CANCELLED, TIMEOUT, INTERRUPTED}`。
- 新增 `POST /api/failures/{failure_id}/analyses/{analysis_id}/cancel`，且在 `ANALYZING/DECIDING/VERIFYING_CANDIDATE` 状态下 `allowed_actions` 含 `CANCEL` —— 取消真的停掉 Provider 调用，而不是只藏起转圈。
- 重启恢复：`recover_interrupted_analyses()`（由 `container.recover_failure_analyses()` 委托，lifespan 调用）把遗留 `RUNNING` 收敛为 `INTERRUPTED`，同时把修复行从 `ANALYZING` 释放；孤儿行按**年龄**（`created_at < now - (budget + 60s)`）判定，不新增心跳列。
- 预算 `repair.analysis_timeout_seconds` 默认 **300s**（`config/config.yaml`、`config.example.yaml`、`packages/platform-config`），并保留逐阶段进度事件（`model.progress` 每秒级）。

**顺带发现并修掉的真缺陷**：`e460213`（SQLite 默认 rollback journal 下，长 SSE 读事务阻塞唯一写者 → `database is locked`）；连接钩子改为 `PRAGMA journal_mode=WAL`，并新增回归测试与备份脚本的在线快照分支。

### 第一阶段：高负载浏览器竞态

`TargetClosedError` 的根因不是压力本身，而是**运行时不处理“活动页被关闭”**：`browser_runtime` 没有注册 `close` 监听，`resources.page` 一直指向已死的标签页，`get_session()` 把“标签页关闭”误判成“整个会话崩溃”；执行器的观测路径又直接对本地 `page` 变量 `count()`，异常直接杀死整轮运行。修复（`ffa7ad2`）：活动页关闭时收养同上下文里仍存活的其他标签页，只有浏览器断开或一个可用标签页都不剩才判 `CRASHED`；执行器侧增加 `_adopt_open_page`，观测重试把 `has been closed / page crashed / target closed` 归类为可自愈而非致命。证据：`test_browser_runtime.py` 17 passed（含两个新回归）、`test_browser_agent.py` 25 passed、弹窗用例 3 passed；修复后 `apps/api/tests` 全量 **724 passed / 11 skipped / 442s**，浏览器用例无 TargetClosedError。

### 第二阶段：完整工作流

- **精确失败源定位（D3，`6a851ac`）**：迁移 `0014_failure_source_location` 给 `failure_records` 增加 `source_file`/`source_line`，由 `test_run_service` 里已经算好的 `last_user_code_frame` 一并持久化；前端 `failureWorkspaceModel.failureCodeFrames` 改为“服务端记录优先、正则/断点兜底”，Studio 打开位置也优先用记录行号。
- **上下文连续性（D4，`c74789f`）**：`workspaceContext.buildScopedHref` + `navigation.pathForTab` + 侧边栏 + `RunsRoute`/`QualityRoute` 读 URL 上下文；此前 `RunsRoute` 的 `useParams()` 永远拿不到 `:runId`，深链从未生效。真实浏览器证据：`.ai-runs/context-continuity/`（含 `run_deep_link_selects_run=true`、`deep_link_project_wins=true`、控制台 0 报错）。
- **Recorder → Studio 真实数据级集成（`507c59d`）**：`AutomationBinding` DTO 暴露裁剪后的 `recorder_steps`（步骤定位器 + 页面证据 id + URL），Studio 上下文栏渲染「录制步骤（N）」；同时修掉“同一路径二次保存必定 409”的死路（改用 PUT 覆盖）。真实验收：录制 → 保存 → Studio 打开（URL 带 `caseId`/`bindingId`/`nodeid`）→ 编辑 `Control+S` 落盘 → 「运行文件」产生真实 run；二次录制同一路径不再 409。证据 `.ai-runs/recorder-studio/`。
- **人工批准 → 应用 → 精确验证链路**：真实浏览器跑 `failure → AI 分析 → 批准并应用补丁 → 回归验证`，验证结论来自真实 run（`.ai-runs/governance/repair-chain/`）。AI 只生成提案，源码写入仍需 `allowed_actions` 中的显式人工动作。
- **AI 长生成超时**：`provider.complete/stream_complete` 原本 `timeout = min(self.timeout, request.timeout_seconds)`，请求侧只能改小不能改大；新增 `LONG_GENERATION_TIMEOUT_SECONDS = 90.0` 并让显式预算优先（`df4d709`）。同一 gap 动作从 **502 / 129.2s** 变为 **200 / 61.1s**，用例生成真实产出 5 条用例。

### 第三阶段：Discovery

- **接入 TaskRuntimeService（`e1f3fdb`）**：新增任务类型 `EXPLORE_PRODUCT` 与单步计划 `discovery.run`，`QualityDiscoveryService._start()` 在装配了 `task_commands` 时创建真实运行任务（任务 id 写入 `run.result["runtime_task_id"]`），`execute_run()` 把当前 asyncio 任务登记进 `_tasks` 以保持 pause/stop 语义；终态非 COMPLETED 时抛 `TaskBlocked`，于是任务中心显示 BLOCKED 而不是假装成功。启动恢复 `recover_interrupted_runs()` 把遗留 `RUNNING/QUEUED` 置 `PAUSED`（可用 `/resume` 继续）。`task_scheduler_service._execute_dag` 把“没有待执行步骤”的完成判定移到挂钟预算检查之前 —— 否则单个长步骤完成后会被 `max_duration_seconds` 追溯判失败。**已知权衡**：运行中的探索会占用调度器两个并发槽之一。
- **无页面对象引导（`2d642e3`）**：草稿生成返回 `page_objects`（`pages/*.py`、`flows`、`components`，上限 50），为空时在 Studio 草稿预览处给出明确引导文案；模型无依据时不编造（ROADMAP §0 的既定边界）。
- **真实浏览器观察体验（`edcde0a`）**：`state.observed` 事件 metadata 增加 url 与网络摘要，`DiscoveryLiveView` 新增网络请求面板；暂停 → 刷新 → 继续 → 停止与**重启恢复**都有真实证据（`.ai-runs/discovery-live/`），其中硬杀进程后 run 变 `PAUSED`、运行任务变 `BLOCKED`（`Interrupted by API restart...`）。

### 第四阶段：工程与安全治理

- **产物项目隔离与审计字段（`19f7e33`）**：迁移 `0015_artifact_ownership` 增加 `stored_artifacts.project_id`（FK `ON DELETE SET NULL`）与 `created_by`；全部写入方（run 制品、Discovery 截图/证据、任务证据）带上归属；`artifacts` 路由改为登录 + `enforce_resource_access(user, "artifact", id)`，上传可选 `project_id` 并校验归属，遗留无归属行仅管理员可取。
- **覆盖率口径统一（`31450a3`、`2ab2874`）**：删除前端自算的 `coverageModel.ts`，`QualityPage` 与 `coveragePresentation` 只信任服务端 `coverage.*` 判定；`docs/QUALITY_INTELLIGENCE.md` 记录唯一口径。
- **迁移往返**：见 §7 与 `.ai-runs/migrations/drill.log`（修了 0015 的 SQLite `create_foreign_key` 缺陷与线上库缺索引漂移）。
- **运维演练**：备份/恢复逐表一致；密钥轮换为“重启生效”并验证了降级行为；**部署/回滚与 CI 在本环境明确 BLOCKED**（无容器运行时；本轮修订从未推送，故 CI 未运行），证据 `.ai-runs/governance/{backup-restore-drill.json,key-rotation-drill.json,deploy-ci-evidence.json}`。

### 独立评审与修复（`be6ec64`）

第三轮独立评审（read-only reviewer，审 `origin/main..HEAD` 的全部提交）结论 **PARTIAL**：六项不变量均成立（无模型决定 PASS/FAIL、不经批准不改码、单一 runtime/agent/provider、外部写入有预览、无无人值守循环），但指出三处问题，已全部修复：

1. `apps/api/tests/test_runtime_migrations.py` 硬编码 `0013_project_ownership` 在 head 变为 0015 后变红，且从未验证降级 —— 改为断言 `ScriptDirectory` 的脚本 head，并补 0014/0015 的 `upgrade → 0013 → upgrade`。
2. Discovery 双重执行：运行任务仍在排队时 `pause` + `resume` 会为同一个 run 再建一个 `EXPLORE_PRODUCT` 任务（两个探索循环、动作预算翻倍），且排队期间的暂停会被启动时静默覆盖 —— `_start` 现在把“记录在案且未终态的任务”视为已拥有该 run，`execute_run` 拒绝被另一个活循环驱动的 run，暂停在排队期间也能保留（新增 2 个回归用例）。
3. 失败页时间线在重连时重复追加服务端重放的事件 —— 按 `event_id` 去重。

复评（`be6ec64` 上，read-only reviewer）：结论 **PASS**，三条 finding 均按根因关闭（证据 `.ai-runs/governance/review-round11-refix.md`），复评另提 4 条非阻断新发现，其中一条是状态机漏洞，已在 `89eb5ed` 修掉：

- **A（状态机漏洞）**：`_runtime_task_in_flight` 把“被用户在任务中心暂停的任务”（`PAUSED`/`PAUSING`，非终态且调度器也不会再领取）当作在飞，于是 `resume()` 已把 run 写成 `RUNNING` 却没有任何执行者。现在 `_start` 遇到暂停态任务时调 `task_commands.resume(task_id, row.requested_by)` 把它交回队列。
- **B（半真）**：暂停门原本只在循环内部，排队期间的暂停仍会先调用 Provider 需求分析、创建浏览器会话并导航。现在 `_assert_runtime_ready` 之后、`run.started` 之前先 `_wait_if_paused` + 停止检查，暂停状态下不产生任何副作用。
- **C（文档过期）**：Git 状态表与 §9 未反映修复提交 —— 本节与 §2、§9 已同步。
- **D（测试覆盖）**：补了暂停任务回队列、`BLOCKED` 后仍可重试、第二循环守卫、暂停运行无副作用四个用例，并让迁移测试在降级时断言两个新版本的全部列。前端事件去重是三行内联逻辑，不新增抽象，由真实浏览器旅程覆盖。

最终回归与 verdict 见 §9。

### 本轮证据索引（全部在未跟踪的 `.ai-runs/` 下）

| 主题 | 位置 |
| --- | --- |
| D1/D2 生命周期（含真实 Before/After 同页对照） | `.ai-runs/d1-d2-lifecycle/{browser-acceptance.json,screenshots/}` |
| Recorder → Studio | `.ai-runs/recorder-studio/` |
| 上下文连续性（D4） | `.ai-runs/context-continuity/` |
| 修复链路（人工批准→应用→验证） | `.ai-runs/governance/repair-chain/` |
| Discovery 观察与恢复、崩溃恢复 | `.ai-runs/discovery-live/` |
| Discovery 下游转换（需求/用例/自动化） | `.ai-runs/discovery-downstream/` |
| 迁移 / 备份恢复 / 轮换 / CI-部署 | `.ai-runs/{migrations,governance}/` |
| 最终走查（9 页 × 2 视口 + 连续旅程 + Before/After 对照表） | `.ai-runs/final-acceptance/` |

### 本轮未解决 / 边界（下一轮优先级）

1. Discovery 停止后运行任务落在 `BLOCKED` 而非 `CANCELLED`（`execute_run` 抛 `TaskBlocked`）——语义可用，但没有“用户主动取消”的独立终态。（**Round 12 已修：`860f4f2`**）
2. 多副本部署下，取消信号无法跨进程传递给持有任务的实例；当前实现只在同一进程有效，跨进程时靠孤儿收敛（预算 + grace）。这是单进程部署的既定边界，需要多副本时再引入租约/信号通道。
3. 运行中的探索占用调度器两个并发槽之一；多用户场景需要提高并发或把探索移出该并发池。
4. 部署/回滚演练与 CI 运行证据在本环境 BLOCKED；换到有容器运行时的环境后必须补做（脚本已就绪：`scripts/deploy.sh`、`.github/workflows/ci.yml`）。
5. 历史遗留（与本轮无关但仍在 §7/§8）：`AIProviderRegistry` 未 `configure_runtime` 时回落 fake provider、`POST /api/jobs/{id}/result` 抢输一方仍返回成功、Monaco chunk 体积、暗色主题验收、worker lease 续租。
6. 本轮评审后仍未处理的历史 UX 项：D5（结果摘要偏薄）；D6 只完成了一半（录制步骤已与 Case 数据级关联，但常规 Studio 工具栏仍无录制入口，入口只在未绑定空状态）。

## 3.9 Round 12（剩余阻断问题核实与真实端到端验收，分支 `audit-remaining-blockers`）

完整报告：`.ai-runs/e2e-round12/audit-report.md`；证据：`.ai-runs/e2e-round12/{journey_a,journey_b,journey_c}.json` + `screenshots/`、`.ai-runs/governance/key-rotation-drill.json`。

### 五项声称完成能力的复核判定

| 能力 | 判定 | 依据 |
| --- | --- | --- |
| D1/D2 分析生命周期（超时/取消/重试/刷新恢复） | **PASS** | 模块级任务所有权 + `_finalize_analysis` 原子守卫 + `_reconcile_orphaned_analyses`/`recover_interrupted_analyses`；4 个生命周期用例；旅程 B：RUNNING + 取消可见 → 刷新仍 RUNNING → 取消 CANCELLED/16 事件/`ANALYSIS_CANCELLED`，且 `failure_diagnosis` 调用同刻 CANCELLED（取消到 provider 层） |
| Recorder → Studio（真实录制数据进入编辑/保存/运行） | **PASS** | 录制会话 steps 3（API/UI 一致）→ `tc_rec_8f67904a75f040439578712bb991b` + `bind_95d61bff41f7` → `binding.recorder_steps` 2 条 → Studio「录制步骤（2）」→ Monaco 编辑持久化 → `run_6eab101ce918` PASSED 1/1。录制面板在「更多工具 → 测试上下文」内（`embedded` 时默认收起），不是缺陷 |
| Discovery 分析循环的进程内任务依赖 | **单实例 PASS / 多实例 BLOCKED** | 循环已由 `TaskRuntimeService` 拥有、DB 原子 `claim_for_execution` 不会双跑；但 pause/stop 信号是 `_tasks`/`_resume_events`/`_stop_events` 进程内对象，且启动收敛把全部非终态 run 置 PAUSED、全部 unfinished 任务置 BLOCKED → 多副本滚动重启会误停别人的探索。正确修法需 lease/信号契约（属重新设计，未做） |
| 真实 AI Provider 成功路径 | **PASS** | `/api/ai/status` = REAL_CONNECTED（streaming）、`/api/decision/runtime-check` = CONNECTED/READY（Jev）；真实业务 SUCCESS：failure_diagnosis 9、quality_discovery_planning 15、exploration/locator selection（jev）38、test_case_generation；本轮旅程 B 诊断 18.9s/补丁生成 41.6s、旅程 C 恢复后诊断→批准→验证 `run_68c6abfca821` |
| 密钥轮换恢复演练 + 明确健康标准 | **PASS（重做后）** | 上一轮 `restored_stack_healthy` 是「未测量」不是通过。标准写进 `key-rotation-drill.json` 的 `health_standard`（health + readiness + login + 领域读 + web bundle + 禁止端口回退）；本轮 10/10：坏密钥栈 8 项全 true 且 `UNAVAILABLE` 不泄漏、分析 FAILED 保留重试；真钥栈 8 项全 true、零回退、`REAL_CONNECTED`、重试产出真诊断并被批准+验证 |

### 本轮修复（3 笔，均带测试）

1. `860f4f2` 用户停止探索不再是 `BLOCKED`：新增 `TaskCancelled`（`services/task_errors.py`），`quality_discovery_service.execute_run()` 对 STOPPED 抛它，调度器映射为 `CANCELLED`，orchestrator 把 RUNNING 步骤置 `CANCELLED` 并发 `step.progress`。测试：`test_discovery_task_runtime.py`（重写 1 + 新增 2）、`test_agent_tasks.py`（+1）。
2. `abe6a2a` 启动时回收死进程留下的 `RUNNING` AI 调用：`ai_repo.recover_interrupted_invocations()` → `INTERRUPTED`/`process_interrupted`，`main.py` lifespan 调用。测试：`test_ai_governance.py`（+1）。DB 中 4 行残留全部收敛，`RUNNING` 归零。
3. `2eb6901` 启动器不再把 `TIME_WAIT` 当端口占用：`scripts/task.py` 的 `_port_is_in_use()` 改为「有人 accept 才算占用」（旧实现对刚停掉的栈 bind 失败 → 静默换端口 → 上一轮轮换演练误记「未测量」）。测试：`test_dev_launcher_ports.py`（2 例）。

### 本轮未解决 / 边界

1. **多实例一致性仍 BLOCKED**（同 §4 上文的进程内信号 + 全量启动收敛）。
2. **部署/回滚/CI/PostgreSQL 仍 BLOCKED**：本环境无 docker/compose/pg；CI 最近 3 次运行失败，那 4 条失败用例在本地重跑通过（环境差异），本轮代码从未在 CI 上跑过。
3. P2 观察：失败页内联分析与 `FIX_FAILURE` 任务两条修复面并存（取消内联分析后 `locator_repairs` 停在 `BLOCKED/ANALYSIS_CANCELLED`，任务链随后验证同一处修复通过 → 两个事实都真但读起来矛盾）；已有分析历史时内联「重新分析」被「打开分析与修复任务」取代（`FailuresPage.tsx:322`）。
4. Jev 评分通道持续 `FALLBACK`（`invalid_request`）；`provider_connection` 探针曾以 `output_limit` 假阴性。
5. 等待人工审批的任务无过期策略（DB 里有一条 9 小时前的 `WAITING`）。

## 3.10 Round 13（产品体验与工作流统一优化，分支 `audit-remaining-blockers`）

用户任务 m01571：在已稳定的闭环上统一交互与信息表达，不加新能力。审计用同一个真实浏览器脚本跑前后对照（`uv run python .ai-runs/e2e-round13/audit.py before|after`），证据 `.ai-runs/e2e-round13/{before,after}/audit.json` + `screenshots/`，控件清单 `.ai-runs/e2e-round13/ui-inventory.json`。

### Before → After（真实 Chromium，1560×1000，UI 点击路径）

| 检查项 | Before | After |
| --- | --- | --- |
| 从总览能到达可运行的发现面板 | FAIL（`开始发现` disabled=True，无解释） | PASS（disabled=False；仍在跑时会显示为什么并保留下方继续/停止） |
| 不输入 URL 就能到达录制器 | FAIL（`view=browser` 不可达，可见入口 0） | PASS（1 次点击 `浏览器录制`） |
| Studio 无需打开菜单就能看到录制步骤 | FAIL（默认隐藏，需 2 次点击） | PASS（`default=True`，0 次点击） |
| 失败页不会把人堵死（能重新分析或有待批审批门） | FAIL（`reanalyze_visible=False`，主操作「打开分析与修复任务」） | PASS（`reanalyze_visible=True`；该检查在 After 版本改名为 `the failure page never leaves the user without a way forward`，同时接受「有审批门」） |
| 从用例进入录制并保留用例上下文 | FAIL（无入口） | PASS（`录制此用例` → `view=browser` 且 URL 保留 `caseId/bindingId/nodeid/file`） |
| 各视口无横向滚动 | PASS | PASS |

### 三笔改动

1. `0cc6abd` **一个修复链取代两个竞争面**：失败页轮询 `GET /tasks/{id}`（3s），`repairTaskChain()` 把 `FIX_FAILURE` 的 plan 步骤（`diagnose/repair/approval/apply/target_run/verify`）投影到与原内联分析相同的「诊断 → 修复 → 重跑 → 验证」轨道；任务已验证时不再显示「未验证」；取消/超时/中断按实际结局标注（`attemptStates.*`）而不是折叠成「阻塞」；无待批审批门时保留「重新分析」。
2. `800bc5d` **录制入口与录制步骤可见**：工作台头部每个阶段都有 `浏览器录制`；自动化标签页文案由「浏览器」改为「浏览器录制」；Studio 工具栏起录制；绑定用例打开时自动展开含 `录制步骤（n）` 的上下文面板（原来是 `<details>` 折叠）。
3. `99a2509` **上下文/文案/数量一致**：`rewriteProjectScope()` 让切换项目时保留 `?projectId=`（`Navigation`）、库页运行/失败链接带项目范围、任务来源 `/recorder` 也带项目；总览待处理条目改显本地化任务类型（补 `type_QA_GOAL`、`type_EXPLORE_PRODUCT` 两个缺失 key，原先直接渲染原始 key）；工作区阶段条在需求范围内计数时明写「当前需求 n 条用例」；探索被暂停时启动行说明原因。

### 本轮未做（有意）

- 未改后端：本轮全部为前端表达与导航一致性，后端 0 改动（Round 12 的 898 passed 基线不受影响）。
- 「最近任务」卡片与「待处理」条仍会同时出现同一任务：前者是历史、后者是待办，不去重（去重会隐藏上下文）。
- 多实例一致性、部署/回滚、CI、PostgreSQL 仍 **BLOCKED**（同 §3.9）。

## 3.11 Round 14（只读工作流画布 MVP，用户任务 m02243）

用户任务 m02243：在既有 Workspace 内用 React Flow 建一块**只读**工作流画布，把真实记录投影成流水线，不新增执行能力、不重做 Recorder/Studio/修复链。起点 `c756994`。

### 交付

| 层 | 内容 |
| --- | --- |
| 契约 | `packages/project-model/project_model/workflow_canvas.py`：`WorkflowCanvas` / `WorkflowNode` / `WorkflowEdge` / `WorkflowStage` / `WorkflowEvidence` / `DiscoveryMetrics` / `DiscoveryEvidenceRef` |
| 投影 | `apps/api/app/services/workflow_canvas_service.py`：把 discovery run → recorder session → studio 绑定 → run → failure → analysis → approval → verification 投影成 8 个阶段节点，业务节点 ID 与任务 ID 分开存放，全部字段来自真实行 |
| 接口 | `GET /api/projects/{project_id}/workflow-canvas?requirement_id=&limit=`（`apps/api/app/api/workflow_canvas.py`，项目 ACL + 截断标记） |
| 画布 | `apps/web/src/features/canvas/{canvasModel.ts,WorkflowCanvasPanel.tsx,canvas.css}`：每阶段一列、每记录一行、状态色调、节点选择与右侧详情、Controls、MiniMap、Background |
| 入口 | Workspace 第 5 阶段 `stage=automation&view=canvas`（既有 5 阶段并存），i18n zh/en |
| 测试 | `apps/api/tests/test_workflow_canvas.py`（9 例：投影、ACL、截断、任务/审批串链）、`apps/web/tests/canvas-model.test.mjs`（布局/色调/连线） |

### 三笔提交

1. `9fd04df` **后端投影层**：只读投影 + ACL + 截断；Discovery 指标与证据索引从 `discovery_runs.result` 与已落库的步骤/快照/网络记录投影，不采集、不调模型。
2. `bf9b5c2` **前端画布**：阶段列 + 节点卡片（`data-entity-id` 便于定位与悬停看完整 ID）+ 详情面板（记录摘要、指标、证据索引、跳转到既有失败/调试/工作台）+ 3s 轮询（仅在存在活跃记录时）；画布不发任何写操作。
3. 本文档提交。

### 真实浏览器验收

`.ai-runs/e2e-round14/canvas_acceptance.py`（Playwright 1.62.0 + Chromium）：**16/16 PASS，`failed: []`，`console_errors: []`**，证据 `.ai-runs/e2e-round14/canvas-acceptance.json` + `screenshots/a1..a7-{desktop,laptop,tablet,mobile}.png`。覆盖：真实 discovery 记录上画布、8 个阶段列齐全、选中节点显示真实指标（`{states:3, actions:3, features:4, requirements:1, gaps:11, covered:1, not_covered:3, test_cases:8}`）与 12 条证据、失败节点链到既有失败页与调试、真的跑一次（`run_ab9bf241bac2` PASSED）并出现在画布、刷新后 29 节点/16 边与状态不变、互动不创建任务、既有阶段仍并存、1560/1280/1024/390 四种视口均可选中节点且无横向溢出。

### 过程中修掉的真实缺陷

- **节点尺寸写法**：给节点写 `width/height` 会被 React Flow v12 当成固定尺寸，导致 MiniMap 空、连线偶发缺失；改 `initialWidth/initialHeight` 后两者正常。
- **窄视口**：整条流水线 `fitView` 到 346px 会压成不可辨认的一团（约 0.11 缩放，首列还在视口外）。现在按容器能给的缩放决定策略：`< 0.45` 时从第一阶段起、`zoom 0.62`（用户自己平移），否则整条 `fitView`；1024px 平板因此从「一片糊」变成可读，1560px 桌面仍是一眼全链。窄视口下小地图会盖住它本来要概括的卡片，`@media (max-width: 1100px)` 隐藏（`Controls` 仍有「适配视图」按钮）。
- **URL 指定文件被空态挡住**：`?file=` 时若用例未绑定脚本，`WorkspacePage` 会在编辑器位置渲染「此用例尚未关联自动化脚本」空态，用户要求的文件根本打不开。现在显式 `file` 优先（`automationSetup` 加 `&& !context.file`）。

### 本轮未做（有意）

- 画布**不可编辑、不可拖动、不可连线**（MVP 只读）；节点位置只由记录顺序决定，不持久化用户布局。
- 不做按需求/阶段过滤的图形化控件（沿用 URL 的 `requirement_id` 过滤），不改 Discovery 采集，不把画布做成第二个运行控制台。
- 记录超过 `limit` 时画布只显示最近的并标注截断，历史仍在运行/质量洞察/失败页。
- 多实例一致性、部署/回滚、CI、PostgreSQL 仍 **BLOCKED**（同 §3.9）。


## 3.12 Round 15（Structured Discovery & Evidence Intelligence，用户任务 m02941）

用户任务 m02941：把 Discovery 从「探索并生成结果」升级为「采集结构化事实、建立证据关系、分析增量变化、支持测试覆盖分析」。起点 `1b19ca1`。数据契约与审计表见 `docs/DISCOVERY_EVIDENCE.md`。

### 交付

| 层 | 内容 |
| --- | --- |
| 存储 | `discovery_evidence`（13 列 + 5 索引 + 唯一 `(run_id, evidence_id)`）与 `discovery_scenarios`（迁移 `0016_discovery_evidence`，`down_revision = 0015_artifact_ownership`，可逆） |
| 预算 | `DiscoverySettings.capture_evidence` / `max_evidence_records 6000` / `max_network_evidence 200` / `max_payload_chars 2000`；每状态 60 元素、40 请求 |
| 采集 | `apps/api/app/services/discovery_evidence_capture.py`：`dom_element` / `locator_candidate` / `network_request` / `page_state` / `user_action` / `screenshot`（只存 artifact_id）；纯函数、无 AI |
| 写入 | `apps/api/app/repositories/discovery_evidence_repo.py`：按 run 去重、后到的「动作↔请求」关系统原地升级、超预算截断并计数 |
| 分析 | `apps/api/app/services/discovery_evidence_analysis.py`：集合统计（raw/deduped/filtered/stored + `MEASURES` 口径）、候选场景合成、`COVERED/CANDIDATE_GAP/UNDETERMINED` 三级匹配、批次 diff（证据缺失 ≠ 元素消失） |
| 接口 | `GET …/evidence`、`…/evidence/summary`、`…/evidence/diff?against=`、`…/evidence/{evidence_id}`、`…/scenarios`、`POST …/scenarios/refresh`（`apps/api/app/api/quality_discovery.py`） |
| 接线 | `apps/api/app/services/quality_discovery_execution.py`：观察循环与动作路径两个 hook，采集失败只发 `capture.failed` 不中断探索；采集键「该状态是否已有 capture」而非「是否新状态」 |
| 画布 | `apps/web/src/features/canvas/`：节点证据行（`DOM 10→5 · API 2（关联 1） · 状态 2`）、详情面板证据集合与候选场景、阶段折叠 + 可读缩放 |
| 测试 | 后端 `test_discovery_evidence_capture.py`(16) / `test_discovery_evidence.py`(9) / `test_workflow_canvas.py`(6) / `test_runtime_migrations.py`（表数改为按元数据推导 + 降级往返）；前端 `apps/web/tests/canvas-model.test.mjs` |

### 三笔提交

1. `8fd6160` **证据层**：两表 + 迁移 + 预算 + 采集 + 分析 + 接口 + 接线 + 敏感值脱敏（`SensitiveRedactor.redact_typed_values`，accessibility 快照里的输入值写成 `{filled}`）。
2. `d2af796` **画布指标**：`DiscoveryEvidenceMetrics` 由同一分析模块算出（不写第二套计数），节点证据行 + 详情面板 + 阶段折叠。
3. `e9f2951` **元素链接修正**：动作→元素证据改为按「动作实际点击的控件」解析，没有控件就不写引用（此前靠 locator 反推会指向不存在的证据行）。
4. `589e6ab` **采集会话收进仓储**：证据写入不再自己读 run 行（架构边界测试禁止服务层直接持久化），改由仓储回答「这个 run 属于哪个项目」。

### 真实浏览器验收

`.ai-runs/e2e-round15/acceptance.py`（Playwright 1.62.0 + Chromium，真实 UI 点击）：**21/21 PASS，`failed: []`，`console_errors: []`**，证据 `.ai-runs/e2e-round15/acceptance.json`，截图 `before-canvas.png`、`screenshots/{after-canvas-evidence,after-canvas-mobile,after-canvas-reloaded,before-canvas}.png`。受控页面 `examples/demo-shop/site/discovery-fixture{,-b}.html`（由 `apps/api/app/api/lifecycle.py` 提供并列入 `PUBLIC_PATHS`）：
- 元素：首个状态 5 个控件，去重 5 条；脚本按同一 identity 规则独立重算，数字一致。
- 每个被观察的状态都有自己的 capture（此前由动作记账先建出的状态会漏采，raw 被低估）。
- 网络：2 条请求、状态 `[200]`，1 条以 `prefix` 关联到引发它的点击，另 1 条保持 `unassociated`。
- 定位器：`role=button[name="View health"]` `match_count=1`，在真实页面重新计数同为 1。
- 脱敏：`SECRET-COUPON-VALUE` 与请求头 `X-Fixture-Token` 在 run 行/证据/摘要/场景里都查不到。
- 增量：B 版新增 1 控件、2 请求 → `added_keys` 精确指出；`comparable: true`。
- 场景追踪：每个候选场景引用的证据 id 全部解析成功，状态取值在允许集合内。
- 画布：节点指标与 `…/evidence/summary` 数字一致，卡片文本与详情面板可展开到证据行，刷新后仍在，390px 视口无横向溢出。
- 回归：Studio（`?file=tests%2Ftest_known_locator.py`）与失败页仍可正常打开。

真实数据追踪（`.ai-runs/e2e-round15/scenarios-trace.json`，AUDIT run `qd_d5b66d6e1f024f16`）：3 个候选场景全部 `COVERED`（`locator_value` / `target_wording`），引用证据 4/3/3 条全部解析，关联真实用例 4/4/16 条，`trace_complete: true`。

### 过程中修掉的真实缺陷

- **定位器证据为空**：`build_action_records` 读扁平 candidate 的 `kind/value`，而 discovery candidate 把 locator 嵌在 `candidate["locator"]` → 记录里 `kind=None`、`value=''`，匹配数无法复核、场景也无法按 locator 匹配。
- **输入值泄漏**：accessibility 快照里 `textbox "Search products": SECRET-COUPON-VALUE` 会整行进入 run 行的 `landmarks`；`SensitiveRedactor` 新增 `redact_typed_values`，只保留标签。
- **漏采状态**：只有 `is_new_state` 才采集，而由动作记账先建出的状态再被观察时「不新」→ 该状态永不采集；改为按「没有 capture 戳」触发（采集本身幂等）。
- **悬空证据引用**：场景引用的元素证据 id 由 locator 反推得到，实际没有那行 → 改为按动作实际点击的控件解析，拿不到就不写。
- **URL 模板丢端口**：`normalize_url_template` 用 `hostname` 会合并 `8000` 与 `5173`；保留端口。
- **资源分类误判**：无扩展名的 `/api/cart` 被判成 `document`；改为按路径 `api` 段判定。
- **迁移测试烘焙表数**：`test_runtime_migrations.py` 改为按 `Base.metadata` 推导，并新增降级往返断言。

### 本轮未做（有意）

- 不采集响应正文、请求头、Cookie、输入值、页面 HTML；不做字段级响应摘要（留 Round 16）。
- 覆盖结论仍是行为级匹配，`measures` 随响应返回；不用它宣称业务覆盖率。
- 不做 AI/Jev 语义复核、不做画布编辑/持久化布局、不建第二套 Discovery 存储。
- 多实例一致性、部署/回滚、CI、PostgreSQL 仍 **BLOCKED**（同 §3.9）。


## 3.13 Round 16（Evidence-Driven AI/Jev Intelligence，用户任务 m03748）

用户任务 m03748：让 AI/Jev 基于 Round 15 的真实结构化证据，只对确定性规则无法判定的场景做语义分析，产出可追溯、可审核的测试建议。起点 `6e8709b`。设计文档 `docs/DISCOVERY_INTELLIGENCE.md`。

### 交付

| 层 | 位置 |
| --- | --- |
| 响应契约 | `packages/qa-core/qa_core/ai/models.py`（`DiscoveryScenarioAnalysis` / `DiscoverySuggestionStep`） |
| Prompt | `packages/qa-core/qa_core/prompts/__init__.py`（`discovery_suggestion@v1.0`，已入 `PROMPT_REGISTRY`） |
| 存储 | `apps/api/app/persistence/models.py`（`discovery_suggestions`）+ 迁移 `0017_discovery_suggestions` |
| 仓储 | `apps/api/app/repositories/discovery_suggestion_repo.py`（`upsert_many` 幂等、`latest_by_scenario`、`set_review`） |
| 任务服务 | `apps/api/app/services/task_discovery_intelligence.py`（`collect` / `analyze` / `grade` / `finalize`；工具 `discovery.collect_gaps` 等四个） |
| 检索与审核 | `apps/api/app/services/discovery_intelligence_service.py`（建议、摘要、详情、审核决定、批准建用例、复用 live 任务） |
| 任务类型 | `TaskType.ANALYZE_DISCOVERY` + `apps/api/app/services/task_workflows.py` 四步计划 + orchestrator dispatch |
| API | `apps/api/app/api/quality_discovery.py`：`POST .../intelligence`(202)、`GET .../suggestions`、`.../suggestions/summary`、`.../suggestions/{id}`、`POST .../suggestions/{id}/review` |
| 画布指标 | `packages/project-model/project_model/workflow_canvas.py`（`DiscoveryIntelligenceMetrics`）+ `apps/api/app/services/workflow_canvas_service.py` |
| 前端 | `apps/web/src/features/canvas/IntelligenceSection.tsx`、`WorkflowCanvasPanel.tsx`、`canvasModel.ts`（卡片上的「AI 建议 n · 待审核 n · Jev 已评分 n」） |
| 测试 | `apps/api/tests/test_discovery_intelligence.py`（17）、`test_decision_layer.py`（32，含真实 provider/Jev 用例）、`test_workflow_canvas.py`（7）、`apps/web/tests/canvas-model.test.mjs` |

### 关键设计（为什么这样做）

- **建议层独立成表**：`discovery_scenarios.coverage_status` 始终是规则结论，AI 读入写在 `discovery_suggestions`，两者各自可追溯；`refresh_scenarios` 全量替换场景表时不会抹掉 AI 历史与人工审核记录。
- **只分析未决场景**：默认只取 `CANDIDATE_GAP` / `UNDETERMINED`，`COVERED` 不被模型重审；每次任务最多 `MAX_SCENARIOS_PER_TASK = 5` 个场景、每场景最多 12 条证据 / 12 条候选用例进入 prompt，截断如实写进 prompt 并记在 payload。
- **引用必须回查数据库**：`evidence_ids` 不在本 run 真实行内 → `REJECTED / UNKNOWN_EVIDENCE`；`related_test_case_ids` 不在本项目 → `REJECTED / UNKNOWN_TEST_CASE`；两种情况都不落任何建议文本。
- **降级不落文本**：`fallback_used` 或 provider 为 `fake`/`fallback` → `DEGRADED`，payload 无摘要无标题，假 provider 无法作者化任何建议。
- **幂等**：`input_hash` 由场景+规则结论+引用证据+候选用例+provider+model+prompt 版本+重分析 token 生成，唯一键 `(run_id, scenario_id, input_hash)`；同一输入重复请求只 `attempts += 1`，不重复计费；显式重分析产生新行而不覆盖旧行。
- **Jev 分数归一化**（本轮修掉的真缺陷）：Jev 的 `score` 是所给刻度的**期望索引**（三点刻度返回 `1.17`），原实现按 0..1 校验 → 每次打分都是 `invalid_request`（Round 12 遗留 FALLBACK 的根因）。现在 `JevDecisionProvider._rescale` 映射回 0..1，实测 `score 0.505 / confidence 0.90`。
- **分级来源与失败语义分开**：`JEV_GRADED`（接受 Jev 分数）/ `JEV_LOW_CONFIDENCE`（答了但低于 `jev.minimum_confidence`）/ `JEV_TIMEOUT` / `JEV_FALLBACK` / `JEV_UNAVAILABLE` / `NOT_REQUESTED`，`source` 只有 `jev` 或 `rules`，`calibrated` 恒 `false`；规则分级（`insufficient`/`thin`/`sufficient`）始终与 Jev 数字并列记录。
- **人工审核复用现有闸门**：`ACCEPT` / `REJECT`（必须写原因）/ `LINK_CASE` / `APPROVE_CREATE_CASE`（幂等，已建过就返回同一 id）/ `REANALYZE`；未批准不写 `test_cases`、不改自动化源码；审核记录写决定、操作者、时间、原因。

### 真实验收（`.ai-runs/e2e-round16/acceptance.json`，`console_errors: []`）

真实 Chromium + 真实 `mimo-v2.6-flash` + 真实 `jev-1.13.0`，可控页 `discovery-fixture.html` / `-b.html` / `-c.html`：**28/28 PASS**，A–H 八种场景全部覆盖（已有用例 → `COVERED` 不被重审；真实行为无用例 → `CANDIDATE_GAP` 建议；同义不同措辞 → `target_wording` 命中；证据不足 → `INSUFFICIENT_EVIDENCE` 不调模型；Provider 失败/超时 → `DEGRADED`/`JEV_TIMEOUT`；伪造 evidence_id → `REJECTED`；拒绝后重分析 → 新行且旧行保留；重复请求/刷新 → 复用任务与行）。

### 本轮修掉的真缺陷

- **Jev 打分全失败**：`score` 未按刻度归一化 → 一律 `invalid_request`；修复后真实分数入档。
- **降级原因被压平**：低置信度、超时、不可用都显示成「Jev 不可用」；现在分开。
- **通用 role locator 假覆盖**：`role=button` 的 value 就是 `button`，几乎命中所有用例 → 把真实缺口判成 `COVERED`；`GENERIC_LOCATOR_VALUES` 改为用 accessible name 匹配。
- **fixture 页未放行**：受控页需加入 `PUBLIC_PATHS` 并有路由，否则浏览器运行时拿不到页面（401）。

### 本轮未做（有意）

- 不做执行树 UI；`agent_tasks` 没有 parent 列、也没有 cost 数据，Round 16.5 需先在运行时层补真实父子关系（映射见 `docs/DISCOVERY_INTELLIGENCE.md` §7）。
- 审核反馈只作为记录保存，不回写全局匹配规则、不自动调参。
- 不新建第二套 Provider/任务状态机；不重构既有 workflow 引擎。
- 多实例一致性、部署/回滚、CI、PostgreSQL 仍 **BLOCKED**（同 §3.9）。


## 3.14 Round 16.5（Agent Execution Tree，用户任务 m04571）

用户任务 m04571：把真实执行轨迹以只读执行树呈现。起点 `254a41e`。契约与缺口文档 `docs/EXECUTION_TRACE.md`。四段：审计真实关系 → 轨迹契约 → 只读执行树 → 实时观测与节点详情 + 真实 Chromium 验收。

### 交付

| 层 | 位置 |
| --- | --- |
| 契约 | `packages/project-model/project_model/execution_trace.py`（`ExecutionTrace` / `TraceNode` / `TraceEdge` / `TraceCounts`，节点保留服务端状态原字符串，`cost` 恒 `None` + `pricing="unpriced"`，无法确证的事实进 `unknown`） |
| 迁移 | `apps/api/alembic/versions/0018_ai_invocation_step.py`（`ai_invocations.step_id` + `ix_ai_invocations_step`，可降级） |
| 写入方 | `apps/api/app/services/ai_step_context.py`（`ai_step_scope` / `current_ai_step_id`）+ `apps/api/app/services/task_execution_orchestrator.py`（步骤执行期间设置）+ `apps/api/app/repositories/ai_repo.py`（`record_invocation(step_id=...)` 默认取上下文） |
| 投影 | `apps/api/app/services/execution_trace_service.py`（`for_task` / `for_project`，节点 id 前缀 `task:`/`step:`/`invocation:`/`evidence:`/`artifact:`/`run:`/`suggestion:`，边类型 `CHILD_OF`/`INVOKES`/`PRODUCES`/`DEPENDS_ON`） |
| 接口 | `GET /api/tasks/{task_id}/execution-trace`、`GET /api/projects/{project_id}/execution-trace?limit=`（`apps/api/app/api/execution_trace.py`，只读、带项目 ACL） |
| 前端 | `apps/web/src/features/canvas/ExecutionTreePanel.tsx` + `executionTreeModel.ts` + `execution-tree.css`（深色模式，仅作用于执行树）、`apps/web/src/types/executionTrace.ts`、`apps/web/src/api/client.ts` |
| 入口 | 工作流画布内的「工作流 / 执行树」两个 tab（`view=canvas`）；任务选择器驱动，3s 轮询任务列表、SSE 事件只触发重新拉取 |
| 测试 | `apps/api/tests/test_execution_trace.py`（8 例：真实行映射与边合法性、`DEPENDS_ON` 按 step key 解析、缺 step/缺 token 标 UNKNOWN、敏感键与截断、项目视图多根、空项目、ACL 且两次读取不改表、同一场景在两个任务下节点不冲突）；`apps/web/tests/execution-tree-model.test.mjs` |

### 真实数据（dev DB）

- 8 段投影来自真实行：`task` 1 / `step` 4 / `invocation` 2 / `suggestion` 1（一次 ANALYZE_DISCOVERY），边 `CHILD_OF` + `DEPENDS_ON`（按 step key）+ `INVOKES`（invocation→step）。
- 缺失的父子任务关系、`ai_invocations.step_id`（历史行）、单价、以及 `token_source != provider` 的用量，一律由服务端标记 `unknown` 并在 UI 底部列出（`服务端无法确认: parent task id, cost, unit price`）。

### 本轮修掉的真缺陷

- **同一场景两次建议出现重复节点 id**：`discovery_suggestions` 以 `(run_id, suggestion_id)` 唯一，同一 `suggestion_id` 会在不同 run 出现两次 → 节点 id 改用行主键 `suggestion:{row.id}`（项目视图一次合并 6 个任务时暴露，真实浏览器控制台报 React duplicate key）。
- **节点详情没有回到原页面的入口**：契约新增 `TraceNode.links`，task → `/runs/tasks?taskId=`、run → `/runs/{id}`、suggestion → 该 run 的画布视图。
- **详情缺少场景可追溯字段**：suggestion 节点 `outputs` 增加 `scenario_id` / `run_id` / `cited_evidence`（真实列值），模型没有引用证据时点击节点仍能定位到该场景。
- **未计量用量被显示成数字**：`token_usage` 仅在 `token_source == "provider"` 且两值非空时存在，否则 `unknown += ["token_usage"]`，UI 显示「未计量」，费用恒显示「未计价」。
- **窄视口把流水线压到不可读**：执行树按宿主宽度决定缩放，390px 下首列可见、卡片文字可读（与流水线画布同一策略）。

### 本轮未做（有意）

- 不加 `parent_task_id`：`agent_tasks` 没有 parent 列，也没有真实的父子任务数据；本轮只把「同一任务内的阶段」和「任务 → 步骤 → 调用」投影出来，父子关系记为 `UNKNOWN`（Round 17 若要可编辑工作流需先有任务定义版本化，见 `docs/EXECUTION_TRACE.md` §9）。
- 不做费用计算（无价格表）、不估算 token、不把 tool 当 agent、不新增第二套任务状态。
- 不修改流水线画布的行为；执行树只是同一路由下的第二个视图。

### 真实验收（`.ai-runs/e2e-round16.5/acceptance.json`，`console_errors: []`）

真实 Chromium 1560×1000 + 真实 `mimo-v2.6-flash` + 真实 `jev-1.13.0`，受控页 `examples/demo-shop/site/discovery-fixture-d.html`：**13/13 PASS**——真实探索出证据 → 真实 ANALYZE_DISCOVERY 任务 → 运行中节点实时增加 → 任务节点状态与服务端一致 → 每个模型调用挂到本任务（经 step）→ Jev 的 provider/model/fallback 取自真实行 → 每个耗时等于服务端记录 → 未计量调用不显示数字也不发明费用 → 刷新重建同一轨迹 → 断线重同步不重复节点 → 节点详情可达证据/场景 → 流水线画布不受影响 → 手机视口可读且无裁切 → 无控制台错误。截图 `screenshots/before-pipeline-canvas.png`、`after-execution-tree.png`、`after-node-detail.png`、`after-execution-tree-reloaded.png`、`after-execution-tree-mobile.png`。


## 4. 环境基线（WSL / Linux）

- 仓库路径：`/home/hans/self-github/ai-qa-platform`（WSL 原生文件系统，非 `/mnt/c`）
- Python 3.13 + `uv`；Node 24 + `pnpm`；`.venv` 与 `node_modules` 已按锁文件在 Linux 下重建
- Playwright **1.62.0**（`apps/api` 与 `apps/web` 均为该版本；1.63.0 被显式禁止）
- 浏览器：`playwright install chromium` 已安装，bundled Chromium 可正常启动
- 服务状态：最近检查 `127.0.0.1:8000` API 与 `:5173` Web 均不可达；本次测试由隔离 TestClient/临时 Uvicorn/Vite 按需启动并清理。项目 SQLite 路径为 `runtime/ai_qa_platform.db`；PostgreSQL/Docker 不可用。
- 详见 `.ai-runs/enterprise-continuation/environment-audit.md`；无系统级改动，Playwright 截图所需 Noto Sans CJK 安装于 `~/.local/share/fonts/`

## 5. 已完成并验证

| 项目 | 证据 |
| --- | --- |
| **Round3 Discovery→Coverage 真实 Chromium + UI 验收** | `.ai-runs/night-continuation/round-3/evidence/discovery-to-coverage.json`; includes `automation-binding-review.png`. Controlled local site, fixture AI/Jev, real BrowserRuntime/Chromium/Playwright worker; UI creates draft, reviews scenario, selects case, manually creates ACTIVE binding, starts real run, refresh/reload verifies VERIFIED, and project switching shows isolation. |
| **Studio 真实调试全流程（历史第二轮）** | `round-2/studio-debug-acceptance.md`（31 项声称 PASS；当前 Round-1 必须重新实测） |
| **真实 AI + Jev 失败修复（API + UI）** | `round-2/ai-jev-live-acceptance.md`（真实 provider/Jev、信心 1.0、人工审批、精确 pytest 复验、回滚；screenshots 在 `round-2/screenshots/failure-ui/`） |
| **D8 AI Disabled 可靠性** | `round-2/ai-disabled-provider.md`（43 GET 路由无 5xx；真实 AI 操作明确 502） |
| **失败修复矩阵映射** | `round-2/failure-repair-matrix.md`（包含 duplicate apply SQLite 回归、Jev loopback 503 与剩余远端 outage/进程中断边界） |
| **Discovery → Coverage 下游闭环** | `round-2/test-results.md` D5：真实 local browser + real AI/Jev requirement/case，人工 Playwright ACTIVE binding，browser TestRun PASSED，显式 refresh 后 coverage VERIFIED；真实 UI 按钮点击成功过一次，strict harness 待 provider 恢复后复跑 |
| 仓库/环境恢复，无 Windows 路径残留导致的功能缺失 | `environment-audit.md` |
| 后端测试基线（真实运行，非沿用旧报告） | `test-results.md` / `.ai-runs/enterprise-continuation/logs/` |
| 前端 typecheck / lint / build | `test-results.md` |
| 链路 A：需求 → AI 分析 → Jev 决策 → 场景 → 用例 → 自动化 → 执行 → 结果 → Knowledge Graph | `logs/live-chain-a.log`（真实 provider + 真实 Jev，无 fallback） |
| 链路 B：失败 → 证据 → AI 诊断 → Jev 决策 → 修复提案 → 人工审批 → 写回 → 精确复跑 | `logs/live-chain-ab.log` |
| 真实 AI provider 健康检查（`REAL_CONNECTED`，`fallback_active=false`） | `/api/ai/status` |
| 真实 Jev 运行时健康检查（`CONNECTED` / `READY`） | `/api/decision/runtime-check` |
| UI 13 个主页面渲染 + 无控制台错误 + 截图 | `screenshots/*.png`、`ui-ux-audit.md` |

## 6. 本次修复的缺陷

### P1（第二轮 D7）— Studio 深链会静默打开另一个文件

- 现象：`/projects/<id>/studio/file/tests/test_known_locator.py` 最终把 URL 的 `file=` 改成
  `tests/test_shop.py`，编辑器、断点与调试目标全部落到另一个文件；用户以为在给 A 设断点，实际调试 B。
- 根因：`WorkspacePage.tsx` 的上下文归一化用「第一条绑定用例的文件」覆盖显式 `file=`；
  `initialOpenFilePath` 只要选中用例就优先绑定文件。
- 修复：`workspaceContext.ts` 新增 `resolveCanonicalFile()`（显式 file > 失败调试上下文 > 绑定文件），
  归一化与 `initialOpenFilePath` 都改用它；新增 3 个前端回归用例。
- 回归：`pnpm --filter @ai-qa/web test` → 160 passed；真实浏览器复验断点落在 `test_known_locator.py:12`。

### P2（第二轮 D6）— `DELETE /api/debug/sessions/{id}` 对已关闭会话返回 404

- 现象：DAP `terminated` 后前端调用关闭接口，浏览器控制台出现 404 报错。
- 修复：DELETE 改为幂等（已关闭 → 200 `{"closed": false}`），未知/他人会话仍 404；
  新增 `test_debug_close_is_idempotent_for_already_closed_sessions`。

### P1（第二轮 D8）— AI/Jev Disabled 时只读 API 500

- 现象：在 `QA_AI_ENABLED=false JEV_ENABLED=false` 下，`GET /api/ai/status`、`/api/runs`、`/api/failures`
  因 Provider 初始化异常返回 500；健康探针本身则能报告 disabled。
- 根因：`ProductionQAOrchestrator.__init__` eager 构造 Provider，导致任何依赖该服务的读取端点在 handler 执行前失败。
- 修复：`packages/qa-core/qa_core/orchestrator/orchestrator.py` 延迟到首次真实 Provider 使用时解析 Provider；
  只读 API 正常可用，AI 写操作仍失败为明确 502，不会静默回退。
- 验证：真实禁用配置扫查 43 个无参数 GET 路由，0 个 5xx；隔离测试覆盖 status/runs/failures + AI 分析失败语义；
  相关测试 20 passed。详情 `.ai-runs/enterprise-continuation/round-2/ai-disabled-provider.md`。

### P1 — Discovery 暴露终态早于 Quality Map 持久化（已在 `02210de` 修复）

- 现象：`_finish()` 先写 `COMPLETED`，再写 Quality Map；API poller / UI 可能读到终态后停止轮询，覆盖率仍空；原 live test teardown 也可在该窗口取消 map task。
- 修复：先构建/持久化 map，再写 terminal status/event；投影异常转为明确 `FAILED`。stop/pause/resume 与 finalization 以 per-run lock 线性化；finalization 已开始时 stop 返回 HTTP 409，不会假装接收。运行 task cancel 会请求 STOPPED；shielded finalizer 支持重复 cancellation 后继续完成持久化。
- 验证：`apps/api/tests/test_quality_discovery.py` 62 passed in 32.04s；真实 local-browser Discovery 用 `openai-compatible` / `mimo-v2.6-flash` 与 Jev `jev-1.13.0` 执行，1 passed，terminal response 已包含 quality map/coverage/workspace scan。全仓 lint/OpenAPI/i18n 与 `git diff --check` PASS；独立 review 无 correctness finding。日志 `.ai-runs/enterprise-continuation/round-2/logs/live-discovery-finalization.log`；详情见 round-2 `test-results.md`。
- 限制：finalization/refresh lock 为单进程状态，未验证多 API worker/PostgreSQL 并发；D5 的 Discovery→gap→case→binding→execution→coverage refresh 已有真实 API 链，真实 UI 按钮曾点击成功，但最新 strict harness尚未因 Provider timeout完成最终绿跑。

### 第二轮真实修复闭环（已通过但矩阵未闭合）

- 真实 AI：`openai-compatible` / `mimo-v2.6-flash`；真实 Jev：`jev` / `jev-1.13.0`，confidence 1.0；fallback 均为 false。
- 真实浏览器 UI：人工审批 → 修复写入 → 精确测试节点通过 → 人工回滚恢复原始字节；1 passed，证据和 screenshots 见 `round-2/ai-jev-live-acceptance.md`。
- 风险：同一 live workflow 后续因真实 AI 返回 `AI provider unavailable` 安全阻断；另一条带干扰控件的输入被 AI 分类为 `TEST_DATA_ERROR`。不可宣称 provider 稳定或模糊页面分类已验收。
- 矩阵剩余远程 Jev outage 未诱发、源码/提案持久化前中断、verification worker restart，详见 `round-2/failure-repair-matrix.md`；真实 Jev 客户端对 loopback HTTP 503 fail-closed 已测试；duplicate Apply 和 stale-source 已有 SQLite 回归。

### P1 — 验收夹具把浏览器 channel 写死为系统 Chrome（跨平台缺陷）

- 现象：链路 A 第一次真实运行失败，日志为
  `BrowserType.launch: Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome`
  （发生在被测工作区里生成的 `tests/test_verification_panel.py`）。
- 根因：`apps/api/tests/test_live_enterprise_journey.py` 与
  `apps/api/tests/test_live_locator_repair_acceptance.py` 生成的测试源码中硬编码 `channel="chrome"`
  （Windows/macOS 开发期为了绕开 bundled Chromium 的问题）。
- 修复：改为环境变量 `AI_QA_ACCEPTANCE_BROWSER_CHANNEL`，默认 `None`（使用 Playwright bundled Chromium，
  在 Linux/WSL/CI 上可直接运行）；仅在不支持的宿主上用 `AI_QA_ACCEPTANCE_BROWSER_CHANNEL=chrome` 覆盖。
- 回归：链路 A 由 `1 failed / 1 passed` 变为 `2 passed`。

### P1 — Web 生产构建 Node 堆溢出（交付阻断）

- 现象：`pnpm --filter web build`（CI 同一命令）报
  `FATAL ERROR: Ineffective mark-compacts near heap limit … JavaScript heap out of memory`，exit 134。
- 根因：Vite/Rollup 转换阶段超过 Node 默认 2 GB old-space 上限（本机 WSL 共 7.9 GB，非宿主内存不足）。
- 修复：`apps/web/package.json` 的 build 脚本改为
  `tsc -b && node --max-old-space-size=4096 node_modules/vite/bin/vite.js build`
  （不用 `NODE_OPTIONS=` 前缀是因为 Windows `cmd.exe` 下不生效）。
- 遗留：`MonacoEditorPane` chunk 4.03 MB，见 `implementation-log.md` D2。

### P1 — 健康探针预算小于 AI 请求超时，UI 误报「部分能力受限」

- 现象：`/library`、`/recorder`、`/settings` 顶栏长期显示「部分能力受限：常规 AI 运行健康」，
  但同一时刻真实 AI 验收通过；`/api/ai/system-health` 报 `PROBE_TIMEOUT` 而 `/api/ai/status` 报 `REAL_CONNECTED`。
- 根因：`platform_health_service` 给 `ai` 探针固定 15 s 预算，而配置的 AI 请求超时是 30 s，
  且该探针实际发出两次 provider 调用（`check_health` + 合成 `stream_complete`）。
- 修复：后端探针预算改为 `max(15, 2 × config.timeout)`；前端把「探针超时」与「能力受限」区分开
  （`apps/web/src/components/readinessNoticeModel.ts`）。
- 回归：`/api/ai/system-health` 由 `degraded` → `healthy`；顶栏在 3 个页面由「显示」→「不显示」。

## 7. 未完成 / 待办

- [x] Round4 全页真实浏览器巡检（14 路由 × 4 视口 + 7 需求标签页 + 交互点击）与失败概览断言详情修复，结论见 §3.1。
- [x] Round6 独立验收：两份跨阶段/前端完整性审计、四个前端 P1 与两个后端 P2 修复、真实浏览器错误面验收、Studio 真实验收、SQLite/PostgreSQL 全量、前端测试/类型/构建/lint/OpenAPI 契约，结论见 §3.3 与 `.ai-runs/night-continuation/final-report.md`。
- [ ] Round6 未完成项（不声称完成）：浏览器内失败修复链路（`test_live_locator_repair_acceptance.py -k through_browser_ui`）未 settle，需 provider 恢复后单次复验；Live Browser Agent 本轮按策略阻断（Jev 置信度 0.06 < 0.70），无通过证据；覆盖率两套口径未统一。
- [ ] Round4 未做且证据不支持改动：IA/布局重排（reviewer 认为现有结构连贯）；字体自托管（离线环境）；这两项不得当作已完成。

Round3 核心目标已通过；Round2 旧矩阵仍未闭合，下一 P0 是全平台项目权限。

- [x] Discovery、结构化 RequirementRisk/TestScenario、TestDesign、TestCase、ACTIVE binding、真实 Run、latest execution 与 map coverage 的关联/状态；没有将“有用例”当成通过。
- [x] 实际 UI 打开并审核草稿、场景设计、生成并选中用例；真实 Chromium 探索 loopback 商店、实际 Playwright 执行、Refresh/reload、另项目切换后的数据空态。
- [x] latest matching execution 不再受旧 Run 排序或 500 项截断误导；外国项目 Workspace binding 被拒绝。
- [ ] 系统级项目 ACL：覆盖所有资源 API、list/query/body/WS 的 owner/team授权与 legacy project认领规则；Round3 E2E 仅证明 tenant数据投影/Workspace绑定项目一致，不能替代 authorization。
- [ ] AI + Jev 修复审批安全决策矩阵：真实高置信度 UI/API 成功及低置信度 fail-closed、SQLite duplicate Apply/stale-source/持久化后恢复和真实 Jev 客户端 loopback 503 fail-closed 已验证；本接管新增 verification freshness / proposal identity / rollback retry persistence / duplicate rollback event 定向覆盖，全仓回归通过。尚缺远程 Jev outage、源码/提案持久化前 interruption、verification worker restart 和 PostgreSQL 并发证据。已覆盖 mocked human reject、AI/Jev readiness block、rollback；逐项证据见 `round-2/failure-repair-matrix.md`。
- [ ] AI 诊断需加强对存在其他控件时的分类稳定性；一次真实页面干扰控件试验把 locator 错误分类成 `TEST_DATA_ERROR`，当前 clean fixture full chain 通过，见 `round-2/ai-jev-live-acceptance.md`。
- [x] Discovery → Coverage API/integration 闭环：真实探索 → AI requirement/case generation → 人工编写 active Playwright binding → browser execution → explicit refresh → VERIFIED；D5 evidence in `round-2/test-results.md`.
- [x] Discover 的 Refresh Coverage 按钮已在真实浏览器点击并显示成功 / VERIFIED；历史 run-switch feedback reset 有实现和确定性覆盖。
- [x] Round3 strict controlled-site Chromium + actual UI journey: UI creates draft, opens/reviews scenario, selects case, configures binding, starts real run, clicks Refresh Coverage, reloads and switches project; report/screenshot evidence lives in Round3. Separate real AI/Jev provider acceptance remains historical Round2 and must not be inferred from this deterministic-fixture run.
- [x] Studio 核心真实浏览器 acceptance：attempt 19 通过编辑/保存、真实 debugpy 断点与 stepping/continue、Pause/Stop、重复会话、失败证据及 desktop/tablet/mobile；证据 `.ai-runs/night-continuation/round-1/attempt-19/`。
- [x] 最终全仓 regression、Python/Web lint、typecheck、build、document-width viewport assertion。
- [x] Round-1 reports 更新、最终独立 reviewer 无 actionable finding。
- [x] Round3 实现本地 semantic commit `f64f711`（no push）；Round3 evidence stays local/untracked.
- [x] PostgreSQL 集成测试：本轮用隔离的本地 PostgreSQL 18.6（`embedded-postgres`，`127.0.0.1:55432`）跑通 API 全量 + 迁移/模型 drift 护栏，见 §3.2 Part 1。仍未在本机验证 CI 的 `postgres:16` service job。
- [x] Worker 真实进程集成测试：`apps/api/tests/test_worker_process_integration.py` 起临时 API + 真实 `python -m worker.main` 子进程，覆盖提交/认领/执行/结果/取消/超时/崩溃恢复/重复请求/资源回收，见 §3.2 Part 2。真实 Jenkins 或分布式集群仍 NOT RUN（无集群）。
- [ ] 系统级 project ACL（P0，见 §8）：覆盖全部资源 API 的 owner/team 授权与 legacy project 认领规则；本轮只修了 artifact 路径穿越与修复审计，不代表授权完成。
- [ ] Worker job lease/heartbeat requeue：本轮修了「死 worker 遗弃 job 会被回收」，但没有 lease 续租/超时重投递；属下一轮。
- [ ] Studio 的 Monaco 全量导入（`MonacoEditorPane` chunk 4.03 MB）按需拆分，需配套浏览器回归
- [ ] 构建峰值内存与新 Bundle 体积证据（第二轮性能小节）
- [ ] 暗色主题验收（低优先级，不得抢占核心功能时间）

> RBAC 与审计日志**已经存在真实后端实现**（`apps/api/app/api/authz.py` 中央策略表 +
> `apps/api/app/api/audit.py` + `apps/api/app/repositories/security_audit_repo.py`），
> 后续不要新建第二套，应扩展已有策略表与审计表。

## 8. 已知 Bug / 阻断

- **Round 12 现状（以此条为准，下面都是历史快照）**：P0 无新开项（两处 P0 级运行状态错误已在本轮修复）；P1 无新开项。本轮修掉两处运行状态错误（用户停止探索落 `BLOCKED`、`ai_invocations` 永久 `RUNNING`）与一处开发启动器端口缺陷（`TIME_WAIT` 被当成端口占用）。仍为 **BLOCKED** 的是：多实例一致性（无 lease/heartbeat，启动收敛是全量的）；部署/回滚/CI/PostgreSQL（无环境）。P2 观察：失败页内联分析与 `FIX_FAILURE` 任务两条修复面的显示不一致；等待审批无过期策略；Jev 评分通道 `FALLBACK`；`provider_connection` 探针假阴性。详见 §3.9 与 `.ai-runs/e2e-round12/audit-report.md`。

- Round6 新增结论：
  - **已修**：四个前端「异步失败被静默」（RunsPage/FailuresPage/QualityPage/SecurityPage）；禁用 TestRail 时伪造 `SUCCESS` 审计；登录审计 IP 硬编码。
  - **仍未修**：P0 project ACL（下方企业 blocker）；覆盖率存在需求加权与按特性两套计算可能不一致；`AIProviderRegistry` 未 `configure_runtime` 时会回落 fake provider；审计行字段仍不完整（`target_resource` 无文件路径、部分 actor 为 `system`）；`POST /api/jobs/{id}/result` 抢输一方仍返回成功；API 与 Worker 制品根目录不一致会静默丢弃制品。
  - 真实 AI/Jev 只在单次时间窗内跑通完整链路；provider 超时期间平台按设计阻断自动修复（未替换 Fake），但 UI 未展示阻断原因（`_runtime_readiness` 的 `reason` / `ai_failure_reason`）→ 建议后续把该原因显示到失败修复界面。
  - 浏览器内失败修复验收日志出现 `sqlite3.OperationalError: database is locked`（本地 SQLite 并发写入），需在复验时一并排查是否为 harness 并发导致。
- Round5 新增结论：
  - **已修**：artifact 下载可被篡改为任意文件读取（storage root containment 校验 + 负向测试）；AI 修复 apply/rollback 无审计（现在写 `REPAIR_APPLY`/`REPAIR_ROLLBACK`）；job 取消不取消 run；worker 崩溃后 run 永久 RUNNING；job 终态可被覆盖；PostgreSQL 无法执行 Alembic 迁移（`alembic_version VARCHAR(32)`）。
  - **仍未修（不声称完成）**：没有系统级 project-resource ACL（同下行）；pytest 子进程不是 OS 沙箱（以宿主用户运行）；worker 无 lease/续租机制（只靠心跳超时回收）；`ArtifactORM` 没有 project_id 列，artifact 的可见性只能靠上传者约束；CI 的 `postgres:16` job 未在本地验证（本地为 18.6）。
  - PostgreSQL 测试限制：同一进程内先为 PG 建过表的 `MetaData` 不能再为 SQLite `create_all` 循环 FK（SQLAlchemy 行为），因此 `test_backend_parity.py` 在 PG 下 skip 那一项，另以真实迁移的 SQLite 级联测试替代。SQLite 生产 schema 由 Alembic DDL 建立，不受影响。
- 已确认的企业安全 blocker：191 条 API route 尚无系统级 project-resource scoping；`ProjectORM` 无 owner/team，`authorize_request` 仅检查全局角色。必须覆盖所有资源 ID / query / body / list / WebSocket，不能用单路由 ACL 代替。Legacy ownerless projects 的迁移规则未获决策；安全建议为 admin-only 直到显式 claim，禁止静默分配 owner。
- Studio locale-tolerant selectors、debug-view flex sizing、phone DebugPanel layout 已修复并在 attempt 19 实测；编辑器 161px desktop / ≥140px tablet-mobile，mobile details 纵向滚动可读，documentWidth 在 1440/768/390px 均不超过 viewport。
- Discovery 最终化修复已提交：终态必须等 Quality Map 写入后才暴露；finalization 期间 stop/pause/resume 返回冲突，重复 task cancellation 下 shielded finalizer 与 BrowserRuntime cleanup 均收敛。D5 refresh endpoint uses terminal guard and per-run lock; double-refresh regression observes serialization in one process. No multi-process/PostgreSQL evidence.
- 项目权限仍是 P0/P3 架构风险：`ProjectORM` 没有 owner/team 关系，RBAC roles 全局；本次只限制非管理员刷新自己发起的 run，不能据此宣称系统级 project isolation 已完成。
- 已提交 CAS/recovery/stale-history 修复（`919cfcd`）；Jev loopback 503 fail-closed 集成测试后，`test_failure_workflow.py` **47 passed / 1 warning**。参数化恢复 **2/2 passed**，PATCH_READY 并发场景 20/20 次通过；stale `ROLLED_BACK` source 不会追加 recovery event。Round-2 历史后端回归为 829 passed / 9 skipped / 55 warnings；Round3 最终全仓 834 passed / 10 skipped / 55 warnings，见 §3。当前 rollback 是 filesystem + DB 两阶段操作，无法跨两者原子提交；先持久化 `ROLLBACK_PENDING`，再用 hash-guarded restore，最后保存 `ROLLED_BACK`。DB 最后一步失败时保留 durable pending intent，调用方重试可恢复；不引入第二 Runtime。
- 真实 AI 曾把带干扰控件的 locator 失败分类为 `TEST_DATA_ERROR`，暂不证明模糊页面分类稳定。
- Round4 巡检环境限制：本机无法访问 `fonts.googleapis.com`，`document.fonts.ready` 永不完成会让 Playwright 全页截图卡在 `waiting for fonts to load`；harness 阻断该域名并同图重试 3 次。应用字体回退正常，但「离线/内网首屏字体」未做产品级自托管，属已知限制，不作为 UI 缺陷处理。
- `apps/api/tests/conftest.py` 为每项测试创建隔离 SQLite，初始无项目；未选择项目时 `/requirements`、`/test-cases`、`/recorder` 回到项目页是设计行为。Runtime sample DB 与验收 DB 分离，禁止用 sample DB 做回归或修改用户数据。

## 3.15 Round 17（版本化工作流 Studio，任务 m05387 第 1 轮）

**目标**：在既有 React Flow 画布上做「可编辑、版本化、可审核」的工作流定义，并把定义与执行轨迹彻底分开（定义≠运行状态，不建第二套执行器）。

**交付**：`packages/project-model/project_model/workflow_definition.py`（24 节点白名单 `CATALOGUE`，含 risk/writes/inputs 元数据；`validate_graph` 校验未知类型、缺输入、悬空边、环；`execution_order` 拓扑排序）；迁移 `0019_workflow_definitions`（`workflow_definitions` + `workflow_definition_versions`，cheksum 不可变）；`WorkflowDefinitionRepository`（乐观并发 `base_checksum`）、`WorkflowDefinitionService`（`compile_plan` 编译成既有 `TaskStepSpec`、`compare_graphs`、`execution_diff`）；9 个端点（草稿 CRUD、校验、发布、版本列表/详情、对比、执行对比）；前端 `apps/web/src/features/canvas/{workflowEditorModel.ts,WorkflowEditorPanel.tsx,workflow-editor.css}`，入口 `?canvas=editor`（服务端仍是唯一权威，刷新可恢复）。

**真缺陷修复**：① 保存后 `dirty` 不清空，因为 `sameGraph` 把节点坐标算进相等性（布局是视图状态，已排除）；② 模式切换标签渲染出原始 i18n key；③ 重名工作流把 `sqlite3.IntegrityError` 冒到界面（改为 `WorkflowNameTaken` → 409）；④ 慢加载覆盖刚创建的草稿（`loadSeq` 守卫）。

**判定**：A Definition **PASS**（白名单 + 校验 + 不可变发布）；B Editor **PASS**（真实浏览器 20/20：创建/编辑/连线/撤销/自动布局/校验/保存/刷新/发布/权限/版本对比）；C **DAG Execution BLOCKED** —— 定义能编译成既有运行时的计划，但没有任何经批准的端到端执行路径被验证过，按任务要求不另建调度器。

## 3.16 Round 18（运行时一致性：任务租约与 fencing）

**审计结论**：任务认领本来就是原子的（`claim_for_execution` 条件 UPDATE），但四处启动收敛把「未完成」当成「已放弃」，且终态写入没有所有权校验 —— 滚动重启会误停别的实例正在跑的任务。

**交付**：迁移 `0020_task_lease`（`lease_owner`/`lease_token`/`lease_expires_at`）；`claim_for_execution(task_id, owner, lease_seconds)` 返回 fencing token；每任务心跳（`LEASE_SECONDS=90`、`HEARTBEAT_SECONDS=20`）；`TaskExecutionOrchestrator._finish` 经 `holds_lease` 校验（失租记录 `task.lease_lost` 事件、不写终态）；优雅退出时释放租约；四处收敛改为「按年龄判定过期」。文档 `docs/TASK_LEASE.md`。

**验证**：`apps/api/tests/test_task_lease.py`、`apps/api/tests/test_multi_instance_recovery.py`（新鲜行在同伴启动后存活、过期行仍被回收），两处旧测试因写死「新鲜行也会被回收」而更新；真实双进程演练 `.ai-runs/overnight-delivery/rounds/r18_two_instances.py` → **8/8**（`.ai-runs/overnight-delivery/regression/r18-two-instances.json`）。

**判定**：单主机多进程 **PASS**；多主机 `MULTI_INSTANCE_PASS` **BLOCKED**（无 PostgreSQL 与第二主机）；跨副本的 cancel 未做 fencing，已记录为缺口。

## 3.17 Round 19（自然语言 → 候选工作流）

**交付**：`WorkflowPlannerService.plan()` —— 一句话 → 候选 DAG，只允许 Round 17 白名单类型，服务端校验（未知类型、环、缺输入、悬空边），AI 只能提议、不能保存；`POST /api/projects/{id}/workflow-plan`（503 表示 provider 不可用，不落库）；前端 `WorkflowPlannerPanel.tsx`（`?canvas=planner`），人工确认后才写草稿。

**关键边界**：模型输出里的节点类型必须在 `CATALOGUE` 内，否则逐条报错；计划不写任何 definition 行；provider 未配置时返回 503 而不是伪造计划。

**判定**：Planner **PASS**（真实验收 15/15，真实 provider）；由计划直接执行仍是 `DAG_EXECUTION BLOCKED`（继承 R17 C）。

## 3.18 Round 20（CI / PostgreSQL / 部署演练）

**CI**：`.github/workflows/ci.yml` 只在 push 到 `main` 时触发，本任务禁止 push → **CI 服务 BLOCKED**；改为逐条复跑 CI 命令，证据 `.ai-runs/overnight-delivery/rounds/r20_ci_parity.md`。因此发现 CI 的 `pytest apps/api` 命令一直是红的（`app/api/test_designs.py` 是路由模块却被收集 → `apps/api/conftest.py` 加 `collect_ignore_glob`），而根目录 `pytest` 因 `testpaths` 不包含它而一直绿。

**PostgreSQL 16 通道**（`postgres:16-alpine`，端口 55432）一次跑出 5 个缺陷：① `stored_artifacts.created_by` 是 VARCHAR(36)，但录制器写入的是标签（`Recorder · <case>`），PG 直接 `StringDataRightTruncationError` 让发现→覆盖 E2E 运行 `ERROR`（迁移 `0021_artifact_actor_width` 加宽到 100，对齐 `test_runs.requested_by`）；② `ai_invocations.step_id` 的索引在迁移里叫 `ix_ai_invocations_step`、模型生成 `ix_ai_invocations_step_id`，`compare_metadata` 永远报漂移（在 `__table_args__` 显式命名）；③ 上述 pytest 收集问题；④⑤ 两处过时测试（Round 18 之后回收改为按年龄判定，测试仍按「新鲜行也回收」断言）。

**部署演练**（`.ai-runs/overnight-delivery/rounds/r20_deploy_drill.py`，隔离 compose 项目 `aiqa-r20`、独立 env 文件、备用端口）→ **12/12**：镜像构建、API 启动 + DB 健康、容器自带 healthcheck 变 healthy、Alembic 在 PG 上降一级再升回 head、种子管理员可登录、容器内可写 PG、逻辑备份 97 KB、**恢复到第二个库后行数与迁移版本一致**、硬编码密钥的配置 fail-fast（exit 1 + 明确原因）、Web 镜像独立启动并返回 SPA、`docker compose stop api` 为优雅停机（exit 0）、`down -v` 不留残骸。演练前必须先修两个镜像级缺陷：API Dockerfile 的 `HEALTHCHECK … CMD-SHELL`（compose 关键字，`docker build` 直接失败）与 Web 镜像的字面 upstream `api`（无兄弟容器时 nginx 启动即崩）。另移除三个服务的硬编码 `container_name`（使 `-p` 生效、允许同机第二套栈）并补资源上限，删除仅作 include 的 `compose.yaml`（否则每次 compose 调用都告警「两个配置文件」）。

**判定**：CI 命令对等 **PASS**；PostgreSQL 通道 **PASS**；单机部署演练 **PASS**；CI 服务、多主机 PostgreSQL、Windows 宿主 **BLOCKED**。

## 9. 最后执行的测试

- **RC Hotfix 1（任务取消 fencing，提交 `9785688`，迁移 `0022_task_cancel_request`）**：取消拆成「请求」（`agent_tasks.cancel_requested_at/by`，`TaskRepository.request_cancel` 单条条件 UPDATE，永不写终态）与「终态」（只有 `finish_fenced` 能写：租约 owner+token 匹配，或确认无人持活租约），属主在 DAG 循环头 / 步骤边界 / 心跳三处识别请求并自行终止，本会落 `FAILED/BLOCKED` 的结局改写为 `CANCELLED` 并把原结局留在 `verification.interrupted_outcome`。后端全量 `uv run python -m pytest apps/api/tests packages -q --timeout=900` → **SQLite 1005 passed / 12 skipped / 63 warnings / 1278.88s / exit 0**（`/tmp/h1-sqlite-final3.log`）；**PostgreSQL 16 全量**（`AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test`，同范围）→ **1009 passed / 8 skipped / 61 warnings / 2699.98s / exit 0**；fencing 组在 PG 上 18 passed / 61.14s，`test_runtime_migrations.py` 6 passed，`test_agent_tasks.py -k cancel` 5 passed。真实 Chromium + 真后端 + 真 SQLite `rounds/r18b_cancel_acceptance.py` → **14/14 PASS，`failed: []`，无控制台错误**（证据 `rounds/r18b-cancel-acceptance.json`，任务 `16822f43ce004effb2dc07a94f8bc228`：02:12:11 创建 → 02:12:14 取消 → 02:12:16 `CANCELLED`）。前端 227 pass + `tsc`/`eslint` 干净，`ruff check`/`format`（490 files）干净，OpenAPI current，i18n 3391 keys。全量跑里唯一的失败 `test_startup_without_credentials` 是子进程 120s 上限在高负载下超时（单跑 16.03s 通过），已把上限提到 300s 并复跑通过。

- **RC Freeze（本轮，用户任务 m07860，零产品改动）**：冻结树上复跑 —— 前端 `pnpm --filter @ai-qa/web test` → **227 pass / 0 fail**，`tsc --noEmit` 与 `eslint src --max-warnings=0` 无输出；真实 Chromium `.ai-runs/overnight-delivery/rounds/r17_acceptance.py` → **24/24 PASS，`failed: []`**。恢复路径实跑 —— `scripts/backup_db.sh` + `scripts/restore_db.sh` 后与活的开发库逐表比对 **44/44 一致**（`alembic_version` 两侧均 `0021_artifact_actor_width`）；空库 `alembic upgrade head` → `0021` / 44 表，`downgrade base` 后 36 表（基线迁移有意保留），再 `upgrade head` 回到 44 表。后端全量沿用 §3.22 的双通道数字（SQLite 996/11/890.37s、PostgreSQL 999/8/2066.93s），本轮未重跑。

- **最终工程收尾（本轮，用户任务 m07699，代码 `b8958e2`，代码冻结）**：先带 `--durations=25` 跑一次定阈值（`regression/durations-sqlite.log`，最慢 `test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e` **166.82s**，第二名 13.40s），再加 `pytest-timeout>=2.4.0`（`pyproject.toml`：`timeout = 180`、`timeout_method = "thread"`；该 e2e 标 `@pytest.mark.timeout(900)`）。双向验证：`--timeout=2` 杀掉一个真实 10.9s 的用例；同一 e2e 在 `--timeout=30` 下靠自带标记通过（168.77s）。最终代码后端 **SQLite 全量 996 passed / 11 skipped / 63 warnings / 890.37s / exit 0**（`regression/final-sqlite.log`）、**PostgreSQL 16 全量 999 passed / 8 skipped / 61 warnings / 2066.93s / exit 0**（`regression/final-postgres.log`，同范围 `apps/api/tests packages`；差的 3 条是 `postgres` 标记用例在 SQLite 下跳过）。`ruff check .` / `format --check .`（488 files）干净、`scripts/export_openapi.py --check` current、`scripts/i18n_check.py` 3390 keys、前端 **227 pass / 0 fail** + `tsc`/`eslint` 干净、真实 Chromium `rounds/r17_acceptance.py` 在最终代码复跑 **24/24 PASS，`failed: []`**。唯一一次失败 `test_analysis_timeout_ends_the_run_with_an_explicit_retryable_error` 判定为**测试侧竞态**（0.5s 预算在 provider 调用被进入前就耗尽），产品侧行为正确；修测试（预算 5s、等待 10s）后该文件 50 passed。旧记录分类见 §3.22 表格。

- **Round 17 复核审计（用户任务 m07420）**：按原 7 个 Phase 逐条核实已交付的 Studio，修复 1 个 P1（拖拽布局永远无法保存），补齐 4 条真实验收。后端 SQLite 全量 `uv run python -m pytest apps/api/tests packages -q` → **996 passed / 11 skipped / 63 warnings / 706.27s**；`ruff check .` / `ruff format --check .`（488 files）干净；前端 `pnpm --filter @ai-qa/web test` → **227 pass / 0 fail**（+2 = `sameLayout` 的布局/亚像素用例），`tsc --noEmit` 与 `eslint src --max-warnings=0` 干净；真实 Chromium `.ai-runs/overnight-delivery/rounds/r17_acceptance.py` → **24/24 PASS，`failed: []`**（新增：循环草稿发布 422、无人工批准步骤的写节点发布 422、restore 只改草稿、拖拽后保存并在刷新后保持）；证据 `rounds/r17-acceptance.json`，说明 `rounds/r17-reaudit.md`。

- **Round 22（发布候选审计，`53b7276`）**：后端 SQLite 全量 `uv run python -m pytest apps/api/tests packages -q` → **996 passed / 11 skipped / 63 warnings / 677.08s**（Round 21 为 994 passed，+2 = planner 的一次纠正与「非列表返回不是 500」两个用例）；PostgreSQL 16 通道（`AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test`）`test_workflow_planner test_runtime_migrations test_discovery_evidence test_task_lease` → **34 passed**；`ruff check .` / `ruff format --check .`（488 files）干净；`scripts/i18n_check.py` → 25 namespaces / 3390 keys；`scripts/export_openapi.py --check` → current；前端 `pnpm --filter @ai-qa/web test` → **225 pass / 0 fail**，`tsc --noEmit` 与 `eslint src --max-warnings=0` 干净。真实 Chromium + 真实 provider：`.ai-runs/overnight-delivery/rounds/r22_acceptance.py` → **15/15 PASS，`failed: []`，`console_errors: []`**（证据 `rounds/r22-acceptance.json`，说明 `rounds/r22.md`）。两条链路：失败→批准→精确验证（`run_1949eb638ae2`/`fail_00fd043c649c`/`7a5e3a6f…`/`run_01b4e1aebd12`）、自然语言→草稿→发布→停在执行前（planner `valid:true` 14 节点，`72b52b01-…`，`/execute` 404）。

- **Round 21（UX/性能/可观测性，`6a865c3`）**：前端 `pnpm --filter @ai-qa/web test` → **224 pass / 0 fail**（Round 20 为 223，+1 = 堆叠布局 extent 用例），`tsc`/`eslint` 干净；后端全量 994 passed / 11 skipped / 724.80s；`ruff`（488 files）、`i18n`（3390 keys）、`openapi --check` 均干净。真实浏览器 `.ai-runs/overnight-delivery/rounds/r21_acceptance.py` → **12/12 PASS，`failed: []`，`console_errors: []`**；性能实测 `rounds/r21-perf-{before,after}.json`（流水线缩放 0.47→0.82、最小字号 6.2→9px；执行树手机单列 10.5px；1000 节点挂载 1107ms / DOM 18410）；截图 `rounds/screenshots/r21-*`。

- **Round 20（CI/PG/部署，`8b1c07d` + 本文档）**：后端 SQLite 全量 `uv run pytest -q` → **989 passed / 11 skipped / 63 warnings / 1049.87s**（Round 19 为 960+）；PostgreSQL 16 通道（`AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test`，整套后端）→ **838 passed / 8 skipped / 71 warnings / 1086.64s**，日志 `.ai-runs/overnight-delivery/rounds/r20-postgres.txt`；`ruff check .` / `ruff format --check .`（488 files）干净；`python scripts/export_openapi.py --check` → current；前端 `pnpm --filter @ai-qa/web test` → **223 pass / 0 fail**，`typecheck`/`lint` 干净，`build` 52.5s；`scripts/i18n_check.py` → 25 namespaces / 2 languages / 3390 keys；部署演练 `.ai-runs/overnight-delivery/rounds/r20_deploy_drill.py` → **12/12**（证据 `rounds/r20-deploy.json`）。

- **Round 16.5（Agent Execution Tree，`ec5bae8` + 本文档）**：后端全量 `uv run pytest -q` → **960 passed / 11 skipped / 62 warnings / 1262.12s**（Round 16 为 952 passed，本轮 +8 = `test_execution_trace.py`）；`ruff check apps/api packages` → All checks passed，`ruff format --check` → 293 files already formatted；`scripts/export_openapi.py --check` → current（两个只读端点已导出）；`scripts/i18n_check.py` → 25 namespaces / 2 languages / **3303 keys**（+63）；web `npx tsc --noEmit` 与 `npx eslint src --max-warnings=0` 无输出，`pnpm --filter @ai-qa/web test` → **213 pass / 0 fail**（Round 16 为 202，+11 = `execution-tree-model.test.mjs`）；迁移 `0018_ai_invocation_step` 有升降级往返用例。真实浏览器 `.ai-runs/e2e-round16.5/execution_tree_acceptance.py`（真实 `mimo-v2.6-flash` + `jev-1.13.0`，受控页 `discovery-fixture-d.html`）→ **13/13 PASS，`failed: []`，`console_errors: []`**；证据 `.ai-runs/e2e-round16.5/acceptance.json`，截图 `screenshots/{before-pipeline-canvas,after-execution-tree,after-node-detail,after-execution-tree-reloaded,after-execution-tree-mobile}.png`。

- **Round 16（证据智能层，`c4075a1` + 本文档）**：后端全量 `uv run pytest -q` → **952 passed / 11 skipped / 61 warnings / 1417.83s**（Round 15 为 932 passed，本轮 +20 = `test_discovery_intelligence.py` 17 例 + Jev 归一化/分级用例）；`ruff check apps/api packages scripts` → All checks passed，`ruff format --check` → **464 files already formatted**；`scripts/export_openapi.py --check` → current（新增受控页路由已导出）；`scripts/i18n_check.py` → 25 namespaces / 2 languages / **3240 keys**；web `npx tsc --noEmit` 与 `npx eslint src --max-warnings=0` 无输出，`pnpm --filter @ai-qa/web test` → **202 pass / 0 fail**；新增/更新后端套件 `test_discovery_intelligence.py`(17) + `test_decision_layer.py`(32) + `test_workflow_canvas.py`(7)。真实浏览器 `.ai-runs/e2e-round16/intelligence_acceptance.py`（最终代码，真实 `mimo-v2.6-flash` + 真实 `jev-1.13.0`）→ **28/28 PASS，`failed: []`，`console_errors: []`**；证据 `.ai-runs/e2e-round16/acceptance.json`，截图 `screenshots/after-canvas-intelligence.png`（AI 建议 + Jev 分级 + 审核按钮）、`after-canvas-approved.png`（批准后进入既有用例链）、`after-canvas-mobile.png`（390px 无横向溢出）。真实 Jev 打分 `score 0.505 / confidence 0.90`（归一化前一律 `invalid_request`）。

- **Round 15（证据层，`e9f2951` + 本文档）**：前端 `npx tsc --noEmit` 无输出、`npx eslint src --max-warnings=0` 无输出、`pnpm --filter @ai-qa/web test` → **201 pass / 0 fail**（Round 14 为 197，+4 = 折叠/证据行用例）；`scripts/i18n_check.py` → 25 namespaces / 2 languages / **3206 keys**（+19）；`scripts/export_openapi.py --check` → current（本轮新增 6 个 `/api/discovery/runs/{run_id}/…` 端点已导出）；`ruff check apps/api packages` → All checks passed，`ruff format --check` 干净；新增后端套件 `test_discovery_evidence_capture.py`(16) + `test_discovery_evidence.py`(9) + `test_workflow_canvas.py`(6) + `test_runtime_migrations.py`(6) + `test_sensitive_redaction.py`(5) → **42 passed**；后端全量 `uv run pytest -q` → **932 passed / 11 skipped / 60 warnings / 517.63s**（Round 14 为 902 passed，本轮 +30 = 证据采集/接口/画布/迁移用例）。真实浏览器 `.ai-runs/e2e-round15/acceptance.py`（最终代码 `589e6ab`，runs `qd_7f6c62767dcf42b3` / `qd_df4cca7749ff4dc9`）→ **21/21 PASS，`failed: []`，`console_errors: []`**；真实数据追踪 `.ai-runs/e2e-round15/scenarios-trace.json` → `trace_complete: true`。

- **Round 14（只读画布，`bf9b5c2` + 本文档）**：后端全量 `uv run pytest -q` → **902 passed / 11 skipped / 60 warnings / 481.13s**（比 Round 12 多 4 例；唯一 FAIL 是 `test_openapi_contract.py` 因新端点导致契约快照过期，已用 `scripts/export_openapi.py` 重新导出，单跑该用例 **1 passed**）；`ruff check` → All checks passed，`ruff format --check` → 378 files already formatted，`scripts/export_openapi.py --check` → current；`scripts/i18n_check.py` → 25 namespaces / 2 languages / **3187 keys**（+72）；web `npx tsc --noEmit` 无输出、`npx eslint src --max-warnings=0` 无输出、`pnpm --filter @ai-qa/web test` → **197 pass / 0 fail**（Round 13 为 191，+6 = canvas 模型与投影用例）；真实浏览器 `.ai-runs/e2e-round14/canvas_acceptance.py` → **16/16 PASS，`failed: []`，`console_errors: []`**。

- **Round 13（前端体验改动，`32f22a3`）**：后端 0 改动（不重跑全量，基线沿用 Round 12 的 898 passed）；web `npx tsc --noEmit` 无输出、`npx eslint src --max-warnings=0` 无输出、`pnpm --filter @ai-qa/web test` → **191 pass / 0 fail**（Round 12 为 188，本轮 +3 = `failure-workspace-model.test.mjs` 新增的修复链用例）；`scripts/i18n_check.py` → 25 namespaces / 2 languages / **3115 keys**（+35）；真实浏览器 Before/After：`.ai-runs/e2e-round13/audit.py` Before **1/5（4 项 FAIL）** → After **6/6**，`console_errors: []`。

- **Round 12 最终回归（`2eb6901`，权威数字；单实例 SQLite + 真实 provider）**：后端全量 `uv run pytest -q` → **898 passed / 11 skipped / 60 warnings / 444.30s**（比 Round 11 多 6 例 = 本轮新增用例）；`uv run ruff check` → All checks passed；`ruff format --check` → 446 files already formatted；`scripts/export_openapi.py --check` → current；`scripts/i18n_check.py` → 25 namespaces / 3080 keys；web `tsc --noEmit` + `eslint .` 干净；`pnpm --filter @ai-qa/web test` → **188 pass / 0 fail**。真实浏览器（Playwright 1.62.0 + Chromium，真实 AI/Jev）：旅程 A（Discovery→Recorder→Studio→Run）**16/16**、旅程 B（失败→调试→分析取消/刷新→任务重试→人工批准→应用→精确验证）**17/17**、旅程 C（坏密钥/恢复密钥 + 轮换健康标准）**10/10**，三段 `console_errors` 均为 `[]`。DB 终态：`failure_analyses` RUNNING = 0、`ai_invocations` RUNNING = 0。报告：`.ai-runs/e2e-round12/audit-report.md`。

- **Round 11 最终回归（`89eb5ed`；日志 `.ai-runs/final-acceptance/regression-final-r2.log`）**：后端全量 `uv run pytest -q`（SQLite）→ **892 passed / 11 skipped / 60 warnings / 810.49s（13:30）**；`ruff check .` → All checks passed，`ruff format --check` → 445 files already formatted；`scripts/export_openapi.py --check` → OpenAPI contract is current；`scripts/i18n_check.py` → 25 namespace / 2 language / 3080 keys；web `tsc --noEmit` + `eslint .` 无输出、`pnpm --filter @ai-qa/web test` → **188 pass / 0 fail**。真实浏览器连续旅程（最终代码）**8/8 断言、0 控制台错误**（`.ai-runs/final-acceptance/journey.json`）；9 页 × 桌面/移动视口横向溢出 0（`viewport-sweep.json`）。**Verdict：PASS（日常可用）**；BLOCKED 项（CI/CD、部署回滚、PostgreSQL 通道）与诚实标注（Jev 评分 50/50 走 `FALLBACK`）见 `docs/RC_ACCEPTANCE.md` §8.3。

Round7（分支 `agent/discovery-live-engine`，本轮收尾提交；环境 WSL2，SQLite；本轮同时间有一个截图委派在跑本地 API/Vite/Chromium，已按串行原则排定）：

- 发现域套件：`uv run --no-sync pytest apps/api/tests/test_quality_discovery.py apps/api/tests/test_quality_discovery_live.py apps/api/tests/test_quality_discovery_live_e2e.py apps/api/tests/test_discovery_coverage_e2e.py -q` → **78 passed / 179.79s**。
- 真实浏览器验收单跑：`test_quality_discovery_live_e2e.py` → **1 passed / 2.37s**（真实 Chromium；坐标断言 ≤8px；流里的帧与 adapter 抓帧字节一致；页内高亮确实绘制）。
- **后端全量（SQLite）：`uv run --no-sync pytest apps/api/tests packages -q` → 867 passed / 11 skipped / 60 warnings / 654.84s**。
- 前端：`pnpm --filter @ai-qa/web test` → **172 passed**；`typecheck`、`lint` 无错；`build` 30.05s。
- 门禁：`ruff check .` All checks passed；`ruff format --check .` 441 files already formatted；`scripts/i18n_check.py` 25 namespaces / 2 languages / 3062 keys；`scripts/export_openapi.py --check` current（本轮修正了自 `534c252` 起过期的 OpenAPI 契约）。
- 未执行（诚实记录）：PostgreSQL lane（未启动 PostgreSQL）、真实 AI/Jev 在线验收（外部 provider 不可达，BLOCKED）。

Round6（提交 `f2dd186`，代码冻结后执行；冻结后仅对 `apps/api/tests/test_discovery_coverage_e2e.py` 做过 `ruff format` 空白格式化，其余无源码改动）：

- 后端全量（SQLite）：`uv run pytest apps/api/tests packages -q` → **850 passed / 11 skipped / 60 warnings / 573.82s / exit 0**（`/tmp/r6-sqlite-final.log`）。
- PostgreSQL lane：`AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test uv run pytest apps/api -q` → **699 passed / 7 skipped / 76 warnings / 424.33s / exit 0**（`/tmp/r6-pg-final.log`）。
- 前端：`pnpm --filter @ai-qa/web test` → **161 passed**；`tsc --noEmit` 通过；`build` → 31.34s；`python scripts/task.py lint` → All linters passed（`/tmp/r6-lint2.log`）；`uv run python scripts/export_openapi.py --check` → OpenAPI contract is current。
- 真实浏览器 E2E + 错误面：`ROUND4_SCREENSHOT_PHASE=after uv run pytest apps/api/tests/test_discovery_coverage_e2e.py -q -s` → **1 passed / 105.49s**，`round6_error_surfaces = ["runs","failures","security","release-create"]`（`/tmp/r6-harness-final.log`；证据 `round-4/evidence/after/` 79 文件）。
- Studio Debug 真实验收：`AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1 uv run pytest apps/api/tests/test_studio_debug_ui_live.py -q -s` → **2 passed / 32.65s**（`/tmp/r6-live-studio-debug.log`）。
- 真实 AI/Jev（provider 降级窗口）：`test_live_enterprise_journey.py` → 1 passed / 1 failed（183.37s，后者死于质量缺口动作 `HTTP 502 AIProviderError`）；`test_live_locator_repair_acceptance.py -k requires_approval_and_exact_rerun` → 失败，事件仅到 `repair.blocked`（`_runtime_readiness` 判定真实 AI 不可用）；`-k through_browser_ui` → 未 settle；`test_browser_agent_live_e2e.py` → Jev 置信度 0.06 触发 `TaskBlocked`。探针：AI `TIMEOUT`（5034ms）、Jev `connected`。按用户约束记 **BLOCKED**，不做重复重试。

Round5（提交 `71f6f14` + `a8c21a1` 的最终代码，2026-10-18；含 reviewer 修复与全部 Round 5 改动）：

- **最终验收对着提交后的 HEAD 重跑（代码冻结）**：
  - 全仓后端（SQLite）：`uv run pytest apps/api/tests packages -q` → **848 passed / 11 skipped / 60 warnings / 578.93s / exit 0**（`/tmp/sqlite-head.log`）。
  - PostgreSQL lane：`AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test uv run pytest apps/api -q` → **697 passed / 7 skipped / 76 warnings / 388.54s / exit 0**（`/tmp/pg-head.log`）。这是本仓第一次在真实 PostgreSQL 上跑通完整 `apps/api` 套件。
- 早前一轮（格式化前，仅差 `ruff format` 的空白改动）：SQLite 848/11/60 573.06s（`/tmp/sqlite-final2.log`）、PG 697/7/76 354.03s（`/tmp/pg-final2.log`）；随后 `ruff format` 改动 4 个文件（含 `apps/api/app/persistence/migrations.py`），重跑涉及文件：SQLite **60 passed / 1 skipped / 68.00s**，PG **17 passed / 1 skipped / 31.69s**。
- 全仓 lint：`python scripts/task.py lint` → Ruff、429 Python 文件格式、i18n（25 namespaces / 3026 keys）、OpenAPI 契约、ESLint 全通过（`All linters passed!`）。
- 前端：`pnpm --filter @ai-qa/web typecheck` 通过；`pnpm --filter @ai-qa/web test` → **161 passed / 0 fail / 1.10s**；`pnpm --filter @ai-qa/web build` → 成功（34.88s，Monaco chunk 4,031.76 kB 警告为历史项）。
- 真实 worker 进程集成测试：`apps/api/tests/test_worker_process_integration.py` 4 个用例，真实 `python -m worker.main` 子进程 + 真实 uvicorn API + 真实 pytest 子进程（claim → run pytest → 结果回传 → 取消 → 崩溃恢复），SQLite 17.76s / PG 同一套件内通过。
- 安全负向测试：`apps/api/tests/test_security_hardening.py`（跨 run 伪造 artifact、路径穿越、symlink、未授权 worker、审计 actor、恢复参数负值 422 等）随全量套件通过。
- 新增 PostgreSQL 防回归：`apps/api/tests/test_postgres_migrations.py` 每次建临时库跑 `alembic upgrade head`，断言 `alembic_version == head` 且 `compare_metadata` 无漂移（允许 `locator_repairs.state` 的 `Enum(native_enum=False)` 已知误报）。
- 说明：`apps/api/tests/test_runs_and_failures.py::test_trigger_run_and_failure_flow` 原先依赖真实外部 provider（opencode.ai），在本轮两次全量运行中分别因「30 秒超时（已重试 3 次）」和「无法解析结构化输出」随机失败；已改为对该用例的助手侧车注入确定性 `FakeAIProvider`（真实 provider 的超时/降级路径仍由 `test_qa_assistant_stream.py` 覆盖）。修复后 SQLite/PG 全量均为绿。

Round4（2026-10-17）：

- 全仓后端：`uv run pytest apps/api/tests packages -q` → **837 passed / 10 skipped / 57 warnings / 566.49s**。
- 全仓 lint：`python scripts/task.py lint` → Ruff、Python format、i18n、OpenAPI、ESLint 全通过。
- 前端：`pnpm --filter @ai-qa/web typecheck` 通过；`node --test tests/failure-workspace-model.test.mjs` → **10 passed**。
- 真实浏览器巡检：`ROUND4_SCREENSHOT_PHASE=after uv run pytest apps/api/tests/test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e -q -s` → **1 passed / 91.14s**，产物 `round-4/evidence/after/`（75 文件、`page-matrix.json` 61 条）。验收基于最后一次修改后的代码（后续只改 handoff/提交，无源码变更）。

Round3 结果和实际浏览器证据保存于 `.ai-runs/night-continuation/round-3/implementation-log.md` 与 `.ai-runs/night-continuation/round-3/evidence/`；历史 Round2 见 `.ai-runs/enterprise-continuation/round-2/test-results.md`。

- Round3 最终全仓：`python scripts/task.py test` → **834 passed / 10 skipped / 55 warnings / 474.19s**。Web 160 passed；typecheck/ESLint/build 都通过。PostgreSQL lane 跳过（`AI_QA_TEST_DATABASE_URL` 未配置，当前无 DB/Docker）。
- Round3 全仓 lint：`python scripts/task.py lint` → Ruff、428 个 Python 文件格式、25 个 i18n namespaces/3025 keys、OpenAPI 和 ESLint 全通过。
- 真实集成验收：`apps/api/tests/test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e`，最后独立重跑 **1 passed / 13.32s**。Chromium真实访问 loopback test shop；发现证据 `3 states/2 actions/6 evidence items`；UI创建需求草稿、查看结构化风险与 scenario、生成并选中 TestCase；UI modal手动创建 ACTIVE binding，UI `结果 → 开始运行` 发起真实 Playwright Run PASSED，点击 refresh + reload 后 Coverage `VERIFIED`；foreign project页面无 Discovery 数据，跨项目 workspace binding API 返回 422。E2E真实 Playwright是测试过程生成且执行的代码。
- 本轮 AI/Jev 使用 deterministic test fixtures；仅浏览器访问/BrowserRuntime/真实 Playwright执行是真实，不可将其宣称为真实生产 AI/Jev验收。
- 独立 reviewer：覆盖Round3 diff；记录的 E2E 选中case断言已补为 URL `caseId` +渲染case steps，并复测成功。rollback 文件race由 `write_file_if_unchanged(expected_sha256=...)` fail-closed，持久 `ROLLBACK_PENDING`，不覆盖其他用户修改。

- 最新 Studio opt-in acceptance attempt 19：**2 passed / 32.10s**，真实 Chromium + debugpy；3 sessions CLOSED、synthetic failure Run 为 FAILED 且保留 trace，API/console errors 为空。1440/768/390px `documentWidth <= viewport`。全套截图、metrics、log：`.ai-runs/night-continuation/round-1/attempt-19/`。
- Studio attempts 1–18 为排障历史；attempt 19 为当前事实。早期 locale selector、Monaco 5px flex collapse、breakpoint verification locator、Step Out 停点等问题已通过修正 harness/布局后解决；最终结果不得引用这些旧失败代替 attempt 19。
- D5 real API C chain 成功：真实 AI/Jev/本地浏览器、AI 需求/用例、人工 ACTIVE Playwright binding、Run PASSED、刷新后 coverage `VERIFIED`；一次真实 Web UI 点击也显示成功。D5 strict live retries 曾被 provider timeout 阻断；本轮 Studio acceptance 不调用真实 AI/Jev，测试 fixture 明确禁用 health probes 并在 teardown 恢复，不能把这项结果说成 AI/Jev 验收。
- D5 OpenAPI 403/404/409、requester/Admin endpoint boundary、run-switch UI stale-feedback 和 timestamp latest-execution均修复；`TestRunRepository.list_runs` newest-first。一次独立 review 发现 strict harness路径/status断言问题，已改；最终 reviewer 复查当前 diff：无剩余 blocker。
- Studio Round1 全仓历史回归（attempt 19 后）：**830 passed / 10 skipped / 55 warnings / 453.15s**；Round3 最新验收结果见上述 834/10/55；PostgreSQL lane skipped（`AI_QA_TEST_DATABASE_URL` 未设置）。Vite 6.4.3 有大型 chunk 警告（Monaco JS 4,031.76KB）。
- Failure workflow CAS/recovery + Jev 503 suite：**47 passed / 1 warning**；duplicate Apply 20/20 重复、exactly one workspace write。Monaco chunk 4.03 MB；PostgreSQL blocked；remote Worker/Jenkins not run。
- 系统级项目隔离仍未解决：Project 无 owner/team ACL，RBAC 角色为全局；D5 仅 requester/Admin 可刷新其 run，不代表其他 API 已隔离。

```bash
# 全仓后端回归（本轮最终代码）
python scripts/task.py test                    # → .ai-runs/night-continuation/round-1/logs/full-regression-final.log
# 仓库 lint（ruff + format + i18n 一致性 + OpenAPI 契约 + eslint）
python scripts/task.py lint                     # → All linters passed!
# 前端
pnpm --filter @ai-qa/web typecheck && pnpm --filter @ai-qa/web lint && pnpm --filter @ai-qa/web test && pnpm --filter @ai-qa/web build

# Round 5 专用（按需）
# 启动隔离的本地 PostgreSQL 18.6（临时目录，不碰仓库 lockfile/系统）
test -d /tmp/sock-aiqa || mkdir -m 700 /tmp/sock-aiqa
/tmp/pgvenv/bin/python -c "import embedded_postgres as ep; ep.pg_ctl(['-o','-p 55432 -k /tmp/sock-aiqa -c listen_addresses=127.0.0.1','-l','/tmp/pg55432.log','-w','start'], pgdata='/tmp/pgdata-aiqa')"
AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test \
  uv run pytest apps/api -q                    # PostgreSQL lane（串行！WSL 7.9GB 内存；库名必须含 test，测试会拒绝清空其他库的 schema）
uv run pytest apps/api/tests/test_worker_process_integration.py -q   # 真实 worker 子进程
uv run pytest apps/api/tests/test_security_hardening.py apps/api/tests/test_job_reliability.py -q
/tmp/pgvenv/bin/python -c "import embedded_postgres as ep; ep.pg_ctl(['-D','/tmp/pgdata-aiqa','stop'])"
```

## 10. 下一步具体命令

Round 12 已完成现状审计 + 3 笔最小修复 + 真实浏览器全路径验收（见 §3.9 与 `.ai-runs/e2e-round12/audit-report.md`）。复跑本轮证据只需要：

```bash
cd /home/hans/self-github/ai-qa-platform
git log --oneline -4 && git status --short      # 期望 HEAD 2eb6901；仅 .ai-runs/** 未跟踪
python scripts/task.py dev                      # API :8000 + Web :5173（日志会打印实际端口）
# 三段真实浏览器旅程（顺序有依赖：B 产出 C 需要的 failure/analysis，A 独立）
uv run python .ai-runs/e2e-round12/journey_a.py
uv run python .ai-runs/e2e-round12/journey_b.py
uv run python .ai-runs/e2e-round12/journey_c_provider_failure.py   # 会停/起 :8010 栈，最后恢复 :8000 开发栈
# 回归
uv run pytest -q && pnpm --filter @ai-qa/web test
```

与多副本/部署有关的下一步（未做，需设计）：先给 `agent_tasks` 加 lease/heartbeat 并把 `recover_interrupted*` 改成只收敛自己租约失效的任务，再改探索的 pause/stop 信号跨进程投递；在此之前不要把 `audit-remaining-blockers` 部署成多副本。

Round6 已完成全系统独立验收（见 §3.3、§9 与 `.ai-runs/night-continuation/final-report.md`）；下一组首要任务仍是 P0 project-resource ACL。开始前需要产品/安全 owner-team 与 legacy ownerless project 认领规则；没有规则前不得静默分配 owner。provider 恢复后请单次复验浏览器内失败修复链路（60s/1 retry，失败即记 BLOCKED）。旧 Studio/Strict D5 命令如下仅供历史重跑参考。

```bash
# 核对现场
cd /home/hans/self-github/ai-qa-platform
git status --short && git log -1 --oneline
# 当前 Studio acceptance（使用新的 attempt 目录，避免覆盖既有证据）
# 若后续代码修改需要重验，先创建全新 attempt-20 目录；当前通过证据为 attempt-19。
mkdir -p .ai-runs/night-continuation/round-1/attempt-20/logs
AI_QA_STUDIO_EVIDENCE_DIR=.ai-runs/night-continuation/round-1/attempt-20/screenshots \\
AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1 uv run --no-sync pytest apps/api/tests/test_studio_debug_ui_live.py -q -s 2>&1 | tee .ai-runs/night-continuation/round-1/attempt-20/logs/studio-ui-acceptance.log
# 修复确认的 UI bug 后运行 Studio 相关回归，再运行全仓回归
uv run --no-sync pytest apps/api/tests/test_studio_debug_ui_live.py apps/api/tests/test_debug_session_service.py -q --no-header
python scripts/task.py lint
git diff --check
# latest failure repair security regression
uv run --no-sync pytest apps/api/tests/test_failure_workflow.py -q --no-header -p no:cacheprovider
# D8 disabled-provider targeted regression
uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider
# 环境（仅依赖确实缺失且 lockfile 无变更时恢复；不要为验证无条件重装）
# uv sync --locked && pnpm install --frozen-lockfile

# 启动服务
(cd apps/api && uv run --no-sync uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
pnpm --filter @ai-qa/web dev                       # :5173

# Strict D5 live UI (仅 Provider 恢复后执行一次；60s/1 retry；若仍超时则 BLOCKED，不循环重试)
AI_QA_RUN_LIVE_ENTERPRISE_ACCEPTANCE=1 QA_AI_TIMEOUT_SECONDS=60 QA_AI_MAX_RETRIES=1 \
uv run --no-sync pytest apps/api/tests/test_live_enterprise_journey.py::test_real_local_discovery_preserves_target_and_project_scope -v -s

# 真实浏览器验收
AI_QA_LIVE_BROWSER_E2E=1 uv run --no-sync pytest apps/api/tests/test_browser_agent_live_e2e.py -v -s

# 回归
uv run --no-sync pytest apps/api/tests -q
pnpm -r typecheck && pnpm -r lint
```

## 11. 下一个 Agent 应当继续的工作

**Round 12 后续（分支 `audit-remaining-blockers`，先读 §3.9 与 `.ai-runs/e2e-round12/audit-report.md`）：**

1. 不要重做已验证的项：五项能力已经逐项取证，旅程 A/B/C 已在 `2eb6901` 上全绿（16/16、17/17、10/10）；非必要不重跑，避免重复消耗真实 provider 预算。
2. 唯一真正的阻断是**多实例一致性**：`task_scheduler_service.recover_interrupted()` 与 `quality_discovery_service.recover_interrupted_runs()` 是全量收敛，探索的 pause/stop 信号是进程内对象。正确做法是先引入 lease/heartbeat（新迁移），再让收敛只针对失效租约，最后把信号落成 DB 行；这三步是一体的，不能只改其中一步。
3. 部署/回滚/CI/PostgreSQL 仍需在有容器与多副本的环境里补做（脚本已就绪：`scripts/deploy.sh`、`.github/workflows/ci.yml`），失败即记 BLOCKED，不循环重试。
4. P2 观察项（内联分析与 FIX_FAILURE 任务两条修复面的状态一致性、等待审批无过期策略、Jev 评分 FALLBACK）需产品决定后再动，不要自行重构。
5. 重跑旅程前先确认 `scripts/task.py dev` 的日志没有被端口回退（现在只有真 LISTEN 才会回退）。

**Round 7 先行事项（分支 `agent/discovery-live-engine`，先读 §3.4 与 `docs/QUALITY_DISCOVERY.md`）：**

1. 先核对 `git log`（本轮收尾提交）、`git status --short`、§2/§3.4；不要丢掉未提交改动。
2. 未完成的 Round 7 队列：R6 真实 AI/Jev 链路（provider 恢复后再做，失败即记 BLOCKED，不循环重试）；私有 IP/CIDR + 端口限制的探索安全策略；把探索循环迁到 `TaskRuntimeService`（同时消除 ROADMAP §0 的偏差）；发现→需求→用例→自动化的 schema 级 provenance；长历史分页（事件上限 500）。
3. Before/After 截图证据在 `.ai-runs/discovery-live/screenshots/`（本地未跟踪）。若仅有 After 而 Before 缺失，报告中必须写明缺失原因，不得拿渲染占位图充当 Before。

旧 Round 6 待办（仍然有效）：

1. 先核对最新 HEAD（Round6 代码提交 `f2dd186`）、`git status --short`、本文件 §3.3、`.ai-runs/night-continuation/final-report.md` 与 `round-6/` 证据；不要丢弃未提交/新用户改动。
2. Round6 已在冻结代码上完成 SQLite 850 / PostgreSQL 699 / 前端 161 / 真实浏览器 E2E 1 passed / Studio 2 passed；没有新的源码变更时不要重跑整套，避免重复消耗。
3. 下一组任务是项目资源 ACL：先获取 owner/team 和 legacy ownerless project claim 策略，再复用 `apps/api/app/api/authz.py` 中央策略表及审计表实施，覆盖 191 API route families 的 resource resolver/list/query/body/WS隔离（运行/失败/制品/工作区/恢复接口，且 `ArtifactORM` 需补 `project_id`）。不能把按 project ID 分组的 Quality Map 或 Workspace binding 验证说成安全 ACL。
4. provider 恢复后单次复验浏览器内失败修复链路（`AI_QA_RUN_LIVE_JEV_BROWSER_ACCEPTANCE=1 … -k through_browser_ui`），并排查日志中的 SQLite `database is locked`；失败即记 BLOCKED。
5. Round2 AI/Jev repair matrix 尚缺远程 outage、持久化前 interruption、verification worker restart、PostgreSQL并发；仅在具备环境时继续，保留明确 blocked 状态。

旧 `/tmp` Studio scripts 不存在；真实 debugpy opt-in test 位于 `apps/api/tests/test_studio_debug_ui_live.py`，通过 `AI_QA_RUN_LIVE_STUDIO_ACCEPTANCE=1` 启动。

## 3.19 Round 21（UX / 性能 / 可观测性）

**测量先于修改**：`.ai-runs/overnight-delivery/rounds/r21_perf.py` 在四个宽度（1560/1280/1024/390）量三个画布视图（流水线 / 执行树 / 编辑工作流）+ 总览/运行/失败三页的 FCP、DOM 节点数、节点数、缩放、**最小可读字号**（font-size × zoom）、横向溢出、拖动延迟。Before：流水线在 1560 用 0.47 缩放把整条链塞进视口 → 正文 ≈6px，1280/1024 只有 0.62；执行树永远 zoom 1（最后一列被裁）；编辑工作流 0.95 / 手机 0.724（8px）。

**修的五处**（都在前端渲染层，不改数据）：① `WorkflowCanvasPanel` 的适配阈值从「塞下整条链」改为**可读下限**（桌面 0.82 / 窄屏 0.72，断点按画布宿主的 900px 判定），装不下就允许平移，MiniMap 缩到 148×92 作为总览；② 三个画布的 10px 以及 workflow-editor/执行树的 9–10px 字号统一抬到 11px（标题 14px）；③ 执行树的适配 effect 原在宿主未挂载时静默返回（`.let-flow` 只在有节点时渲染，`deps: []` 永远观察不到），改为有界重试 + `fitView({padding:0.1,maxZoom:1})`；④ 宿主 < 720px 时执行树改为**单列纵向列表**（每层缩进 12px、卡片固定 300px），手机可读 10.5px；⑤ 证据分页 `offset`（`list_by_run(limit=500, offset=0)` → `list_evidence(offset)` → `GET …/evidence?offset=`）+ 一个「翻页不重不漏」用例，并把证据标签从 `EvidenceType.ANALYSIS` 这类枚举原值改成 `ANALYSIS · 来源`。

**实测 After**：流水线 0.82/0.82/0.82/0.72（最小字 9/9/9/7.9px，此前 1280/1024 有 30 个 <9px 的卡片）；执行树 1/0.957/0.876/**1（手机单列、0 卡超出）**；编辑 0.95（10.5px）/ 8px 手机。压力测试（真实组件、按真实 trace 克隆 100/500/1000 节点）：挂载 853/944/1107ms，拖动 27.8/73.5/25.8ms，DOM 537/9314/18410，1000 节点在 0.7 缩放（7.7px）。总览/运行/失败页 FCP 220/180/188ms。**必须承认的边界**：`MAX_NODES=30` 与「项目 trace 汇总 6 个任务」意味着 100/500/1000 节点在真实产品路径上到不了，压力样本是真实 trace 的等比副本；100 节点那一档会与面板 3s 轮询竞争，读数不可靠；证据分页目前没有 UI 消费者。

**验收**：`r21_acceptance.py` **12/12 PASS，`failed: []`，`console_errors: []`**（`.ai-runs/overnight-delivery/rounds/r21-acceptance.json`）：五个视图可达、流水线首列完整在屏、执行树三档宽度无节点越界、手机单列 10.5px、编辑工作流 10.5/8px、刷新后 33 个节点且 id 全一致、点节点能看到引用的 evidence id、失败页主操作为「创建分析与修复任务」且阶段链（诊断/修复/重跑/验证）齐全、失败页外链保留 projectId、无控制台错误、运行页正常渲染。截图 `rounds/screenshots/r21-{before,after}-{pipeline,execution,editor,failure,dashboard,failures,runs}-w{1560,1280,1024,390}.png`。提交 `6a865c3`。

## 3.20 Round 22（最终发布候选审计）

**只读审计，再修被证明的问题**。两项业务链路都真实跑通（真实 Chromium + 真实 `mimo-v2.6-flash` + 真实 `jev-1.13.0`）：`r22_acceptance.py` **15/15 PASS，`failed: []`，`console_errors: []`**（`rounds/r22-acceptance.json`）。

- 链路一（失败 → 修复 → 人工批准 → 精确验证）：把退役定位器写回 `tests/test_known_locator.py` → 运行 `run_1949eb638ae2` FAILED → 失败记录 `fail_00fd043c649c` 落在 `pages/shop.py:35` → FIX_FAILURE 任务 `7a5e3a6f3462446183d245b6ccf56ad9` 停在 `approval=WAITING_FOR_APPROVAL`、`apply=PENDING`（此时源码仍是旧调用）→ 人工批准后写入源码 → 验证运行 `run_01b4e1aebd12` PASSED 且 nodeids 精确等于 `tests/test_known_locator.py::test_known_locator_change`。
- 链路二（自然语言 → 候选工作流 → 草稿 → 发布 → 停在执行前）：planner 一次成功产出 14 节点合法计划（invocation `ffbaf78f-4998-4b17-a880-1c479e622b7d`），存草稿 v1（`72b52b01-ec41-4185-aba6-00168d146036`）→ 发布 → 再编辑只产生 v2 草稿、**已发布 v1 的 checksum 不变** → `POST /workflows/{id}/execute` 返回 404。

**审计修掉的 7 个缺陷**（4 个后端、3 个前端；均由失败运行或独立 reviewer 发现）：① planner `max_tokens=2400` → 真实 `output_limit` 503，改 6000；② `timeout_seconds=60` → 真实 122s 超时，改 120（契约上限）；③ 非 JSON 回复直接 503，改为**一次**有界纠正（第二次仍失败才 503，两分支都有测试）；④ 目录声明为 list 的输入被模型写成单值时整份计划判无效，改为形状纠正；⑤ `{"nodes": 3}` 这类非列表返回 `TypeError` → 500，加 `isinstance` 守卫（`valid:false`）；⑥ reviewer P1：流水线适配 effect 依赖 `pipelineExtent` 对象，每次 3s 轮询都会把平移过的视口拽回起点，改为依赖 `.right/.bottom` 原语；⑦ reviewer P2：`traceExtent` 用列宽 236 量 300px 的堆叠卡片，手机端裁掉约 22px，改用 `initialWidth`。

**判定（五个等级分开给，不合并）**：`CORE_PRODUCT_PASS` = PASS；`WORKFLOW_STUDIO_PASS` = PASS；`DAG_EXECUTION_PASS` = **BLOCKED**（定义能编译成 plan、`task_scheduler_service` 也真的按 `depends_on` 调度，但没有经审批的端到端执行路径，`/execute` 是 404）；`MULTI_INSTANCE_PASS` = **BLOCKED**（Round 18 只证明同机双进程）；`RELEASE_CANDIDATE_PASS` = **BLOCKED**（CI 服务未在远端跑过、部署只做过 Round 20 的单机 compose 演练）。

**诚实边界**：⑥ 的视口回弹**未能在浏览器中复现**（探针期间流水线没有任何运行中节点，轮询未触发，`/tmp/pan-probe.json` 记 `polls: 0`，视口保持不变），该修复只由代码阅读保证；planner 在本环境是模型依赖的（连续四次真实调用 3 次合法、1 次 122s 超时 503），验收脚本允许最多 3 次重试并记录 `attempts`（最终一次为 1）；reviewer 关于 `ExecutionTreePanel` 的 `nodesInitialized` 依赖项与证据 ACL 测试口径两条 P2 保留为债务。

## 3.21 Round 17 复核审计（用户任务 m07420：按原 7 个 Phase 逐项核实已交付的 Studio）

结论：Round 17 的交付范围与本轮 prompt 基本一致，但审计找出 4 个「只有描述、没有证据」的位置和 1 个真实缺陷；缺陷已修，证据已补。本轮不重做 Studio，不新增执行能力。

**逐 Phase 核实（以代码与可重跑证据为准，不看文档措辞）**
- Phase 1 设计 7 项：全部落在 `docs/WORKFLOW_STUDIO.md` §1–§6（定义/执行分表、版本与乐观并发、25 种节点 + 14 个校验码、权限划分、Diff、刻意不做）。代码侧 `workflow_definition.py:436-449` 是真实的 gate：任何 `writes` 节点必须有人工批准祖先节点，`APPROVAL_WITHOUT_WRITE` 反向兜底。
- Phase 2 版本化：`POST /draft`（`base_checksum` 冲突 409）、`/publish`（不可变）、`/versions/{v}/restore`、`/compare` 均存在；本轮补上 restore 的真实验收（此前只有接口没有证据）。
- Phase 3 编辑器：拖拽 / 增删 / 连线 / 参数 / 保存 / 自动布局 / 阶段折叠 / Undo-Redo / 校验 / 版本对比均在 `WorkflowEditorPanel.tsx` + `workflowEditorModel.ts`。**缺陷：布局不可保存**（见下）。
- Phase 4 受限执行：`WorkflowDefinitionService.compile_plan`（`workflow_definition_service.py:226`）可把定义编译成 `TaskStepSpec`，但**没有任何执行路由**（`/execute` 404），因此 B/C 仍为 BLOCKED，与本轮 prompt 允许的降级一致。
- Phase 5 Definition vs Execution Diff：`GET /workflows/{id}/execution-diff?task_id=` 按 step `tool` 匹配，返回 matched / not_executed / undeclared 三组 + `unknown` 列表（不比较 step inputs 与依赖边），真实验收 2 次通过。
- Phase 6 证据与测试数据治理：任务级证据确实在写——R22 修复任务 `7a5e3a6f3462446183d245b6ccf56ad9` 的 11 个步骤共 9 条 `agent_task_evidence`（PytestTraceback / Analysis ×2 / SourceCode ×2 / GitDiff / TestResult ×2）。测试数据一侧新增 `suggestion:<suggestion_id>` 溯源标签（`discovery_intelligence_service.py`），治理流程写入 `docs/WORKFLOW_STUDIO.md` §11：按 id 清理、不按 tag 清理、批准生成的用例照常计入覆盖率。
- Phase 7 真实验收：原 20 项 → **24 项全部 PASS**（`.ai-runs/overnight-delivery/rounds/r17-acceptance.json`，`failed: []`）。新增 4 项：循环连线在发布口被 422 拒绝（不只是"存下来标记 invalid"）、含写节点但无人工批准步骤的工作流不允许发布（`WRITE_WITHOUT_APPROVAL` + 422）、旧版本 restore 只改草稿且已发布 checksum 不变、拖拽后的布局保存并在刷新后保持。

**本轮修复的真实缺陷（P1）**：`WorkflowEditorPanel.tsx:200` 的 `dirty` 只比较 `sameGraph`，而 `canonical()` 刻意排除 `position`，保存按钮又是 `disabled={… || !dirty}` → 拖动节点后「保存草稿」始终禁用，布局**永远无法持久化**。修法：`workflowEditorModel.ts` 新增 `sameLayout()`（按 key 排序比较取整后的坐标），`dirty = !sameGraph(...) || !sameLayout(...)`；图语义不变，版本 diff 仍不受布局影响。新增前端 2 个测试（布局算未保存、亚像素漂移不算变化）+ 1 条真实验收。

**回归**：前端 227 pass（原 225）、`tsc`/`eslint` 干净；后端全量见 §9 本轮条目；`ruff check`/`format --check` 干净。

## 3.22 最终工程收尾（用户任务 m07699：挂死防护、双通道全量回归、记录按 revision 分类）

**为什么做**：此前出现过三次「不可用的回归记录」（`--timeout=600` 参数不被识别 → 直接启动失败、退出码 143（我自己 SIGTERM 掉的）、只打到 57% 的截断输出）。“跑不动/跑一半”和“真失败”必须分开，这是发布判定的一部分。

**1) 用真实耗时定超时，而不是拍一个数**
- 先带 `--durations=25` 跑一次全量（`regression/durations-sqlite.log`，HEAD `460cf3e`）：最慢 `apps/api/tests/test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e` **166.82s**，第二名 `test_agent_tasks.py::test_browser_agent_completes_second_ecommerce_journey_on_demo_shop` **13.40s**，其余 call 均 < 11s（setup 最大 10.72s）。
- 依赖：`pytest-timeout>=2.4.0` 加入 dev 组（`uv add --dev pytest-timeout`，`uv.lock` 同步更新）。
- 配置：`pyproject.toml` 的 `[tool.pytest.ini_options]` 增加 `timeout = 180` 与 `timeout_method = "thread"`（跨平台，不依赖 SIGALRM）；真实浏览器用例单独 `@pytest.mark.timeout(900)`。
- 双向验证（缺一不可）：① `uv run python -m pytest "apps/api/tests/test_agent_tasks.py::test_create_test_runs_browser_decision_approval_and_generated_pytest" -q --timeout=2` → 插件在 2s 打印 `Timeout` 并终止（该用例真实耗时 10.9s）；② `uv run python -m pytest apps/api/tests/test_discovery_coverage_e2e.py -q --timeout=30` → **1 passed / 168.77s**，即用例自带的 900s 标记覆盖了命令行默认值。

**2) 那次唯一的失败是测试自身的时序竞态，不是产品缺陷**
- 失败用例：`apps/api/tests/test_failure_workflow.py::test_analysis_timeout_ends_the_run_with_an_explicit_retryable_error`，断言 `await asyncio.wait_for(cancelled.wait(), timeout=3)` 超时。
- 产品侧在同一份日志里是正确的：`run.timeout` 事件已发出、`Failure analysis timed out analysis_id=… budget=0.5s` 已记录，`status=TIMEOUT` / `result.block_reason=ANALYSIS_TIMEOUT` / `allowed_actions` 含 `START_ANALYSIS` 三条断言全部通过。
- 根因：用例把预算压到 0.5s；高负载全量运行时，0.5s 会在「provider 调用被进入之前」被 setup 的建库/建项目/编排放耗尽，于是**没有东西可取消**，`HangingProvider.complete()` 从未执行，`cancelled` 永不置位。单跑 2.29s 通过，全量下约 1/5 概率失败。
- 修法（只动测试，产品零改动）：预算 0.5s → **5s**（仍远小于任何真实分析，仍证明“超时会终止”），等待窗口 3s → **10s**，并把这段时序原因写成注释。修后该文件 **50 passed**。

**3) 最终代码上的双通道全量回归**（日志都记录 HEAD、命令、开始/结束时间、退出码、汇总行）
- SQLite：`regression/final-sqlite.log` → **996 passed / 11 skipped / 63 warnings / 890.37s**，`EXIT: 0`。
- PostgreSQL 16（容器 `aiqa-r20-pg`，`postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test`）：`regression/final-postgres.log` → **999 passed / 8 skipped / 61 warnings / 2066.93s**，`EXIT: 0`。差异来源是 3 条 `postgres` 标记用例在 PG 上真跑、SQLite 下跳过（996+3=999、11−3=8）。本轮把 PG 通道从「`apps/api`」扩到与 SQLite 相同的「`apps/api/tests packages`」，所以数值高于 Round 20 的 838。

**4) 回归记录按真实 revision 分类**（不把修复前/中断的结果当最终结果）

| 记录 | 代码状态 | 结果 | 处置 |
| --- | --- | --- | --- |
| `regression/final-sqlite.log` | 最终 HEAD | 996 / 11 / 890.37s / exit 0 | **最终** |
| `regression/final-postgres.log` | 最终 HEAD | 999 / 8 / 2066.93s / exit 0 | **最终** |
| `regression/durations-sqlite.log` | `460cf3e` | 1 failed / 995 passed / 1402.88s | 仅用于定阈值；失败已判定为测试竞态并修复 |
| `r17-readaudit-backend` | `0f11fa3` | 996 / 11 / 706.27s | 该 revision 有效，被最终跑取代 |
| `r22-backend-verbose` | `53b7276` | 996 / 11 / 677.08s | 该 revision 有效 |
| `r22-backend-full-v2` | R22 修复前 | 994 / 11 / 724.80s | 被 996 取代 |
| R21 全量 | `6a865c3` | 994 / 11 / 724.80s | 该 revision 有效 |
| `rounds/r20-postgres.txt` | `8b1c07d` | 838 / 8 / 1086.64s | 该 revision 有效，但范围只有 `apps/api` |
| `backend-full-sqlite-r20` | `8b1c07d` | 989 / 11 / 1049.87s | 该 revision 有效 |
| `r22-backend-full` | — | `unrecognized arguments: --timeout=600` | **无效**（插件缺失，套件没跑起来） |
| `r22-backend-full-final` | — | exit 143 | **无效**（被 SIGTERM 终止） |
| `r22-backend-final-2` | — | 仅 57% 进度 | **无效**（截断，无汇总行） |

**5) 其余门禁（最终代码复跑）**：`ruff check .` / `ruff format --check .` 488 files 干净；`scripts/export_openapi.py --check` → current；`scripts/i18n_check.py` → 25 namespaces / 3390 keys；前端 `pnpm --filter @ai-qa/web test` → **227 pass / 0 fail**，`tsc --noEmit`、`eslint src --max-warnings=0` 干净；真实浏览器 `rounds/r17_acceptance.py` 在最终代码复跑 **24/24 PASS，`failed: []`**（编辑/发布/版本对比/执行 Diff/权限/手机视口/无控制台错误）。

**6) 五级判定（分开给，不合并）**：`CORE_PRODUCT_PASS` = **PASS**；`WORKFLOW_STUDIO_PASS` = **PASS**；`DAG_EXECUTION_PASS` = **BLOCKED**（`compile_plan` 可编译，但没有经审批的执行路由，`/execute` 为 404）；`MULTI_INSTANCE_PASS` = **BLOCKED**（只证明同机双进程；`cancel` 仍未按租约 fencing，`R18-B2`）；`RELEASE_CANDIDATE_PASS` = **BLOCKED**（CI 服务从未在远端跑过、部署只做过单机 compose 演练、多实例未达 PASS）。

**本轮未做（有意）**：不改产品代码、不做无证据的重构、不 push/merge/deploy；`.ai-runs/**`（除 `overnight-delivery/`）与 `runtime/backups/` 保持未跟踪。

## 3.23 RC Freeze（用户任务 m07860：冻结、审计、可恢复标记）

**本轮只做冻结/审计/交接，零产品改动。** 完整基线报告：`.ai-runs/overnight-delivery/RC-BASELINE.md`。

**1) 冻结点**
- 代码提交 `b8958e2`（最终回归所在树），本轮验收证据复跑提交 `a17275d`，`origin/main..HEAD` = **37 笔**（13 feat / 11 docs / 6 fix / 4 test / 1 style / 1 refactor / 1 chore），时间跨度 2026-10-20 → 2026-10-22。
- 本地标记：annotated tag **`rc-2026.10.22`**（不推送）；可恢复副本 `runtime/backups/aiqa-rc-2026.10.22.bundle`（自包含 git bundle，62 MB，含完整历史与该 tag，未跟踪、本地；`git bundle verify` 报告 records a complete history）。
- 跟踪树干净：`git status --porcelain` 只有未跟踪目录 —— `.ai-runs/` 下 17 个历史验收目录（2.2 GB）与 `runtime/backups/`（1.7 MB，2026-10-19 的三份 SQLite 备份）。`.ai-runs/overnight-delivery/**` 在 git 内。

**2) 数字与 revision 的对应**（完整表见 RC-BASELINE.md §1）
- 两份全量日志的 `HEAD:` 行写的是 `460cf3e`，因为提交发生在跑完之后；被测树与 `b8958e2` 逐字节一致，证据是 `git diff --stat b8958e2 -- pyproject.toml uv.lock apps/api/tests/test_discovery_coverage_e2e.py apps/api/tests/test_failure_workflow.py` 为空，且该提交只包含这 4 个文件 + 验收证据/日志。
- 本轮在冻结树复跑：前端 **227 pass / 0 fail**、`tsc --noEmit` 与 `eslint src --max-warnings=0` 干净、真实 Chromium `rounds/r17_acceptance.py` **24/24 PASS，`failed: []`**。

**3) 敏感信息审计**：`git diff origin/main..HEAD` 的新增行全量扫描（provider key / bearer / 私钥 / 口令）只命中两处：`rounds/deploy-drill/drill.env` 的 `POSTGRES_PASSWORD=drillonlypassword`（同一文件写明 `APP_SECRET_KEY=drill-only-secret-key-not-for-production`、`QA_AI_ENABLED=false`、`JEV_ENABLED=false`，该栈由同一演练创建并销毁）与 `docs/agent-handoff.md` 里 Postgres-16 测试通道命令的 `POSTGRES_PASSWORD=postgres`（仓库早已记录的本地一次性容器）。**真实 provider / Jev 凭据不在仓库内**（`config/config.yaml` 只引用 `${QA_AI_*}` / `${JEV_*}`），证据目录内也没有 provider 材料。

**4) 备份与迁移恢复路径（本轮实跑，不是引用）**
- 备份 → 恢复：`bash scripts/backup_db.sh /tmp/rc-drill`（走 SQLite 在线备份 API，WAL 安全）→ `bash scripts/restore_db.sh <备份> /tmp/rc-drill/restored.db` → 逐表比对 **44/44 一致**（`test_runs` 76、`failure_records` 24、`failure_analyses` 28、`agent_tasks` 103、`ai_invocations` 1631、`workflow_definitions` 41、`discovery_evidence` 624、`discovery_suggestions` 13），两侧 `alembic_version` 均为 `0021_artifact_actor_width`。
- 迁移：空库 `alembic upgrade head` → `0021` / **44 表**；`downgrade base` 后仍留 **36 表**，因为 `0001_baseline.py` 的 downgrade 有意保留数据（源码注释即如此），所以「一键清空」不是受支持操作；再 `upgrade head` 回到 44 表与 `0021`（升级路径幂等）。**受支持的回收路径是逐级 `downgrade -1`**：Round 20 在 PostgreSQL 容器上演练过 `0021 → 0020 → head`（`rounds/r20-deploy.json`），`test_runtime_migrations.py` 对每个非基线迁移做往返（6 passed）。
- 运行手册写在 RC-BASELINE.md §4（停 API → 备份 → 必要时降一级 → restore（会先自我快照 `*.pre-restore.<ts>`）→ `alembic current` 对齐 → `/api/health` 三项健康）。

**5) 三个发布阻断（代码证据 + 关闭标准见 RC-BASELINE.md §5）**：B1 DAG 执行路由缺失（`compile_plan` 存在但无路由，`/execute` 404）；B2 cancel 未按租约 fencing（`task_command_service` 直接写终态，`R18-B2`）；B3 远端 CI 与部署/回滚验收从未真跑（CI 只在 push 到 `main` 触发，部署只有单机 compose 演练 12/12）。

**6) 下一阶段最小修复清单**：只做 B2（最小、纯后端）→ B1（需人工决定哪些节点可无人执行，先要产品/安全决策）→ B3（需真实 push 权限与主机）。验收标准：§2 的数字不得回退，每条新结论必须自带 JSON/日志证据且日志内记录 revision，最终树上的运行才能标 PASS。

**判定**：`CORE_PRODUCT_PASS` PASS、`WORKFLOW_STUDIO_PASS` PASS、`DAG_EXECUTION_PASS` BLOCKED、`MULTI_INSTANCE_PASS` BLOCKED、`RELEASE_CANDIDATE_PASS` BLOCKED。未验证条件不标 PASS。**本轮未做**：不 push/merge/deploy，不加功能，不改产品代码。

## 3.25 RC Hotfix 2 — Safe DAG Execution（2026-10-23）

**当前 HEAD / 范围**：代码基线 `a732cb1`；此轮更改未提交。执行范围严格限于不可变已发布 QA Workflow 的两个形状：单个 `failure.collect`，或该节点后接一个输入绑定到 collector 输出的 `failure.classify`。复用现有 `TaskRuntimeService`、`TaskCommandService`、scheduler、lease、cancel、recovery 和 Execution Trace；未添加第二套 Runtime/Agent/Provider，也未打开任意 DAG 或其它 catalogue handler。generic `WORKFLOW_EXECUTION` plan 创建被拒绝。

**可靠性修订**：Workflow 任务时限读取 `agent.max_runtime_seconds`，并遵守 `agent.enabled`；幂等键按 definition + owner 跨版本唯一，fingerprint 包含已解析的发布版本、checksum、输入和编译计划。相同请求在数据库唯一约束竞态中返回获胜任务；相同 key 不同指纹返回冲突。迁移 `0023_workflow_task_execution` 增加执行来源字段与唯一约束；迁移测试在 SQLite 执行 downgrade 到 `0022_task_cancel_request` 再升至 head。

**验证证据**：
- `uv run pytest -q apps/api/tests/test_workflow_execution.py apps/api/tests/test_workflow_definitions.py apps/api/tests/test_runtime_migrations.py apps/api/tests/test_task_cancel_fencing.py apps/api/tests/test_task_lease.py apps/api/tests/test_agent_tasks.py` → **117 passed / 1 skipped / 98.62s**（PostgreSQL 专属用例在 SQLite 跳过）。
- 单独复跑 `test_workflow_launch_concurrent_replays_share_the_database_winner`，包含两个独立 RuntimeService、相同请求并发重放以及相同 key / 不同输入指纹并发 → **1 passed / 0.78s**。
- Ruff（本轮后端改动文件）与 `git diff --check` → 通过。
- 上下文接续前的全 SQLite 套件结果：**1018 passed / 12 skipped / 913.78s**；该次结果在最新并发不同指纹覆盖加入前完成，因此不作为最终树的全量结论。
- F11–F13 continuation pre-final-review SQLite regression: `uv run --no-sync pytest apps/api/tests packages -q` → **1043 passed / 12 skipped / 72 warnings / 600.67s / exit 0**; output `.ai-runs/rc-hotfix2-live-acceptance/sqlite-f11-f13-final.log`. This is historical: the final run includes later malformed-graph, replay-race, and deterministic node-order fixes. Focused Workflow tests after all current fixes: **33 passed / 12 warnings**. Frontend 227 passed; typecheck/lint/build, Ruff, format (411 files), OpenAPI, i18n (3398 keys), and diff check passed. Playwright 1.62.0 + Chromium 151 on `/tmp/aiqa-f11-f13-chromium.db`: seeded project failure `fail_6539505817f0`, task `3904cb6436e1430ebfb8ba3f29baf5d7`, COMPLETED with PytestTraceback evidence in Execution Tree; no page/console errors. Screenshots `screenshots/f11-f13-*`. PostgreSQL 16 remains BLOCKED; do not infer PostgreSQL from SQLite.
- 真实 Chromium + isolated API + SQLite 已验收发布两节点自定义 key Workflow：HTTP 202、两个 step 完成、Execution Trace 带发布版本与 checksum、无页面错误。截图 `.ai-runs/rc-hotfix2-live-acceptance/screenshots/workflow-execution-tree.png`；任务 `8306330f9bcb4e1f8a1d6e15c63c4898`，execution `67fa6fef4d77464397fe5ee301d65b50`。
- 当前环境未发现 PostgreSQL 工具或 `127.0.0.1:55432` listener；因此本轮迁移/并发未声称 PostgreSQL 通过。既有 Hotfix 1 PostgreSQL 证据仍限于 §3.24 的 fencing 组。

**结论边界与未解决项**：仅可称「受限发布 Workflow 执行子集」；不可称任意 DAG 或通用 `DAG_EXECUTION_PASS`。F11–F13 后续已修复并完成 SQLite、前端和静态门禁；实际 Chromium UI 证据见本节 continuation update 与 Registry。最终 SQLite 全量为 **1048 passed / 12 skipped / 74 warnings / 738.79s / exit 0**；PostgreSQL migration/concurrency 仍 BLOCKED；全体 RC 判定 PARTIAL。

## 3.24 RC Hotfix 1 — 任务取消按租约 fencing（用户任务 m07997）

**目标：只修 R18-B2（非租约持有者可写任务终态），不加功能。** 基线 HEAD `6e2705b`（tag `rc-2026.10.22`），旧 tag 保持不动。

**1) 审计到的可绕过路径（修复前）**
- `apps/api/app/services/task_command_service.py:380 cancel()` 无条件 `update_task(status=CANCELLED)`：任何能调 `POST /api/tasks/{id}/cancel` 的进程都直接写终态，不管自己是不是执行者。
- `apps/api/app/services/task_execution_orchestrator.py:481 _finish()` 在 `current_lease()` 为 `None` 时直接写终态（无租约上下文即免检）。
- `apps/api/app/services/task_scheduler_service.py:100 recover_interrupted()` 先 `unfinished_stale()` 再无条件写 `BLOCKED`（SELECT-then-write 竞态）。
- `_execute_step` 的等待循环只认 `status == CANCELLED`，因此「请求已记录但尚未落终态」的中间态在 owner 侧完全不可见。

**2) 修复（取消 = 请求 + 由属主/授权恢复落终态）**
- 迁移 `0022_task_cancel_request`：`agent_tasks.cancel_requested_at` / `cancel_requested_by`（可逆）。
- `TaskRepository.request_cancel(task_id, actor)`：单条条件 UPDATE，只记录首个请求、永不碰终态；`TaskRepository.finish_fenced(...)`：单条条件 UPDATE，可要求 `lease_owner+lease_token` 匹配或「无人持有活租约」，`rowcount == 1` 才算成功。
- `TaskCommandService.cancel()` 改为：记请求（事件 `task.cancel_requested`）→ 仅当没人持有活租约时才 `finish_fenced(require_no_live_lease=True)`；否则只返回请求态。
- `_finish()` 全部走 `finish_fenced`；属主侧在 DAG 循环头、步骤边界、心跳（20s）三处识别请求并自行终止；把本会落 `FAILED/BLOCKED` 的终态改写为 `CANCELLED`，原结局写进 `verification.interrupted_outcome`，不丢被中断的步骤。
- 前端 `RuntimeTaskActions` 显示「取消已请求，任务会在当前步骤结束时停止。」并禁用重复取消；`Task`/`AgentTask` 类型与 OpenAPI 同步。
- 文档：`docs/TASK_LEASE.md` 新增 §4（请求 vs 终态），§5 换成 10 条 fencing 用例与浏览器验收，§6 只剩多主机 BLOCKED。

**3) 修复前可复现的证据**：取消后 `cancel_requested_at` 有值、状态停在 `RUNNING` 近一分钟，随后被写成 `BLOCKED`。根因不是代码路径没接上，而是开发机上存在一个 **Oct 21 20:43 的孤儿 uvicorn**（PID 110215，父进程已死，仍持 DB 与调度器、跑旧代码）在执行任务——正是 B2 描述的场景：非属主（HTTP 副本）写终态，真正执行者随后覆盖。`lsof runtime/ai_qa_platform.db` 定位后 `kill -9`，单进程下任务 2 秒内 `CANCELLED`。**教训：验收前必须确认只有一个进程持有 `runtime/ai_qa_platform.db`。**

**4) 验证**
- `apps/api/tests/test_task_cancel_fencing.py`（10 条，含 1 条 `@pytest.mark.postgres`）：属主边界取消 / 非属主只记请求 / 过期属主写入被拒 / 租约过期后取消立即终态 / 恢复按请求分流（CANCELLED vs BLOCKED）/ 取消与完成并发只留一条终态 / 丢失租约留 `task.lease_lost` / 重复取消幂等 / 列往返 / PG 双事务并发。
- PostgreSQL 16 容器（`aiqa-r20-pg`，`AI_QA_TEST_DATABASE_URL=…:55432/aiqa_test`）跑 `test_task_cancel_fencing + test_task_lease + test_multi_instance_recovery` → **18 passed / 61.14s**；同组在 SQLite 下 9 passed / 1 skipped。
- 真实 Chromium + 真后端 + 真 SQLite：`.ai-runs/overnight-delivery/rounds/r18b_cancel_acceptance.py` → **14/14 PASS，`failed: []`，无控制台错误**（证据 `rounds/r18b-cancel-acceptance.json`，截图 `rounds/screenshots/hotfix1-*.png`）。任务 `48fc9096fc144559b529c99c951e4526`：07:15:33 创建 → 07:15:35 点取消（`cancel_requested_at=07:15:35.739`）→ 07:15:37 `CANCELLED`，`lease_owner=null`、`finished_at` 有值、`task.cancel_requested` ×1 + `task.cancelled` ×1、`diagnose` 步骤 `CANCELLED`、再次取消 409。

**5) 判定**：`B2` **PARTIAL**。单进程与「请求/终态分离」的语义已修复并有真实浏览器证据；PostgreSQL 上的并发与 fencing 由测试覆盖；但**没有第二台主机**，`MULTI_INSTANCE_PASS` 仍为 BLOCKED，`RELEASE_CANDIDATE_PASS` 仍为 BLOCKED（B1、B3 未动）。

---

## 3.12 Round 15（2026-10-24：UX 审计、设计方向与 Direction C 选择）

- `.ai-runs/2026-10-24-ux-redesign/audit/` 完成了代码路径和信息架构审计；未声称真实浏览器复现，结论及证据级别保留在各报告中。
- Pencil 方向 A（IDE Native）、B（Flow Native）、C（Adaptive Workspace）均为概念稿；方向对比见 `.ai-runs/2026-10-24-ux-redesign/design-comparison.md`。推荐 C：复用现有 Workspace、Test Explorer、Monaco、BrowserRuntime、Task/Run Runtime、FailureWorkflow 和现有上下文布局，不引入第二套流程/运行时。
- 本轮开发只在收到明确选择后开始；C 的实现和初步验收见 §3.13，不能把概念稿当作 live-app 证据。

## 3.13 Round 16（2026-10-25：Direction C Adaptive Workspace 第一轮实现与部分验收）

### 实际完成

- 在 `apps/web/src/app/workspaceContext.ts` 增加 `WorkspaceMode` 与 `workspaceModeForContext`，以测试覆盖的 URL context 映射 Explore、Write Tests、Debug、AI Repair；`WorkspacePage.tsx` 以四模式替代五阶段导航，仍复用现有 Workspace views。
- Dashboard 的 Recent Runs 打开所选 run；首项目 CTA 指向 `/projects?create=1`，复用 Projects 现有创建对话框。
- Workers 操作错误变为可见且本地化，并补充表单/滚动区的可访问性；Recorder 用户可见文案、默认值、状态与校验迁入双语 i18n。
- E2E evidence 路径可通过 `AI_QA_E2E_EVIDENCE_DIR` 配置。Pencil C 文档增加 implementation/acceptance review frame，并明确概念稿与运行时证据的边界。
- 没有更改 DecisionService、Task Runtime、BrowserRuntime 的业务语义；AI 不判 PASS/FAIL，修复需人工批准，外部写入保持 preview-first。

### 实际验证与限制

- Web tests **192 passed**；lint、TypeScript、production build、i18n（26 namespaces / 2 languages / 3314 keys）和 targeted Ruff 通过。Vite 保留已有 Monaco 大 bundle 警告。
- 隔离 API/Web/SQLite 上用 macOS system Chrome 150 做了手工交互与 1440×900、1280×800、390×844 视口检查；检查页无 document 横向 overflow。已检查 Axe 页面为 0 violation；另有一项移动导航对比度检查因元素遮挡未完成。
- 真实 Playwright 1.62 E2E 当时因 Playwright Chromium executable 缺失而 **BLOCKED**；Chrome 155 不兼容 macOS 12.7.6。系统 Chrome 手工检查不等价于 Playwright E2E。全量 API suite 未运行，Debug 概念中的编辑器/浏览器同屏不等同于当前生产 Debug 视图。
- 截图、日志和准确命令见 `.ai-runs/2026-10-25-adaptive-workspace/04-functional-test.md`、`05-ui-review.md` 与 `evidence/`；当前验收状态为 **PARTIAL**，独立 Review 与 pinned E2E 尚待完成。

### 交接与文档恢复说明

本节根据 `.ai-runs/2026-10-25-adaptive-workspace/03-implementation.md`、`04-functional-test.md` 和 `09-final-report.md` 重建。在本轮开始时误用空内容覆写了本 handoff；随后从独立 UI worktree 的副本恢复历史主体，并在此补回 Round 15/16 摘要。恢复前主 worktree 专有的 handoff 文本没有独立快照，不能保证与覆写前逐字相同；恢复过程与校验材料保存在 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/recovery/`。此处明确披露，不把重建内容表述为原文恢复。

**下一步命令：** 先核对 Git 状态与 `stash@{0}`；完成独立只读 Review；在可用的 Playwright 1.62 Chromium 环境重跑 `.ai-runs/2026-10-25-adaptive-workspace/04-functional-test.md` 中的 discovery E2E。不得提交/推送或把不完整结果提升为 PASS。

## 3.11 Round 14（2026-10-24：Pencil/Pi 工作流评估与首项目入门 UI）

### 当前状态（以此节为准）

- 当前 worktree：`/Users/hans/Code/github/ai-qa-platform-ui-redesign`，分支 `agent/ui-workbench-pencil`，HEAD `c756994e7cc4b6789e3793369c0c43214a562722`。
- 源码未提交改动：`DashboardPage.tsx`、`ProjectsPage.tsx`、`index.css`、中英文 `dashboard.json`；本 handoff 文档也已更新。未提交、未推送。
- 原 worktree `/Users/hans/Code/github/ai-qa-platform` 的 main/stash 整合改动与 `stash@{0}` 保持独立；本分支没有触碰原 worktree。原工作区的剩余检查与最终核对待本任务后续步骤。
- run 证据位于 `.ai-runs/2026-10-24-pencil-pi-workflow/`。这些文件是本次新增的本地证据，不应提交或覆盖原工作区的 `.ai-runs/`。

### 实际完成

- 检查真实空项目 Dashboard 与 Project Management 路径；在项目数确认为 0 时，Dashboard 的项目概览条显示双语“创建第一个项目”按钮，复用已存在的 `onOpenCreateProject` 与 `/projects` 路由。数据不可用或项目数非 0 时不显示该 CTA。
- 通过同一入口实际打开现有创建对话框，修复五个字段 label 与控件的关联；确保两个“新建项目”按钮分别打开/关闭时，焦点回到实际触发按钮；在 520px 以下将框架/分支字段改单列，避免移动端选项文字截断。
- 修复 Dashboard 趋势空状态文字的低对比度，复用 `--ink-muted`，不新增 token。
- 无 API/Runtime/Agent/Provider 改动，无新项目、Golden Demo、仓库或工作区写入；提交表单未执行。
- 三个设计方向、选中规范与实际截图在 `.ai-runs/2026-10-24-pencil-pi-workflow/03-design-directions.md`、`04-selected-spec.md`、`05-browser-review.md`。用户完成登录后，`pen status` 显示 Active；CLI 生成尝试在 Claude Code 会话启动阶段被无效模型 `deepseek-v4.1-flash` 阻断，未创建 `.pen` 或导出预览。设计文件和浏览器截图仍明确区分。

### 测试证据

- `pnpm --filter @ai-qa/web test`：191 passed / 0 failed。
- `pnpm --filter @ai-qa/web typecheck`：`tsc --noEmit` passed。
- `cd apps/web && pnpm lint`：`eslint .` passed。
- `pnpm --filter @ai-qa/web build`：passed，38.04s；仍有历史 MonacoEditorPane >500kB chunk warning。
- `uv run python scripts/i18n_check.py`：25 namespaces、2 languages、3116 keys passed。
- 真实本地浏览器：Dashboard 桌面 1440×900 与手机 390×844 axe 均 0 violations；项目新建 dialog 0 violations。390px documentWidth 保持 390；dialog 342×653px，框架/分支单列；Escape 关闭且两种入口均精确恢复焦点；数据库仍为 0 项目。截图与日志见 run 目录。验证后隔离 API/Vite/Chrome 与 VS Code smoke 实例均已停止；临时浏览器/VS Code profiles 和 PID/session 文件已删除。
- `git diff --check`：passed。未运行后端测试（本轮无后端源码变化）。

### 阻断与风险

- Pencil CLI 登录已通过（`pen status`: Active），但两次 CLI 生成分别使用默认 Opus 5.5 与命令级 Sonnet 4.6，均在 Claude Code `generate_session_title` 阶段报 `unrecognized_model: deepseek-v4.1-flash`；没有实际执行 Pencil 设计操作、`.pen` 或预览输出。没有改用户全局 Claude/Pi 配置。错误日志和后续步骤见 `.ai-runs/2026-10-24-pencil-pi-workflow/06-pencil-auth-retry.md`。
- macOS 12 的 agent-browser bundled Chrome 155 无法启动（VideoToolbox symbol 缺失）；实际浏览器验证改用隔离的系统 Chrome 150。未升级系统或绕过兼容检查。
- 全量 `uv sync --locked --all-packages` 的 macOS 12 SDK build `nodejs-wheel-binaries` 失败；排除可选 `basedpyright` / `nodejs-wheel-binaries` 的 locked sync 成功，Playwright 仍为 1.62.0。

### 下一步具体命令

```bash
# 先核对当前 worktree，不要提交
cd /Users/hans/Code/github/ai-qa-platform-ui-redesign
git status --short && git log -1 --oneline
git diff --check
pnpm --filter @ai-qa/web test && pnpm --filter @ai-qa/web typecheck
(cd apps/web && pnpm lint)
pnpm --filter @ai-qa/web build
uv run python scripts/i18n_check.py

# 回原 main worktree 继续 stash 整合；先保护现状、确认 stash 仍在
cd /Users/hans/Code/github/ai-qa-platform
git status --short && git stash list
# 再依既有任务计划完成剩余 diff review、前端检查、handoff 更新；不 drop stash、不 commit/push
```

## 3.14 Direction C 二轮验收续记（2026-10-25，收尾）

- **结论 PARTIAL。** 主 worktree `/Users/hans/Code/github/ai-qa-platform` 仍为 `main` / HEAD `c756994e7cc4b6789e3793369c0c43214a562722`；保留原 staged/unstaged/untracked 用户改动、`stash@{0}`（`cf7afb211db6a6248dd4e77e7081496e86cc9487`）和 `/Users/hans/Code/github/ai-qa-platform-ui-redesign` 独立 worktree。起始 dirty paths 均仍存在、未新增 staged path，复核日志 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/logs/final-preservation-check.log`。未 commit/push/deploy/reset/clean，也未安装依赖。
- 本轮实现：Studio 无 task 的 linked-run 深链复用现有 `StudioRunPanel`；Quality Discovery 测试 fixture 显式关闭 loopback server，并使用同一现有 `PlaywrightBrowserRuntime` 实现的独立实例；BrowserRuntime 现在跟踪 session/resource close 与 Playwright stop task，`close_all()` 有界等待、Runtime-owned 强制 stop 与可重试失败状态。另将 `apps/api/app/api/test_designs.py` 中导入的 `test_design_access` 别名为 `_test_design_access`，避免 pytest 误把路由依赖收集成测试；`Depends` 仍使用同一个 callable，路由语义不变。没有新增 Runtime/Agent/Provider，也未改变 AI verdict/人工审批语义。
- 最终聚焦回归：`apps/api/tests/test_browser_runtime.py` + `test_cancelled_discovery_finalizes_as_stopped_and_closes_browser` + `test_quality_discovery_live_e2e.py` → **25 passed / 25.99s**；日志 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/logs/runtime-regression-final.log`。Ruff check/format 和 `git diff --check` 通过。
- 首次最终全量回归发现 pytest 误收集 `test_design_access`（`TopRequest` 无 `path_params`）；改为 `_test_design_access` 后项目 ACL 回归 **9 passed**。最终完整非 slow API 回归：**755 passed, 9 skipped, 3 deselected, 78 warnings / 514.33s，exit 0**；live-discovery E2E 通过且 pytest 正常收尾。日志 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/logs/backend-not-slow-final-after-collection-fix.log`。
- 之前的实际 UI 验收仍有效：system Chrome 150 上 Studio linked-run acceptance 1 passed、discovery-to-coverage E2E 1 passed；响应式证据 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/studio/studio-749bac45b7/`。Web tests/typecheck/lint/build 通过，见 `.ai-runs/2026-10-25-adaptive-workspace/08-regression.md`。system Chrome 仅补充，不等价 pinned Chromium。
- 最终独立只读 Review `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/logs/independent-review-final-collection-fix.txt`：未发现本轮新增 P0–P3 blocker；记录既有跨 event loop 复用风险：`PlaywrightBrowserRuntime._start()` 会丢弃旧 loop 的资源/driver/stop task。本轮单 loop ASGI 与测试专用 Runtime 不触发，未扩大范围修复。
- Pinned Chromium **BLOCKED**：Playwright 1.62.0 的 bundled executable 路径不存在，证据 `evidence/logs/pinned-chromium-availability.log`（`chromium_exists=False`）；没有安装浏览器。仓库有 Ubuntu GitHub Actions workflow，但没有包含当前未提交 diff 的 CI/Linux 运行；按保全要求未 commit/push 触发远端执行。因此总体保持 **PARTIAL**。
- 结束时无 pytest、Playwright driver、Vite 或 Uvicorn 项目进程；原有用户 Chrome 保留、未终止。根 `test.pen` 仍 0 bytes / SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；基线未记 checksum，不能声称逐字节比对。handoff 未暂存内容恢复 caveat 见 §3.13 与 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/recovery/recovery-note.md`。

### 后续步骤（保持范围）

1. 在 Playwright 1.62.0 bundled Chromium 可执行的 CI/Linux 环境重跑 `test_quality_discovery_live_e2e.py`、Studio 与 discovery-to-coverage E2E；在此之前 pinned browser 继续 BLOCKED。
2. 若后续支持跨 asyncio event loop 复用 Runtime，再单独设计旧 loop 上的资源清理/拒绝策略；本轮不扩大范围处理。

## 3.15 Direction C Adaptive Workspace 第三轮实现与验收（2026-10-25）

### Git 与保护状态

- 当前 worktree `/Users/hans/Code/github/ai-qa-platform`，分支 `main`，HEAD `c756994e7cc4b6789e3793369c0c43214a562722`；`stash@{0}` 仍为 `cf7afb211db6a6248dd4e77e7081496e86cc9487`（`before pulling origin/main`）。
- 保留已有 staged/unstaged 改动、未跟踪证据/设计/缓存文件、独立 worktree 与 stash；未执行 add/commit/push/deploy/reset/clean。`test.pen` 仍为 0 bytes，当前 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- 本轮报告和截图位于 `.ai-runs/2026-10-24-ux-redesign/round-three/`；不把这些本地证据提交。

### 本轮实现

- 将 Workspace app chrome 收紧为紧凑导航与四种自适应模式；Debug 复用现有 `RuntimeBrowser` / `RuntimeTimeline` 显示浏览器与运行证据，加入最近运行上下文和小屏幕可关闭上下文抽屉。
- 嵌入式 Write/Debug 在没有显式 file/case context 时，只读打开排序稳定的现有 `tests/test_*.py`；尊重 `caseId` 和 legacy `testCaseId`，不创建、保存、校验或执行文件。
- Explore 自然语言流程改为可展开区；AI Repair 空队列、加载和请求错误分别呈现，空队列提供保留项目参数的运行历史入口。
- 修正 file tab 的键盘选择与关闭按钮名称；新增默认测试文件路径选择的单元测试。
- 本轮未改 API/Worker/Runtime/DecisionService 实现，也未新增 Runtime/Agent/Provider/依赖。PASS/FAIL 仍来自持久化测试结果；修复仍需人工批准。

### 最终验证

- `pnpm --dir apps/web test`：**193 passed / 0 failed**；`pnpm --dir apps/web typecheck`、`pnpm --dir apps/web lint`、`git diff --check` 均通过。
- `uv run python scripts/i18n_check.py`：**26 namespaces / 2 languages / 3327 keys** 通过。
- `pnpm --dir apps/web build`：通过，38.01s；仍有既有 Monaco >500 KB bundle warning。
- 用隔离项目 `Direction C Isolated Validation` 和 macOS system Chrome 150/agent-browser 检查 1440×900、1280×800、390×844；手机文档宽度未溢出，验证了 Debug context drawer 开关、Explore 自然语言区域展开/收起、Repair run-history 项目上下文、默认测试文件只读打开和键盘选取。
- Axe 4.12.1：Debug desktop 0 violations，1 组 color-contrast incomplete（已人工核对可见文字对比度：6.50:1、14.53:1、5.40:1；Monaco textarea 是透明输入层）；Explore mobile、Repair mobile 各 0 violations / 0 incomplete。`.studio-tab-close` 的 button-name 问题已修复。
- 详细证据：`.ai-runs/2026-10-24-ux-redesign/round-three/{03-implementation,04-functional-test,05-ui-review,06-code-review,07-fixes,08-regression,09-final-report}.md` 和 `evidence/`。

### 结论与未验证项

- 本轮目标 UI 范围实现完成；整体真实流程证据仍标为 **PARTIAL**，不是全流程 PASS。
- 隔离项目没有失败记录，无法验证有真实失败证据时的 Repair/proposal 流程；Recorder 没有活动浏览器会话，因此录制/保存/运行流程未验证。未为验证而创建失败、启动录制器或执行测试。
- 手工 system Chrome 不是 pinned Playwright E2E；本轮没有跑 API/Worker regression（无后端改动且范围明确排除）。

### 下一步

如需继续，只运行与实际变更范围相关的命令并保留当前工作树：

```bash
cd /Users/hans/Code/github/ai-qa-platform
git status --short --untracked-files=no && git rev-parse HEAD
pnpm --dir apps/web test && pnpm --dir apps/web typecheck && pnpm --dir apps/web lint
pnpm --dir apps/web build
```

不要清理未跟踪文件、改动 stash、提交或推送；如后续能提供隔离失败记录/活动浏览器会话，再单独补验对应流程。

## 3.16 Direction C Adaptive Workspace 第四轮 UI/UX 精修（2026-10-25，已完成）

### Git 与保护状态

- 当前 worktree `/Users/hans/Code/github/ai-qa-platform`，分支 `main`，HEAD `c756994e7cc4b6789e3793369c0c43214a562722`。已有 staged/unstaged/untracked 文件、`stash@{0}`、独立 worktree 与 `test.pen` 均保留；`test.pen` 仍 0 bytes，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- 不提交、推送、部署、reset 或 clean；Round Four 新证据位于 `.ai-runs/2026-10-24-ux-redesign/round-four/`。

### 已完成：基线截图与审查

- Pencil Direction C 四个正式 mode frame 已通过 Pencil MCP 检查；真实 system Chrome 在隔离项目 `proj_460a6ea4877b` 下对 Explore、Write、Debug、Repair、Dashboard、Projects、Quality 完成 1440×900、1280×800、390×844 基线截图。22 张 PNG 位于 `round-four/evidence/before/`。
- 21 组截图 document `scrollWidth <= innerWidth`。四个 Workspace mode 的移动端 Axe 4.12.1 均为 0 violations / 0 incomplete；Dashboard 和 Projects 0 violations / 1 incomplete。
- 已确认 Quality 移动端覆盖表的真实无障碍缺陷：390px viewport 下 scroll container 336px、table 510px，`overflow-x:auto` 但不可聚焦；Axe 4.12.1 报 `scrollable-region-focusable` serious。
- 已修复三项经浏览器/Axe 证据确认的问题：Quality 移动端表格不可键盘滚动、语言切换按钮 accessible name 不含可见标签、Debug 移动端详情 scroller 不可键盘滚动。最终 Axe 4.14.0 对 7 个移动页面与 Debug/Quality desktop 均为 0 violations；Explore/Write/Dashboard/Projects 留有少量 `color-contrast` incomplete（未在本轮人工复核）。
- `docs/UI_DESIGN_SYSTEM.md` 与当前 `apps/web/src/index.css` 的 canvas/accent token 值过时；遵循项目规则，以当前代码为准，暂不做无关 token 文档改写。

### 实现、最终验证与未解决项

- Round Four 记录完整，详见 `round-four/00-request.md` 至 `09-final-report.md`；真实 Chrome Before/After 截图分别 22/23 张，另有交互聚焦态截图。
- 最终改动位于 `QualityPage.tsx`/`QualityPage.css`、`DebugPanel.tsx`、`Navigation.tsx`、`index.css` 与 EN/zh-CN `quality.json`、`studioPanels.json`；真实 Chrome 已验证 Quality 左右键和 Debug 上下键滚动，焦点 ring/提示可见，三种尺寸下 21 个页面视图均无文档溢出。
- 最终 Web 回归：193 tests passed；typecheck/lint/i18n（26 namespaces、2 languages、3329 keys）/build/diff-check 全通过。初版 Quality/Navigation 后有一次 detector scan；Axe-driven Debug 修复后再有唯一一次 final post-edit scan。两次结果相同：两个已有 side-tab 警告（Monaco glyph triangle 与未使用的 `.card-rail`），未添加 ignore。评分：UI/UX Implementation 8/10；Full Platform E2E 4/10，PARTIAL。
- 未解决限制：隔离项目没有失败记录，不能验证真实非空 Repair/proposal；无活动 Recorder；未跑 pinned Playwright E2E 或 API/Worker regression。后续只有在获得隔离失败/活动录制数据时再单独补验。未复核的 contrast incomplete、dark mode 截图与既有 Monaco chunk warning 详见 `09-final-report.md`。
- 执行边界：只使用现有隔离项目；未运行测试用例或启动 Recorder；未改 API/Worker/Runtime，不提交/推送，不改其他 worktree、stash 或 `test.pen`。

```bash
cd /Users/hans/Code/github/ai-qa-platform
pnpm --dir apps/web test && pnpm --dir apps/web typecheck && pnpm --dir apps/web lint
uv run python scripts/i18n_check.py
pnpm --dir apps/web build && git diff --check
```

## 3.17 Direction C Workspace 第五轮实际布局重构（完成；全平台 E2E 仍未验收）

- 当前 Git Commit：`c756994e7cc4b6789e3793369c0c43214a562722`（branch `main`，未创建提交）。本轮完成实际 React 布局改造：Debug 桌面 Editor/Browser 可调并列分屏，移动 Code/Browser/Steps/State 四面板；Explore 桌面 Browser/Task/Steps，移动 Browser/Task 切换；隐藏面板保持挂载，保留草稿/步骤状态、URL context、现有 Recorder/Runtime 和人工批准边界。桌面 RuntimeTimeline 仍由 Browser evidence details 展开，移动 Steps 使用同一 snapshot。实现与风险见 `.ai-runs/2026-10-25-adaptive-workspace/round-five/{03-implementation,06-code-review,09-final-report}.md`。
- 浏览器证据：使用隔离项目 `proj_460a6ea4877b`，system Chrome 150.0.7871.125 经 CDP `9222`；Chrome 155 bundled 因 macOS VideoToolbox symbol 不兼容不能启动，所以本轮是手工 Chrome/CDP 验证，不是 pinned Playwright E2E。Before 六张、After 十张 PNG 在 `.ai-runs/2026-10-25-adaptive-workspace/round-five/evidence/{before,after}/`。1440×900 / 1280×800 / 390×844 均实测，文档无横向溢出；Debug 1440 Monaco 从 106px/5 行增加至 292px/13 行，Explore Browser viewport 从 193px 增至 514px；更多 DOM 结果见 `05-ui-review.md`。
- 功能/无障碍：键盘与指针分屏、比例限制/会话存储、各移动面板导航、Explore 草稿保留和自然语言折叠已手工验证。Axe 4.12.1 检查 Debug 移动四面板和 Explore Browser/Task（当前空 Runtime 状态），修复两个 scrollable-region keyboard-access 发现后各 0 violations。共享 RuntimeTimeline 的 populated scroll region 也已加命名/键盘焦点和可见 focus ring，但因无 Runtime 记录未能在浏览器扫描该分支。未启动 Recorder/browser session 或平台 TestRun，未触发 Run/Save/Generate/AI action，未写入项目数据。
- 最终前端检查（最新代码）：`pnpm --dir apps/web test` 194/194 通过；`lint`、`typecheck`、`build` 通过；`uv run python scripts/i18n_check.py` 通过（26 namespaces / 2 languages / 3338 keys）；`git diff --check` 通过。Build 保留 Monaco 约 4.03MB chunk 的既有 Vite 大块警告。API/Worker、populated Runtime/Repair、Recorder execution、pinned Playwright 和全平台 E2E 未运行；Full Platform E2E 仍为 **4/10 PARTIAL**，不可称为整体验收通过。Round Four UI/UX 8/10 与全平台 4/10 独立结论见 `.ai-runs/2026-10-24-ux-redesign/round-four/09-final-report.md`；本轮 UI layout 评审 8/10。
- 状态保护复核：HEAD 未变；既有 staged/unstaged/untracked 改动、`stash@{0}`（`cf7afb211db6a6248dd4e77e7081496e86cc9487`）、worktree `/Users/hans/Code/github/ai-qa-platform-ui-redesign` 均保留。`test.pen` 仍 0 bytes / SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。没有 commit/push/deploy/reset/clean。
- 本轮详细阶段记录：`00-request.md`、`01-analysis.md`、`02-plan.md`、`03-implementation.md`、`04-functional-test.md`、`05-ui-review.md`、`06-code-review.md`、`07-fixes.md`、`08-regression.md`、`09-final-report.md`，均位于 `.ai-runs/2026-10-25-adaptive-workspace/round-five/`。如果需要复跑 Web 回归：

```bash
cd /Users/hans/Code/github/ai-qa-platform
pnpm --dir apps/web test && pnpm --dir apps/web lint && pnpm --dir apps/web typecheck
pnpm --dir apps/web build && uv run python scripts/i18n_check.py && git diff --check
```

- 后续全平台验收的前置条件：使用独立 fixture 准备非空 Runtime/Failure，再按 Playwright 1.62.0 验证；另外跑 API/Worker regression。不得在生产项目启动录制或运行来补证据。
