# Final handoff — overnight product improvement batch

Branch: `feat/overnight-product-improvement` (local only; no push).
Base: `main` @ `3c6f33a`. HEAD at handoff: `d148d7e`.

## What is now true that was not before

1. 断言卡显示该断言对应测试函数的真实执行状态（7 态 + 未采纳），不是文件级近似。
2. 断言与测试的关联边由代码里的 `# criterion:` 标记按**函数粒度**决定，客户端伪造会被 422。
3. 流程条第 3/4 步由持久化脚本与真实执行驱动；未采纳/运行中不再算完成。
4. 保存脚本是「比较并写 + 绑定」的原子动作；同内容幂等、不同内容 409、持久化失败回删文件。
5. 从运行结果页可回到需求上下文（run 链接保留 requirementId；工作区头部「返回需求」）。
6. 409 冲突给可执行恢复路径，不再显示原始错误。
7. 录制生成的脚本把非敏感输入变成 `QA_DATA_*` / `QA_BASE_URL` 环境变量，脱敏值继续走必需 env。
8. 只读探针清单工具，让开发库清理变成「先看清单再删」。

## Commits (oldest → newest)

| Commit | 内容 |
|---|---|
| `cd3743b` | 断言 ↔ TestRun 关联、7 态、绑定由 marker 决定、ACL、page fixture |
| `89bcf42` | requirementId 透传、返回需求、409 文案 |
| `1e636f8` | 录制变量抽取与生成 |
| `41389eb` | 只读探针清单 |
| `053fb41` | 补提交被引用的本地模块（redactor / recorder 模型 / websocket 测试） |
| `afabbd7` | 补提交此前本地源码与文档，使 HEAD 可构建 |
| `0332aed` | 断言级 nodeid 配对、白名单、原子性、本地化、变量安全、429/503 |
| `f68af99` | 无执行记录时用 run 级终态（BLOCKED / CANCELLED / RECORD_INACCESSIBLE / RUNNING） |
| `f32c810` | 断言行布局修复 |
| `d148d7e` | 关闭配对旁路（marker 必须在 test 函数内）、执行状态本地化、断言作废路径 |

## Verification (actually executed)

- 干净检出 `/tmp/final-check`（HEAD `d148d7e`）：`import app.main` OK、**87 passed**、`tsc --noEmit` 通过。
- 早期干净检出（`f68af99`）：37 passed，用于定位提交不自洽问题。
- 广泛回归（工作区）：`527 passed, 7 skipped`（含此前 2 个失败已修复）。
- 前端：234 passed、`tsc`、ESLint 通过；i18n 3,517 keys；`vite build` 通过。
- Ruff：`ruff check` / `format --check` 在提交状态全绿。
- 真实浏览器：断言状态徽标 + 查看运行结果 + 返回需求 + 409 文案；三视口登录后截图。

## Remaining / known limits

1. 断言↔执行仍是「测试函数级」而非「用例级」；同函数多断言只能共同状态。
2. `RECORD_INACCESSIBLE` 依赖 run 的 `nodeids`；Jenkins 若不带 nodeids 仍可能显示 NEVER_RUN。
3. 录制变量只在单元/契约层验证，未跑真实录制会话端到端。
4. 探针数据未删除（清单 + 方案已给）。
5. 项目级 SUT 地址、失败→修复→重跑的完整闭环仍是产品 P0（未在本批次）。
6. 回滚到 `1a51bfe` 及更早的代码前，需清理需求文档里的 `scripts` 字段（新模型 `extra="forbid"` 会使旧代码读取 500）。
7. `>10` 个 test 函数仍返回 422（已回滚文件，无孤儿），如需支持需把绑定上限提高。
6. 工作区仍有大量历史未跟踪产物（`.ai-runs/*`、设计与证据预览），未清理。

## Recovery

```
git checkout feat/overnight-product-improvement
cd apps/api && uv run --no-sync uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
cd apps/web && VITE_DEV_API_TARGET=http://127.0.0.1:8000 node node_modules/vite/bin/vite.js --port 5183
git revert --no-edit <commit>   # 任一变更有问题时可单独回滚
```

## Independent verdicts

- **QA（rev2，锚点 `f68af99`）**：PASS，P0=0，P1=0，建议 Release；边界：未重跑全量后端、未做 live provider。
- **Critical Review（rev2，锚点 `f68af99`）**：APPROVE WITH FIXES，P0=0；条件（R-P1-2 假通过旁路）已在 `d148d7e` 修复并新增测试；R-P1-1 本地化、R-P1-3 PII 死路同批修复。
