# Validation Plan — Night Final Acceptance

1. Preserve the inherited dirty worktree and verify this run's branch/index/status baseline.
2. Check actual architecture/contracts and safe environment configuration; query current service/readiness/provider health without exposing secrets.
3. Run official Python/backend, web, lint/format/i18n/build, OpenAPI export/type-parity, and Quickstart suites on the current worktree. Run focused lifecycle/cancel/timeout/reconnect and debugger tests.
4. Run opt-in real AI + Jev acceptance with configured real providers and no fallback. Exercise UI/browser acceptance at desktop/tablet/mobile sizes. Never click Apply or invoke a repair source write.
5. Verify available local browser/runtime/Debugger and test execution; inspect pending tasks/resources and preserve unrelated processes/data. Mark PostgreSQL and remote Worker lanes honestly if unavailable.
6. Review all changed code and its connected callers/tests. Attempt only the established Orca independent-review path; self-review is not independent.
7. Repair only confirmed defects within scope, then rerun affected and complete regression checks.
8. Produce all seven requested reports/evidence, inspect `git status`, explicitly stage only verified scoped changes, classify commits, and push only `agent/night-final-acceptance` if credentials/remote permit. Leave inherited unrelated modifications untouched.

## Planned coverage matrix

| Area | Evidence to collect | Gate |
|---|---|---|
| Runtime/API | live/ready health, auth, DB/storage, task/worker state | PASS only for observed current state |
| Backend/full regression | repository CI-equivalent Python suite and focused lifecycle tests | PASS on zero failures |
| Frontend | tests, typecheck, lint, build, i18n, responsive browser QA | PASS on zero failures; retain existing advisories |
| Contracts | OpenAPI export check, API contract tests, generated TS type parity | PASS on exact current output |
| Database | SQLite run plus PostgreSQL-specific lane | SQLite cannot substitute for PostgreSQL |
| AI + Jev | live provider status and real acceptance; record provider/model/fallback without secrets | Must be real; no mocks or fallback |
| Execution/debugger | execute a real selected test, inspect result/evidence, open/close debugger session | isolate test fixtures and leave sources unchanged |
| Human approval | reach proposal and show available actions | Apply remains blocked pending explicit human approval |
| Independent review | Orca reviewer output | BLOCKED if Orca unavailable; do not relabel self-review |
| Git | exact status, explicit staging, scoped commits, task-branch push | preserve `mise.toml` and inherited unrelated state |

## Execution status

- Complete: preserved the inherited baseline; ran repository tests, lint, contracts, Quickstart, live provider probes, isolated browser/debugger journey, and responsive checks; recorded evidence and all seven requested reports.
- Complete: stopped only this run's disposable processes and removed its temporary DB/workspace/artifacts. Existing API/Vite services remained healthy.
- No product repair was applied. The disabled-provider 500 was recorded as a follow-up; live provider flow passed and stopped before Apply.
- Blocked: independent Orca review, PostgreSQL, Windows/Linux, separate remote Worker, and human approval/post-approval verification.
- Git: inherited changes remain unstaged and untouched. Stage only `.ai-runs/night-final-acceptance/`; never stage `mise.toml` or earlier-round records. Commit/push outcome is pending final scoped staging and remote verification.
