# Next sprint — traceability & real-path verification (2026-11-01)

Base: `feat/next-sprint-traceability` (from overnight branch `d148d7e`).

## Scope and status

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | 用例级断言映射 | **DONE** | `ModernTestModel.assertions`; nodeid derived from requirement script pairings at read time (`GET /test-cases/{id}/assertions`); case detail panel; 2 tests |
| 2 | 项目级 SUT 地址 + 运行身份 | **DONE** | `projects.sut_base_url`; recorder defaults to it; `test_runs`/`failure_records` carry `requirement_id`/`case_id`; run-result route restores context from the row; workspace run creation sends both ids; migration 0016 reversible (verified upgrade→downgrade→upgrade on a DB copy) |
| 3 | 失败 → 修复 → 重跑闭环留证 | **NOT DONE** | Existing locator repair chain is unchanged; producing a genuine `LOCATOR_CHANGED` failure requires mutating a target app's DOM, which this batch did not do. No claim made. |
| 4 | 探针数据隔离 | **DONE** | `hidden_from_overview` + per-row toggle + management list still shows them; live check: hidden project absent from `/dashboard/stats`, present in `/projects`; no data deleted |
| 5 | 真实录制会话 E2E | **DONE** | Real recorder session (browser launched, SUT default `http://127.0.0.1:5183`), generate → `QA_BASE_URL` variable, save-case binding, file written, run **PASSED** (`evidence/recorder-e2e.json`) |

## Fixed on the way (real defects found by the E2E)

1. Failure persistence crashed with a SQLAlchemy async lazy-load error because the run row was read
   after commit expiry; identity is now fetched inside the active session.
2. `project_subprocess_environment` dropped `QA_RECORDER_SECRET_*` (name matches the credential
   filter), so any recorded sensitive step could never run. Those explicitly named per-run secrets are
   now forwarded; ambient credentials remain filtered.

## Verification

- `pytest apps/api/tests/test_project_sut_and_identity.py test_case_assertions.py test_assertion_runs.py` → **22 passed**
- `pytest packages/qa-core/tests/test_sensitive_redaction.py` → **10 passed**
- `ruff check` / `format --check` → clean
- Frontend: 234 passed, `tsc`, ESLint, i18n 3,535 keys
- Migration on a DB copy: columns added, downgraded, re-added
- Live: recorder E2E PASSED; hidden-project statistic check

## Notes / limits

- Case assertions are derived from requirement scripts, so a case with no adopted requirement assertion shows no rows (by design).
- `requirement_id`/`case_id` on runs are nullable and SET NULL on delete.
- Item 3 needs a controlled broken-locator fixture; recommended next.
