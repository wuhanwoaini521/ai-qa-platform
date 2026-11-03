# 04 — Functional test

Method: Python Playwright 1.62.0 (project-pinned) against the running local stack (`127.0.0.1:8000` API, `127.0.0.1:5173` Vite) with the seeded `Northstar · Golden Demo Shop` project (15 requirements, 108 cases, 3 independent cases, 1 requirement without cases). Scripts kept next to the evidence: `evidence/final-check.py`, `evidence/shots3.py`, `evidence/shots4.py`.

Re-runnable with `uv run python .ai-runs/2026-11-03-requirements-cases-management/evidence/final-check.py` while the dev servers are up.

## Results — PASS

| Check | Observed |
|---|---|
| Tabs, URL state | `tab` switches requirements / cases / traceability; `显示 15 / 15 条记录。` on load |
| Keyboard | ArrowRight ×2 → cases, traceability; wrap → requirements; ArrowLeft ×3 → traceability, cases, requirements (previously ArrowLeft moved forward) |
| Filter chip — relationship | `关联情况: 无关联用例的需求` → `显示 1 / 15 条记录。`, 1 row |
| Chip removal | Chip click clears only its own param; chip count 0 afterwards |
| Search chip | `搜索项目记录: 购物车` chip, 11 matching rows, no-match state reachable with `zzzz-nothing` |
| No-match state | `显示 0 / 15 条记录。` + one 清除筛选 button (no duplicate clear action) |
| Detail drawer | Opens from 详情, `role=dialog`, focus lands on the drawer, 3 facts, deep link `?detail=req_9c72a1dabe30` restores the same requirement |
| Drawer close | Backdrop click and Escape both close it and remove the param |
| Acceptance criteria edit | Save shows `验收标准已保存`; the saved text re-renders in the list; duplicate lines render without duplicate-key warnings; the test edit was restored to the original empty value afterwards |
| Link existing case | Drawer lists 3 unlinked project cases with the 关联 action |
| Header primary | 新建需求 on 需求/需求追踪, 新建用例 on 测试用例 |
| Console/runtime | 0 page errors, 0 console errors across the runs above |

## Not executed (in this read-only pass)

- Create-requirement / create-case submission, loading/load-failed states and link-case feedback were **not** exercised against the shared seeded project, because those need writes or forced failures.

## Closed later — see `10-closure.md`

All three gaps above were verified afterwards in an isolated API instance (`:8010`, `/tmp/aiqa-isolated/closure.db`)
with the seeded demo project untouched: `evidence/closure-check.py` → 46/46 PASS, including
`create_requirement_success`, `create_failure_shows_error`, `create_retry_after_failure`,
`load_failure_not_empty`, `load_retry_recovers`, `link_success_persisted`,
`link_failure_shows_error` and `link_failure_no_false_relation`.

## Data safety

The only write performed was the acceptance-criteria round-trip on `req_9c72a1dabe30`; it was restored to `acceptance_criteria: ''` with `qa_model.criteria: []` (matching sibling seeded requirements). One `qa_model.history` entry from that edit remains and is left in place as the honest audit record.
