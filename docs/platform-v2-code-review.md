# Platform V2 独立 Code Review

审查日期：2026-10-02。Reviewer 未参与业务实现；仅阅读代码、检查现有测试证据、执行 reducer 重现和隔离测试，并编写本报告。动态验证使用内存 SQLite 或 acceptance 目录中的独立临时 workspace，未修改业务代码或生产数据。审查时工作区已有大量未提交修改，未重置、覆盖或提交这些修改。

最终 Code Review 结论：**PASS。首次发现 1 项 P1、4 项 P2，开发 Agent 修复后，Reviewer 已逐项复核关闭。当前审查范围内没有未关闭的 P1/P2。此结论不等于整体 Acceptance 结果。**

## 范围与方法

阅读原始任务及 `docs/runtime-visualization-audit.md`，核对 Run Store、Task SSE、RuntimeProjection、EventNormalizer、六个 Runtime 视图、Inspector、Studio 内嵌 Runtime、Failure 业务摘要、Task 审批/写入、Provider fallback、Alembic 及关系回填。

所有下述行号是首次发现时的工作区行号；文件绝对路径以 `D:\code\self-github\ai-qa-platform` 为根。后续修复可能改变行号。

## 首次发现

### CR-01 · P1 · 审批期间编辑的源文件会被旧提案覆盖

- 位置：`D:\code\self-github\ai-qa-platform\apps\api\app\services\task_runtime_service.py:2082`，`_apply_repair`；同文件 `:1713` 的 `_write_generated` 也处理完整文件写入及 OPTIMIZE_TEST。
- 触发：任务读取源文件并生成提案，进入 WAITING_FOR_APPROVAL；用户在 Studio/Debugger 中修改同一文件，再批准提案。
- 影响：执行器直接 `write_file` 写入旧提案的完整 replacement，未比较当前文件与生成提案时的基线，会覆盖用户在等待审批期间的新修改。
- 建议：修复任务比较 `repair.old_code`，重构比较 `inspect.source`；新文件在审批期间已出现也应阻止覆盖。当前文件与提案基线不一致时进入 BLOCKED，由用户重新检查提案。
- 验证：增加实际临时 workspace 用例，在审批前修改文件，确认审批后的写入步骤 BLOCKED 且保留用户修改。

### CR-02 · P2 · ContextTaskProgress 为同一 Task 建立重复 SSE 并反复重连

- 位置：`D:\code\self-github\ai-qa-platform\apps\web\src\components\ContextTaskProgress.tsx:43`、`:75`；`D:\code\self-github\ai-qa-platform\apps\web\src\features\runtime\useRuntimeSnapshot.ts:55`。
- 触发：业务页面通过 `useContextTask` 显示 active Task，同时内嵌 `RuntimeDetail`。
- 影响：父 hook 和 Runtime 各调用一次 `streamTaskEvents`。父 hook 更新 `task.updated_at` 后，传给 Runtime 的 `revision` 又重建其 transport；重复连接增加数据库读取，并让运行中的连接反复断开。
- 建议：保留 Runtime 的唯一 Task SSE；父 hook 仅读取业务摘要，轮询需有取消和 in-flight 守卫。不要用每次变动的 `updated_at` 驱动 SSE effect 的依赖。
- 验证：检查唯一 Task SSE 调用点，浏览器中执行任务并观察请求数及状态切换，不因 Task 更新持续重连。

### CR-03 · P2 · 日志达到 20,000 字符后，运行中的最新输出冻结

- 位置：`D:\code\self-github\ai-qa-platform\apps\web\src\features\runs\runStore.ts:142` 的 `reconcileRun`；`D:\code\self-github\ai-qa-platform\apps\api\app\services\test_run_service.py:959` 的 `event_generator`。
- 触发：持久化日志使用最近 20,000 字符；达到上限后继续追加日志，snapshot 的长度不变但内容向前滚动。
- 影响：服务端仅用 `len(log) > sent_log` 发 LOG_STREAM，长度固定后不再发送；客户端把新 snapshot 作为 persisted、旧 state 作为 observed 合并，旧 state 会被拼在末尾，从而挤掉 snapshot 新尾部。运行结束的 authoritative snapshot 才恢复最新日志。
- 独立重现：真实 `reconcileRun` 输入 `first = 'a'.repeat(19994) + 'OLDEND'` 和 `next = first.slice(10) + 'LATESTLOG!'`，两者均长 20,000；更新后 `retainedLatest=false`，输出尾部仍为 `OLDEND`。
- 建议：服务端通过内容重叠或显式游标识别 ring log 新尾部；客户端在不存在更晚 SSE 日志时信任较新的 snapshot，同时保留晚返回 snapshot 的并发保护。
- 验证：真实运行输出超过 20,000 字符，在 RUNNING 时确认尾部持续更新；再测试断线、重连及较慢 snapshot 不覆盖新输出。

### CR-04 · P2 · 审批只显示 replacement 前缀，尾部变更不可审查

- 位置：`D:\code\self-github\ai-qa-platform\apps\api\app\services\task_runtime_service.py:1698`；`D:\code\self-github\ai-qa-platform\apps\web\src\features\runtime\RuntimeTaskActions.tsx:33`。
- 触发：修复一个超过 12,000 字符的测试模块，变更只在尾部。
- 影响：后端摘要截取 replacement 前 12,000 字符，前端显示该前缀并启用批准；页面没有实际 Diff、截断提示或对应完整变更入口，用户看到的内容可完全不含实际修改。
- 建议：利用真实 old/new source 生成 unified diff；新文件使用新增文件 diff。截断需明确提示并提供真实 PATCH_PROPOSAL artifact 全文，不把替换代码前缀称为完整 diff。
- 验证：超过 12,000 字符且只修改尾部的模块，应在审批页面显示对应 diff；较大 diff 应有截断提示及全文下载入口。

### CR-05 · P2 · 工作流列表逐 Task 查询步骤，形成 N+1

- 位置：`D:\code\self-github\ai-qa-platform\apps\api\app\services\task_runtime_service.py:270`；`D:\code\self-github\ai-qa-platform\apps\web\src\pages\TasksPage.tsx:76`。
- 触发：打开工作流执行列表，默认加载 50 个 Task，页面每 5 秒刷新。
- 影响：`list` 先读 Task，再在逐项构建 plan 时 `await repo.get_steps`；50 项至少需要 51 次 SELECT。此发现属于现有列表路径，RuntimeProjection 自身未确认到 N+1。
- 建议：一次查询全部 TaskStep，按 task_id 分组后保持既有响应契约。
- 验证：SQL query count 应不随返回 Task 数线性增长。

## 已核验的正面结论

- TestRun transport 已集中到 `useRunStore`；Runs、Studio、Runtime Browser/Results 使用共享 store，不再各自 switch SSE 事件。
- Store 包含引用计数、卸载清理、generation 守卫、pending 快照保护、终态收敛、未知事件忽略和 bounded trace/log/browser 数据；上述日志 ring 例外另列 CR-03。
- RuntimeProjection 仅执行 SELECT，Task 与 Step 读取检查 owner；关联使用正式 nullable 外键，legacy 匹配对歧义及超过搜索上限不猜测。独立 Run 保持既有共享访问语义，不把本轮未做 RBAC 改造认定为新缺陷。
- 投影查询批量聚合执行、Browser、Failure、Analysis 与 Artifact；Retry 祖先使用有深度上限的 CTE。
- Trace 排除 delta/content/reasoning 事件，metadata 白名单、敏感内容脱敏、单字段上限及非法耗时处理均已落实；事件缺失时间保留 unavailable。
- Timeline 对 derived 时间做显式标注；Flow 使用 TaskStep dependencies，未确认到 fake Agent、fake parallel 或 fake Browser event 的业务实现。
- Studio 已内嵌 RuntimeDetail；FailureWorkflowPanel 已保留业务摘要，未再实现第二套执行图或 Trace。
- Alembic 为 nullable relationship 添加索引及外键，SQLite 不重建 test_runs，从而避免对子表的级联删除；legacy 回填对 missing/conflict 留 NULL。
- 真实 Provider 的隐式 Fake fallback 已移除，显式 Fake Provider 仍用于测试/明确的模拟配置。

## 测试证据边界

独立读取 `runtime/platform-v2-acceptance/final-pytest.xml`：421 个收集用例，0 failures、0 errors、4 skipped，即 417 passed。`final-supplement-valid.xml`：4 项通过。未把更早因临时目录权限失败的 `baseline-pytest.xml`、`phase-b.xml` 或 `final-supplement.xml` 当作有效业务回归结果。

这些数字对应首次审查之前的测试记录。Reviewer 在修复后独立运行 Run Store 的 13 项测试和审批相关的 4 项后端测试，均通过；开发 Agent 后续完成修复后完整回归，Reviewer 已核读最终 XML 与日志，详见下节。浏览器 UI 与 10 分钟性能由各自专项验收负责；本报告不冒称重新运行了这些验收。

真实 AI/JEV 服务缺外部配置属于环境缺口，需在 Acceptance 记录，不作为代码缺陷，也不能把显式 Fake 结果计入真实 AI 验收。

## 修复复核

| Finding | 最终状态 | 独立复核 |
| --- | --- | --- |
| CR-01 · P1 | 已关闭 | `_write_generated`、`_apply_repair` 均调用 `_write_approved_source`。审批记录真实文件存在状态及 SHA-256；最终 `write_file_if_unchanged` 比较基线，冲突进入 BLOCKED，新文件使用 exclusive create。Reviewer 在独立临时目录实测未修改源允许写入、用户编辑保留、新文件冲突保留；再独立运行 repair/refactor/generate 三种任务的审批后修改测试，全部通过。 |
| CR-02 · P2 | 已关闭 | `useContextTask` 改为带 in-flight 与取消守卫的 3 秒业务摘要轮询；ContextTaskProgress 及 TasksPage 已删除 updated_at revision。`rg` 确认除了 API 定义外，前端只在 `useRuntimeSnapshot` 调用 Task SSE。 |
| CR-03 · P2 | 已关闭 | 服务端比较日志内容，发送有界的 `replace=True` snapshot；客户端 reducer 支持幂等替换，快照并发时保留更新的 live log。原有 20,000 字符重现现为 `retainedLatest=true`。新增等长 ring、重复 replacement 及较晚 live 内容保护测试通过；Run Store 共 13 项独立通过。后端 on_log 也改成单条 20,000 字符文本，消除无限 append list。 |
| CR-04 · P2 | 已关闭 | `_request_approval` 生成真实 unified diff，并把完整内容存为 PATCH_PROPOSAL Artifact；摘要记录 preview_truncated，前端显示截断提示和全文下载，缺 Diff/基线时禁用批准。超过 12,000 字符的尾部变更用例独立通过，完整 artifact 包含实际 old/new assertion。 |
| CR-05 · P2 | 已关闭 | Task 列表批量读取全部 TaskStep 后按 task_id 分组。Reviewer 创建 50 个内存 SQLite Task，监听当前真实 `TaskRuntimeService.list`：50 个 Task 仅产生 2 次 SELECT。 |

修复后后端独立测试命令：

```powershell
uv run --offline --no-sync pytest -q apps/api/tests/test_agent_tasks.py -k 'approval_preserves_source_modified_while_waiting or approval_diff_exposes_tail_and_keeps_complete_artifact' --basetemp=runtime/platform-v2-acceptance/pytest-independent-review -o cache_dir=runtime/platform-v2-acceptance/pytest-cache --junitxml=runtime/platform-v2-acceptance/independent-review.xml
```

结果：**4 passed，24 deselected**，15.34 秒。仅有 pytest cache 写入权限 warning，测试 fixture、断言及 XML 正常完成。证据：`runtime/platform-v2-acceptance/independent-review.xml`。

修复后前端独立测试命令：

```powershell
node --experimental-strip-types --test apps/web/tests/run-store.test.mjs
```

结果：**13 passed，0 failed**。原始 findings 保留用于审查追踪，不代表尚未解决。

## 修复后最终完整回归证据

开发 Agent 完成完整回归后，Reviewer 只读核验了以下最终产物，没有重复执行全量测试：

- `runtime/platform-v2-acceptance/accepted-full.xml`：427 个收集用例，0 failures、0 errors、4 skipped，即 **423 passed**；XML suite 时间 704.016 秒。
- `runtime/platform-v2-acceptance/accepted-full.log`：**423 passed，4 skipped**，704.14 秒。4 个跳过用例均明确要求 `AI_QA_TEST_DATABASE_URL` 指向 PostgreSQL，不能据此声称 PostgreSQL 集成已验证。
- `runtime/platform-v2-acceptance/frontend-reviewed-tests.log`：**58 passed，0 failed，0 skipped**。
- `runtime/platform-v2-acceptance/backend-reviewed-lint.log`：Ruff `All checks passed!`；`frontend-reviewed-lint.log` 与 `frontend-reviewed-typecheck.log` 未报告 ESLint 或 TypeScript 错误。
- `runtime/platform-v2-acceptance/build-final.log`：production build 成功，46.33 秒；Monaco 相关 chunk 仍有超过 500 kB 的体积提示，属于已有构建优化债务，不是构建失败。

Reviewer 同时检查最后调整的 `apps/api/tests/test_ai_execution_trace.py` 差异：当 provider 只完成 discovery、未给出可用 streamed model response 时，旧 `FALLBACK_ONLY/fallback_active=True` 断言改为 `UNAVAILABLE/status=UNAVAILABLE/fallback_active=False`。这与已审查的“真实 provider 失败不隐式使用 Fake”行为一致，没有用降低真实验收标准来掩盖业务失败。

最终 Code Review **PASS** 结论保持；真实外部 AI/JEV 配置和 PostgreSQL 集成验收边界仍需保留在整体 Acceptance 中。
