# M1/M2 最终质量门报告

日期：2026-10-29 · 基线 `d66c5319d7d080aaac04dd85933bba23c3c10f85`（未提交改动）
分支 `main` · 环境 Linux 6.6.87.2 WSL2 / Python 3.13.16 / Node 24.22.0 / Playwright 1.62.0

---

## 1. 最终判定

| 里程碑 | 判定 | 说明 |
|---|---|---|
| **M1 基线盘点** | **PARTIAL** | 5 项交付物全部产出、OpenAPI 基线 PASS；PG16 基线子项 BLOCKED（环境） |
| **M2 终态原子化** | **PARTIAL** | 实现与 SQLite 通道 PASS；6 项事务要求 4 PASS / 2 PARTIAL；PG16 BLOCKED；前端 E2E 为既有缺陷 |

两者都**不能**判 PASS：PASS 需要双库通道与全部验收项，而 PostgreSQL 16 在本环境不可用。

---

## 2. 全量测试（两轮，均记录退出码）

### 2.1 首轮（测试文件并非最终状态）

- 命令：`uv run pytest apps/api/tests -q --timeout=900`
- 收集 **921**（908 passed / 1 failed / 12 skipped），1013.87s，**exit 1**。
- 失败原因：`AssertionError: API/Vite servers did not become ready; ... Vite exit=1`，Vite 日志 `Port 46847 is already in use`。
- 归因：**测试夹具不稳定**（`_free_port()` 绑定后释放、Vite 以 `--strictPort` 启动的 TOCTOU 竞争），与产品代码无关。
- 收集数缺口：套件启动（11:52:52）早于最后 2 个用例落盘，921 = 914 + 7；当前应收集 923。**该轮不是最终代码的证据。**

### 2.2 最终轮（最终测试文件）

- 命令同上；收集 **923**（910 passed / 1 failed / 12 skipped），685.42s，**exit 1**（`PYTEST_EXIT=1` 已写入日志）。
- 910 + 1 + 12 = 923，数量自洽；9 个未提交新增用例全部被收集执行。
- 唯一失败：`test_discovery_coverage_e2e.py::test_real_browser_discovery_to_playwright_coverage_e2e`，失败点为 `.workspace-mode-tab` 点击被 `.workspace-main-heading` 拦截。
- 无超时、无崩溃、无 INTERNALERROR。
- 12 个 skip：6 个 PostgreSQL 专项因缺少 `AI_QA_TEST_DATABASE_URL`（`test_postgres_integration.py`×3、`test_postgres_migrations.py`×1、`test_runs_and_failures.py:573`、`test_task_cancel_fencing.py:253`）；另 6 个是 opt-in live/provider acceptance（Jev acceptance×2、enterprise journey×2、browser-agent live×1、Studio/debugpy×1）。全量日志未带 `-rs`，故通过当前测试代码的 skip gate 和定向复跑归因；这些 live acceptance 均未执行，不是通过。详情见 [10-s0-stabilization.md](10-s0-stabilization.md) §2.3。

范围说明：命令只收集 `apps/api/tests`；仓库 `testpaths` 合计 1077 个用例，qa-core/integrations/worker/platform-config/project-model 的 154 个用例不在本日志范围。

---

## 3. 前端 E2E 归因：EXISTING DEFECT

| 运行 | 结果 |
|---|---|
| 当前树单独复现 | 1 failed / 39.73s，点击被 `.workspace-main-heading` 拦截 |
| 基线 worktree `d66c531`（Python 3.11） | 1 failed / 62.70s，同一拦截 |
| 基线 worktree `d66c531`（Python 3.13） | 1 failed / 48.44s，同一拦截 |
| QA 独立对照：基线 / 当前树 | 1 failed / 40.69s、1 failed / 40.37s，同一拦截 |
| DOM 探针（基线代码） | 见下 |

根因（基线代码即存在）：

- `apps/web/src/index.css:914-918` 给 `.workspace-shell` 定义 **3 行**网格（`auto auto minmax(0, 1fr)`），但 shell 现有 **4 个子元素**（header、stage-nav、mode-nav、grid）。
- mode-nav 落入第 3 行，被压成 **0px**；实测 `gridTemplateRows = 68.6875px 72px 0px <grid>`（1280×720 与 1280×800 相同）。
- nav 内容（tab 高 38px）溢出，grid 从 y≈228.7 绘制，`.workspace-main-heading` 覆盖 tab 下半部；`elementFromPoint` 返回 heading，点击被拦截。

交叉验证：`apps/web` 与 E2E 测试文件在基线/当前树逐字节一致（无 diff）；本轮改动只涉及后端 service/repo/tests/docs。E2E 在失败前已通过 Discovery COMPLETED、gap、生成用例等断言，说明 M2 影响的后端路径在该运行中成功。

结论：**EXISTING DEFECT，不是本轮回归，不是测试不稳定**（4 次独立运行稳定复现）。

证据目录：`.ai-runs/2026-10-29-arch-refactor-m1-m2/e2e-baseline/`（`probe-failure.json`、`probe-failure-1280x800.json`、`probe-failure.html`、`probe-failure.png`、`probe-trace.zip`、`qa-baseline-e2e-control.log`、`qa-current-e2e-control.log`）与 `e2e-current-tree.log`。

---

## 4. PostgreSQL 16：BLOCKED

- WSL 内 `docker` 是悬空符号链接（`/usr/bin/docker → /mnt/wsl/docker-desktop/...`，目标不存在）；`/var/run/docker.sock`、`/mnt/wsl/docker-desktop` 均不存在。
- Windows `docker.exe desktop status` → `Status: stopped`；`docker.exe ps` → `Docker Desktop is unable to start`；`docker.exe desktop start` 返回 "already running" 但引擎仍 stopped。
- 无本地 `postgres`/`psql`/`pg_ctl`，无 5432 监听；`AI_QA_TEST_DATABASE_URL` 未设置。
- 未安装任何工具、未修改 Docker 配置。

此前 macOS + Docker 环境的 PG16 结果（19 passed）在本机不可复现，已在 handoff 中标注，**不得**作为 M2 双库证据。

恢复所需：宿主机可用的 Docker Desktop 引擎 + WSL 集成，或可达的 PostgreSQL 16 实例。

---

## 5. M2 六项事务边界核对（QA 独立复核）

| # | 要求 | 覆盖 | 判定 |
|---|---|---|---|
| 1 | 终态与事件同一事务 | `test_finishing_a_run_persists_status_and_terminal_event_together` + 回滚注入用例 | PASS（happy-path 单独不足以证明，回滚用例才是证据） |
| 2 | 事件持久化失败回滚 | `test_finishing_a_run_rolls_back_status_when_event_persistence_fails` | PASS |
| 3 | 状态已变化时旧任务不覆盖 | `test_finishing_a_run_does_not_overwrite_a_status_changed_after_it_started` | PASS |
| 4 | 重复完成不重复事件 | `test_finishing_a_run_twice_does_not_duplicate_its_terminal_event` | PASS（旧代码已有终态早退，回归价值大于缺陷检测） |
| 5 | 广播失败时 DB 正确且错误可追踪 | Discovery 用例（caplog）+ TestRun 顺序用例 | **PARTIAL**：Discovery 已证；TestRun 未断言日志，worker 外层的错误转换路径未直接执行 |
| 6 | 并发完成/迟到写入受守卫保护 | 并发用例 + 交错用例 + recovery 用例 | **PARTIAL**：仅进程内锁串行化；跨进程/多副本未验证 |

红/绿证据：同一失败注入断言在 `d66c531` 旧两事务路径上失败（`assert 'COMPLETED' == 'RUNNING'`），在新代码上回滚通过。日志 `e2e-baseline/red-evidence-d66c531.log`。

---

## 6. 独立评审结论

| 评审 | 结论 | 关键保留项 |
|---|---|---|
| architecture-critic | **CONDITIONAL**，无 BLOCKER | MAJOR：`_update` 用 `**values` 接收参数，未知关键字被静默吞掉，「终态必有事件」仅靠调用约定；MAJOR（必要性）已由红/绿证据关闭；MINOR：并发用例只证进程内锁、守卫依赖 `version_id_col`、终态写产生两次 UPDATE、收尾遇状态变化会放弃写入 |
| qa-reviewer | **M2 实现 PASS（SQLite）/ 整体 PARTIAL** | 全量套件首轮漏收 2 个新用例（已补跑 21 passed）；PG16 BLOCKED；E2E 归因成立但需拆清 Vite 端口 flake；文档计数漂移（已修正） |

---

## 7. 关键风险与未完成项

| 项 | 级别 | 处置 |
|---|---|---|
| PostgreSQL 16 事务/并发证据缺失 | 阻断双库结论 | 需环境；维持 BLOCKED |
| `_update` 参数静默吞掉（终态不变量仅约定） | MAJOR | 未改代码；建议 M3 前决定是否加断言/唯一入口 |
| 跨进程终态竞争未验证 | MAJOR（对多副本而言） | M7 harness |
| 前端 mode-nav 0 高度既有缺陷 | P1（产品缺陷） | 本轮不修；需单独批准 |
| TestRun 广播失败日志未断言 | MINOR | 记录 |
| 12 skip 中 6 个原因未知 | UNKNOWN | 记录 |
| M2 文档与 handoff 计数漂移 | 已修正 | — |

---

## 8. 能否关闭 M1/M2

- **M1：可以关闭（PARTIAL）**。交付物齐备；PG16 基线作为环境遗留项转入后续。
- **M2：可以关闭（PARTIAL）**。代码实现、SQLite 失败注入、红/绿对照、最终全量套件（最终文件）均已完成；未完成项全部是环境（PG16）或跨进程范围（M7）或范围外产品缺陷（前端 mode-nav）。关闭不等于「双库通过」，不得对外声称多副本安全。

## 9. 是否具备进入 M3 的条件

**技术前置基本满足，但未获授权，不进入 M3。**

- M3 依赖 M2 的「事务与错误处理边界稳定」，这一条件在 SQLite 通道已成立。
- 建议在进入 M3 前由人工决定三件事：
  1. 是否先处理 critic 的 MAJOR（`_update` 显式参数 + 终态断言）；
  2. PG16 是否作为 M3 的并行阻塞项，还是推迟到 M7；
  3. 前端 mode-nav 缺陷是否单独立项修复。
- 用户已明确当前不授权 M3；质量门在此停止。
