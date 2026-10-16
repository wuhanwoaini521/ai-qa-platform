# Round 2 · Studio 调试能力真实浏览器验收

日期：2026-05（WSL Ubuntu 22.04，Python 3.13，Playwright 1.62.0 bundled Chromium，headless 1680×1050）
被测：`runtime/workspaces/proj_golden_shop_v1`（真实 golden demo 项目，非静态假数据）
入口：`http://127.0.0.1:5173/projects/proj_golden_shop_v1/studio/file/<path>` → 归一化为
`/workspace/proj_golden_shop_v1?...&view=code&file=<path>`

## 结果

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 打开 Python 测试文件（真实浏览器） | PASS | 脚本 1 第 1 项 |
| gutter 点击设置断点并渲染 `qa-breakpoint-glyph` | PASS | `glyph=1 line=10` |
| 启动 Debug 并**真实命中断点** | PASS | 面板 `已暂停` |
| 调用栈可见 | PASS | `frames=33` |
| 局部变量可见 | PASS | LOCALS 非空 |
| 当前执行行高亮 `qa-debug-execution-line` | PASS | count=1 |
| 断点绑定标记「已命中」 | PASS | 面板文本 |
| Step Over / Step Into / Step Out | PASS | 逐项 |
| Continue 恢复运行 / Pause / Continue 至结束 | PASS | `运行中` → `已暂停` → `已结束` |
| 结束后 debugpy adapter 进程清理 | PASS | `adapter before=0 leaked=0`（轮询等待，非单次采样） |
| 可重复调试（第二次会话再次命中） | PASS | 面板 `已暂停` |
| Stop 结束会话并清理 | PASS | `adapter=0` |
| 失败场景：在故意失败用例中断点命中 | PASS | `tests/test_known_locator.py:12`，栈帧 `test_known_locator_change:12` |
| 失败场景：Continue 后运行结束 | PASS | `已结束` |
| 失败场景：Python 异常定位到源码位置 | PASS | 调试控制台含 `add_with_legacy_locator` 与 `test_known_locator.py:12` |
| 连续点击 Debug 只创建一个会话 | PASS | `debug_sessions` 计数 `created=1`，adapter ≤ 1 |
| 未保存修改后 Debug 会先保存文件 | PASS | 未保存缓冲区已落盘（磁盘内容含探针） |
| 无浏览器控制台错误 / 无 HTTP ≥ 400 | PASS | `[]` |

脚本：`/tmp/studio_debug_accept.py`（17 项）、`/tmp/studio_debug_failure_accept.py`（14 项），
日志 `.ai-runs/enterprise-continuation/round-2/logs/studio-debug-accept.log`、`studio-debug-failure-accept.log`（日志按仓库规则不入库）。
截图：`screenshots/studio-debug-paused.png`、`studio-debug-second-run.png`、`studio-debug-failure-paused.png`、`studio-debug-failure-finished.png`。

## 本轮发现并修复的缺陷

### D6（P2）`DELETE /api/debug/sessions/{id}` 在会话已被适配器关闭时返回 404

- 现象：前端在 DAP `terminated` 事件后 250 ms 调用 `closeDebugSession()`，服务端因会话已 `closed_at` 而返回 404，
  浏览器控制台出现 `Failed to load resource: the server responded with a status of 404 (Not Found)`。
- 根因：`apps/api/app/api/debugger.py` 的 DELETE 把「已经关闭」当成「不存在」。
- 修复：DELETE 改为幂等——`closed = await debug_session_service.close(...)`；
  仅当 `not closed` 且 `get_record(...) is None` 时才 404，否则返回 `{"closed": false}`。
  未知或他人会话仍然 404。
- 回归测试：`apps/api/tests/test_debug_session_service.py::test_debug_close_is_idempotent_for_already_closed_sessions`
  （该文件 7 → 8 tests，`8 passed in 28.49s`）。

### D7（P1）Studio 深链 `.../studio/file/<path>` 会静默打开**另一个**文件

- 现象：请求 `/projects/proj_golden_shop_v1/studio/file/tests/test_known_locator.py`，
  URL 最终变为 `...&file=tests%2Ftest_shop.py`，编辑器与调试目标都变成 `tests/test_shop.py`。
  用户以为在给 A 文件设断点，实际断点、编辑与调试都落在 B 文件上。
- 根因（两处，均会覆盖「链接里点名要的文件」）：
  1. `apps/web/src/features/workspace/WorkspacePage.tsx` 的上下文归一化在数据加载后
     `file: preserveFailureDebugContext ? context.file : nextCase?.binding?.file_path`
     ——用「第一条绑定用例的文件」覆盖 URL 里显式的 `file=`；
  2. 同文件 `initialOpenFilePath={... view === 'debug' || !selectedCase ? context.file ?? automationFilePath : automationFilePath}`
     ——只要选中了用例就优先用绑定文件，忽略 `context.file`。
- 修复：
  1. `apps/web/src/app/workspaceContext.ts` 新增纯函数
     `resolveCanonicalFile(context, boundFilePath)`：显式 `file` 优先，其次失败调试上下文，最后回退绑定文件；
  2. `WorkspacePage.tsx` 归一化改用 `resolveCanonicalFile(context, nextCase?.binding?.file_path)`；
  3. `initialOpenFilePath` 改为 `context.file ?? automationFilePath`（URL 仍是事实来源，与代码注释一致）。
- 回归测试：`apps/web/tests/workspace-context.test.mjs` 新增 3 个用例
  （深链文件优先 / 未点名文件时回退绑定文件 / 失败调试链接保留自身文件），
  该文件 6 → 9 tests，前端整体 **160 passed**，typecheck、eslint 均通过。
- 真实浏览器复验：URL 保留 `file=tests%2Ftest_known_locator.py`，断点落在
  `tests/test_known_locator.py:12`，栈帧 `test_known_locator_change:12`（见上表）。

## 误报与教训（避免下一轮重复排查）

- **D5 误报**：adapter 进程泄漏曾是误报。`_stop_process()` 会先等
  `shutdown_grace_timeout_seconds=3` 再等 `shutdown_force_timeout_seconds=2` 才 kill，
  单次采样必然看到残留。验收脚本必须**轮询**等待进程消失（`wait_for_no_adapters(timeout=20s)`）。
- **Playwright 输入教训**：`page.keyboard.type()` 逐键输入会与 Monaco 的异步 model 更新竞争并丢字符
  （实测 `# probe-save-check` 落盘为 `#poesechek`，一度被误判为「保存按钮失效」）。
  断言编辑器内容时必须用 `page.keyboard.insert_text()`。
- **编辑 `apps/api/app/api/debugger.py` 会触发 uvicorn `--reload` 重启 API**，
  而 debugger 子进程用 `start_new_session=True` 启动，重启会留下孤儿 adapter。验收前后都要清理。
