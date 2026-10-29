# M2 终态写入原子化

状态：**已完成（SQLite 通道）；PostgreSQL 通道 BLOCKED**
基线：`d66c531` + 工作区未提交改动 · 完成日期 2026-10-29
对应路线：[05-refactor-roadmap.md](05-refactor-roadmap.md) M2 · 缺陷 F3

---

## 1. 问题与范围

M2 要消除的是：**终态与终态事件跨越两个事务提交**，进程若在两次写之间崩溃，会留下「已完成但没有说明为什么完成/结束的事件」。

| 域 | 原状 | 判定 |
|---|---|---|
| Quality Discovery | `_finish_locked` 先 `_update`（事务 1，提交状态），再 `_event`（事务 2：`_change_result` 写事件并提交），最后 `live.publish` | **缺陷存在**，已修 |
| TestRun | `persist_suite_result` 用单条带状态守卫的 `UPDATE`（`transition_run_status`）写终态与计数，随后 `commit`，再 `event_bus.publish` | **已原子**，无需改代码；补一个顺序回归测试 |

范围外（明确不做）：不改 schema、不新增事件表、不改判定函数 `_verdict`、不改 TestRun 的分批结果写入。

---

## 2. 实现

### 2.1 Discovery（`quality_discovery_service.py:_finish_locked`）

```python
message = error or f"探索状态：{status}"
updated = await self._update(
    run_id,
    expected_statuses=(row.status,),
    status=status,
    error=error,
    finished_at=utc_now() if status in self.TERMINAL else None,
    persisted_event=(f"run.{status.lower()}", message),
)
if updated is None:
    return
self._publish_event(run_id, f"run.{status.lower()}", message)
self.live.publish(run_id, event_payload("run.finished", ...))
```

要点：

1. **同一事务**：状态、错误、`finished_at` 与 `run.<status>` 事件由一次 `_update` 写入；`_update` 内部先 `repo.update` 状态，再在同一 session 追加事件到 `result["events"]`，最后一次 `commit`。
2. **提交后才广播**：`_publish_event` 与 `live.publish` 都在 `_update` 返回非空之后执行。广播失败不会回滚已提交的终态。
3. **状态守卫**：`expected_statuses=(row.status,)` 取自函数开头的新读；若运行在 `_build_quality_map` 期间已被其它路径改变（例如用户停止），本次终态写入放弃，不覆盖更新的决定，也不补发事件。
4. **不再有第二次持久化事件写**：原先的 `await self._event(...)` 已移除；`_event` 仍用于非终态事件，未改动。

失败语义：`_append_persisted_event` 或第二次 `repo.update` 抛错时，`_update` 不捕获（只重试 `StaleDataError` / `database is locked`），session 上下文回滚——状态与事件要么都在，要么都不在。

### 2.2 TestRun

未改代码。复核结论：

- `transition_run_status`（`test_run_repo.py:153-192`）是一条带 `status IN (QUEUED, RUNNING)` 守卫的 `UPDATE`，与计数、`log_output`、`finished_at` 同一条语句。
- `close_running_sessions` 与终态转换在同一个 repository scope、同一次 `commit`（`test_run_service.py:840-860`）。
- TestRun **没有持久事件表**；`RUN_FINISHED` 是进程内 SSE 消息，提交后发布。SSE 丢失不影响终态可读性（状态、计数、`log_output` 都在行上）。

因此 TestRun 的「状态 + 事件原子」在当前模型下等价于「终态先提交、再广播」，已满足；新增回归测试锁定该顺序。

---

## 3. 新增测试

| 测试 | 断言 |
|---|---|
| `test_finishing_a_run_persists_status_and_terminal_event_together` | `_finish` 后状态 COMPLETED、`finished_at` 非空、`result.events == ["run.completed"]` |
| `test_finishing_a_run_publishes_only_after_the_commit` | 让 `live.publish` 抛错：状态与事件仍已提交，证明广播在提交之后；同时断言错误仍写入 `app.quality_discovery` 日志 |
| `test_finishing_a_run_rolls_back_status_when_event_persistence_fails` | 事件写入抛错：状态仍 RUNNING、`finished_at` 为 None、无事件、无广播 |
| `test_finishing_a_run_does_not_overwrite_a_status_changed_after_it_started` | 终态写入前状态被改成 COMPLETED：不覆盖、不重复写事件 |
| `test_finishing_a_run_twice_does_not_duplicate_its_terminal_event` | 连续两次 `_finish`：只有一条 `run.completed` |
| `test_concurrent_finishes_produce_exactly_one_terminal_event` | 两个 `_finish` 并发：终态唯一、事件恰好一条（**仅证明进程内串行化**，见 §5） |
| `test_a_run_is_persisted_before_its_finish_event_is_broadcast`（TestRun） | `RUN_FINISHED` 广播抛错后，数据库仍是 PASSED 且计数已提交 |

M2 新增 6 个 Discovery 用例 + 1 个 TestRun 用例。加上本轮早先的 2 个启动恢复用例（`:289` 竞态不覆盖、`:313` 事件写失败回滚，属于前一个 Discovery 修复里程碑），`test_discovery_task_runtime.py` 当前共 **21 passed**；这 2 个恢复用例同样覆盖状态守卫与事件回滚语义。

### 3.1 红/绿对照（必要性证据）

为避免「只测新实现」，在隔离 worktree `/tmp/aiqa-baseline-d66c531`（`d66c531` 旧两事务实现）上运行同一失败注入断言：

- 旧代码：`_update` 先提交 COMPLETED，随后 `_event` 抛错 → `AssertionError: assert 'COMPLETED' == 'RUNNING'`（`1 failed`），日志 `.ai-runs/2026-10-29-arch-refactor-m1-m2/e2e-baseline/red-evidence-d66c531.log`。
- 新代码：同一场景回滚，状态保持 RUNNING、无事件（本文件 §3 第 3 条用例，**PASS**）。

这证明 F3 是真实缺陷，不是仅由源码推断。

---

## 4. 验证证据

环境：Linux 6.6 WSL2，Python 3.13（`uv`），SQLite（默认测试库）。

| 命令 | 结果 |
|---|---|
| `uv run pytest apps/api/tests/test_discovery_task_runtime.py -q` | **21 passed**（全量套件启动后新增的 2 个用例已单独补跑） |
| 全量：`uv run pytest apps/api/tests -q --timeout=900` | **1 failed, 908 passed, 12 skipped**（1013.87s；失败项见 §6） |
| 当前代码树单独复现失败项：`AI_QA_E2E_EVIDENCE_DIR=/tmp/aiqa-current-evidence uv run pytest ...test_discovery_coverage_e2e.py::test_real_browser... -q` | **1 failed in 39.73s**（`.ai-runs/.../e2e-current-tree.log`） |
| 基线 worktree 同一 E2E（Python 3.13、独立 SQLite/端口/证据目录） | **1 failed in 48.44s**，失败点相同 |

（早前定向回归在新增最后 2 个用例之前执行：四文件合跑 **148 passed / 1 skipped**，五文件回归 **72 passed / 1 skipped**；新增用例落地后，`test_discovery_task_runtime.py` 已整体重跑为 **21 passed**，其余文件未再变更。）

### 4.1 浏览器 E2E 的两种失败模式（必须分开）

| 运行 | 失败点 | 归因 |
|---|---|---|
| 首次全量套件（`full-suite.log`，921 收集） | `AssertionError: API/Vite servers did not become ready; ... Vite exit=1`；Vite 日志 `Port 46847 is already in use` | **测试夹具不稳定**：`_free_port()` 先绑定端口再关闭，Vite 以 `--strictPort` 启动，存在 TOCTOU 竞争。与产品代码无关 |
| 当前树单独复现（`e2e-current-tree.log`） | `.workspace-mode-tab` 点击被 `.workspace-main-heading` 拦截 | **既有 UI 缺陷**（见下） |
| 基线 worktree `d66c531` 单独运行（两次，Python 3.11/3.13） | 同一拦截 | **EXISTING DEFECT**，与本轮改动无关 |
| QA 独立对照（基线 / 当前树，各自独立证据目录与端口） | 同一拦截（40.69s / 40.37s） | 同上；日志归档在 `e2e-baseline/qa-*-control.log` |

UI 缺陷根因（基线代码，`apps/web` 与本轮改动无关，工作区该目录干净）：

- `apps/web/src/index.css:914-918` 为 `.content-viewport.is-workspace .workspace-shell` 定义 **3 行**网格（`auto auto minmax(0, 1fr)`），但 shell 现有 **4 个子元素**：header、stage-nav、mode-nav、grid。
- mode-nav 落入第 3 行 `minmax(0,1fr)`，被压成 0px；实测 `gridTemplateRows = 68.6875px 72px 0px <grid>`（1280×720 与 1280×800 相同）。
- nav 内容溢出（tab 高 38px），grid 从 y=228.7 开始绘制，`.workspace-main-heading` 覆盖 tab 下半部，`elementFromPoint` 返回 heading，点击被拦截。
- 该状态出现在 `workspace-shell is-write` / `workspace-main-panel is-cases-panel`、非 inline 模式导航的布局。

处置：本轮**不修改**前端产品代码；记为既有缺陷，需单独批准后修复。E2E 验收视口（1280×800 / 1440×900 / 1920×1080）的交互断言属于后续修复的验收项。

### 4.2 PostgreSQL 16

**BLOCKED**。复核结果：

- `docker` CLI 在 WSL 内不可执行：`/usr/bin/docker` 是指向 `/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker` 的悬空符号链接，`/mnt/wsl/docker-desktop` 不存在，`/var/run/docker.sock` 不存在。
- Windows 侧 `docker.exe desktop status` → `Status: stopped`；`docker.exe ps` → `Error response from daemon: Docker Desktop is unable to start`；`docker.exe desktop start` → `Docker Desktop is already running`，但引擎仍为 stopped。
- 无本地 `postgres`/`psql`，无 5432 监听。
- 未执行安装、未修改 Docker 配置、未启用 WSL systemd。

结论：需要宿主机上可用的 Docker Desktop 引擎与 WSL 集成，或一个可达的 PostgreSQL 16 实例 + `AI_QA_TEST_DATABASE_URL`。上一轮在 macOS + Docker 取得的 PG16 结果不能作为本环境证据。

按 `docs/QUALITY_GATES.md` §5.5：

- 本次 SQLite 结果**不覆盖** PostgreSQL 的并发与事务差异。
- 未设置 `AI_QA_TEST_DATABASE_URL` 时 PG 用例被静默 skip；skip 计数已单独记录，不能读作「全绿」。

---

## 5. 风险与回滚

| 项 | 说明 |
|---|---|
| 事务变大 | 只是把原有的第二次写并入第一次；`_build_quality_map` 仍在事务外 |
| 行为变化 | 终态写入新增状态守卫：收尾期间状态被其它路径改变（例如 PAUSED）时，本次收尾放弃写入并依赖恢复路径。这是更保守的语义，不是回归 |
| 回滚 | 纯代码回退，无 schema、无数据迁移 |
| 未覆盖 | 跨进程并发终态写入；PG16 事务行为；多 API 副本 |

### 5.1 独立架构评审的保留项

| 编号 | 级别 | 内容 | 处置 |
|---|---|---|---|
| M1 | MAJOR | `_update` 用 `**values` 接收参数，未知关键字会被 `repo.update` 当作属性静默吞掉；「终态必须有终态事件」目前只是调用约定 | 本轮不改产品代码；记录为进入 M3 前的整改项 |
| M2 | MAJOR | 必要性证据已由 §3.1 的红/绿对照补齐 | **已关闭** |
| m1 | MINOR | 并发用例只证明进程内锁串行化，不证明 DB 守卫 | 文档已标注；跨进程用例留待 M7 |
| m2 | MINOR | 守卫原子性隐式依赖 `version_id_col` | 记录；建议加锁定测试 |
| m3 | MINOR | 终态写入产生两次 UPDATE（version +2） | 记录；可合并为一次 update |
| m4 | MINOR | 文档测试计数漂移 | **已修正**（本文件与 handoff） |
| m5 | MINOR | 收尾遇到非快照状态时放弃写入 | 已写入 §5 行为变化 |
| m6 | MINOR | `recover_interrupted_runs` 返回值改为「实际成功数」 | 调用方仅用于日志，风险低 |

---

## 6. M2 结论

| 项 | 判定 |
|---|---|
| Discovery 终态与事件单事务 | **PASS**（SQLite，失败注入 + 红/绿对照） |
| 提交后广播 | **PASS**（SQLite，广播失败注入 + caplog） |
| TestRun 终态原子性 | **PASS（代码复核 + 顺序回归）**；错误日志断言未覆盖，记 PARTIAL |
| 冲突/重复/并发收尾 | **PASS（进程内）/ PARTIAL（跨进程未验证）** |
| 最终全量套件（最终文件） | **1 failed / 910 passed / 12 skipped / exit 1**；失败为既有前端缺陷，非本轮回归 |
| PostgreSQL 16 | **BLOCKED** |
| 多进程验证 | **不属于 M2**，留待 M7 |

**M2 总体：PARTIAL**。SQLite 通道的原子性目标已达成并有红/绿证据；双库结论、跨进程守卫与前端既有缺陷使其不能判 PASS。最终质量门见 [09-final-acceptance.md](09-final-acceptance.md)。
