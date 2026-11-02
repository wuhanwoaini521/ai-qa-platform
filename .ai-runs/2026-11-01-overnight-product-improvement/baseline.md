# Baseline — 2026-11-01 overnight batch

Branch: `feat/overnight-product-improvement` (from `main` @ `3c6f33a`, 112 dirty entries preserved).
Services: API `http://127.0.0.1:8000`, Web `http://127.0.0.1:5183`.

## Verified baseline (re-run at start, not reused from history)

| Check | Result |
|---|---|
| Frontend tests | 234 passed, 0 failed |
| `pytest apps/api/tests/test_grounded_assertions.py` | 21 passed |
| `tsc --noEmit` / ESLint | pass |
| i18n | 3,509 keys |
| Vite build | pass (existing Monaco chunk warning) |

## Capability status at start

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | 项目 / 需求 / 验收标准 CRUD | DONE | `api/requirements.py`, lifecycle panel |
| 2 | Grounded 断言草稿 + 人工采纳 | DONE | `draft_assertions`, `set_assertion_adoption` |
| 3 | 断言 → 脚本生成（criterion 双向校验、禁自造页面） | DONE | `generate_assertion_script`, 21 tests |
| 4 | 脚本保存（比较并写、409 冲突） | DONE (backend) / PARTIAL (UI 提示未实测) | `write_file_if_unchanged`, `expected_exists` |
| 5 | 断言 ↔ 脚本 ↔ TestRun 关联 | **PARTIAL → DONE in this batch** | `RequirementDocument.scripts`, `/assertions/runs` |
| 6 | 断言最近一次真实运行状态 | **DONE in this batch** | 7-state resolver + panel badges |
| 7 | 流程条第 4 步真实状态 | **DONE in this batch** | `executedCount` from real executions |
| 8 | 失败 → Debug → 返回原上下文 | PARTIAL | `/runs/:runId` page exists; requirement back-link not wired |
| 9 | 409 冲突用户恢复路径 | NOT_IMPLEMENTED (UI) | backend returns 409; no UI recovery copy/actions |
| 10 | 运行记录不可访问 / 取消 / 阻塞文案 | **DONE in this batch** | `RECORD_INACCESSIBLE`, `BLOCKED`, `CANCELLED` |
| 11 | 录制回放与变量抽取 | NOT_IMPLEMENTED | recorder hardcodes literal values |
| 12 | 元素自愈与重定位 | DONE (existing) | locator intelligence + Jev + Playwright verify + apply/rollback |
| 13 | 可观察性 / 证据关联 | PARTIAL | 13 evidence kinds; trace timeline linkage missing |
| 14 | 探针项目数据隔离 | NOT_IMPLEMENTED (proposal only) | 5 probe projects pollute dashboard counts |
| 15 | 需求级 ACL | **DONE in this batch** | `requirement_id_access` on 5 assertion routes |

## Constraints honored

- No new Runtime / Agent / Provider / run-record store.
- No destructive data cleanup.
- No dependency added.
- Playwright stays 1.62.0.

## P0-C：探针数据（非破坏性处理）

新增只读工具 `apps/api/scripts/dev_probe_inventory.py`：列出探针项目及其 requirements / test_cases / runs，不删除任何数据。
运行结果（`probe-inventory.json`）：

| 项目 | requirements | runs |
|---|---|---|
| AI Live Probe 2026-10-31 | 1 | 0 |
| Grounded Assertion Demo | 1 | 0 |
| Assertion-to-Run Slice | 1 | 1 |
| Assertion to Run (final) | 2 | 3 |
| Frozen Slice Evidence | 4 | 4 |

非破坏性隔离方案（未执行，需授权）：
1. 先跑 `PYTHONPATH=apps/api uv run --no-sync python apps/api/scripts/dev_probe_inventory.py` 复核清单；
2. 通过既有项目管理界面逐个删除（可回滚点：先 `cp runtime/ai_qa_platform.db /tmp/aiqa-backup.db`）；
3. 若希望"保留数据但从统计隐藏"，需新增项目级 `hidden_from_overview` 字段 + 迁移——本轮未做（避免未审查的 schema 变更）。
