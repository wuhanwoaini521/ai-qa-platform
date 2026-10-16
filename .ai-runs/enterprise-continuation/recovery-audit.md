# Recovery Audit — previous agent's progress

Objective: recover the previous agent's development state from `d8a2eef`, decide what is actually
finished, and re-derive the test baseline on WSL instead of trusting the written report.

## 1. What was recovered

| Source | Status |
|---|---|
| Git history | intact — `d8a2eef` is HEAD, `main` == `origin/main` |
| Commit message of `d8a2eef` | full change description available (71 files, +3474 / −1019) |
| `.ai-runs/` (33 run dirs, 593 tracked files) | intact, including `night-final-acceptance`, `night-round-*`, `refactor-audit` |
| `.ai-runs/enterprise-platform-upgrade/logs/backend-final.log` | **MISSING** — referenced by the `d8a2eef` commit message but never written or never committed |
| Working tree at handoff | clean apart from the incoming agent's `AGENTS.md` edit |
| Windows copy holding the missing logs | **none** — no Windows checkout exists on this machine |

### Recovery finding R1 — the previous agent's final regression log is gone

The `d8a2eef` commit message states: *"The final full backend regression re-run was still executing and must
be read from `.ai-runs/enterprise-platform-upgrade/logs/backend-final.log`."* That path does not exist on
disk or in Git. The previous agent also wrote (in the handoff prose):

> 最近一次完整后端测试：817 passed / 2 failed / 9 skipped。两项失败随后修复，但没有完成最终提交上的完整回归确认。

So the previous agent committed a fix for two failures and **never re-ran the full suite on the final
commit**. Recovery therefore required re-running it, which is exactly what this audit did.

### Recovery finding R2 — the two reported failures were already fixed and now pass

Re-run on `d8a2eef` in WSL: **819 passed, 9 skipped, 0 failed** (588.76 s), i.e. the 817+2 split is now
819+0 with the same 9 skips. One of the two previously-failing tests was `test_agent_tasks.py::test_browser_agent_completes_second_ecommerce_journey_on_demo_shop`,
which failed here only because Playwright's Chromium had not been installed on the fresh Linux box; after
`playwright install chromium` it passes. The other failure was not reproducible.

### Recovery finding R3 — claims vs evidence

Everything the previous agent claimed to have implemented is present in the tree and is exercised by tests
that now pass, but several claims had **no independent re-verification**. Status per claim:

| Claimed by previous agent | Present in code | Independently re-verified on WSL |
|---|---|---|
| Run↔workspace ownership + workspace-bounded pytest nodeids | yes (`test_runs_and_failures.py`, `test_runner_failure_isolation.py`) | **yes** — full suite green |
| `security:admin` required for worker/job infrastructure writes | yes (`apps/api/app/api/authz.py`, `jobs.py`, `test_authorization_rbac.py`) | **yes** — full suite green |
| Browser telemetry/evidence scoped to run + nodeid | yes (`browser_session_repo.py`, `test_debug_session_service.py`) | **yes** — full suite green |
| Coverage from active bindings + terminal executions only | yes (`quality_intelligence_service.py`, `test_quality_and_releases.py`) | **yes** — full suite green |
| Failure risk data scoped to project | yes (`test_quality_risk_scoring.py`) | **yes** — full suite green |
| Credential scrubbing from project subprocess env | yes (`pytest_runner.py`, `test_project_pilot.py`) | **yes** — full suite green |
| OpenAPI schema + web types regenerated, freshness in CI/lint | yes — `scripts/export_openapi.py --check` passes, `task.py lint` enforces it | **yes** |
| Knowledge / scenario / mind graph UI default focus, search, fit | yes — `KnowledgeGraph.tsx`, `graphModel.ts`, `tests/lifecycle.test.mjs` | **partially** — unit-tested; live browser pass still outstanding |
| Workspace run result: single repair action, evidence tabs, inline screenshots | yes — `WorkspaceRunResult.tsx`, `workspace.css` | **partially** — unit-tested; live browser pass still outstanding |
| Quality discovery explicit site/project scope | yes — `QualityDiscoveryPanel.tsx`, `qualityDiscoveryMap.ts` | **partially** — unit-tested; live browser pass still outstanding |
| Real AI + Jev acceptance | tests exist (`test_live_enterprise_journey.py`, `test_live_locator_repair_acceptance.py`) | not re-run at the time of writing — see `test-results.md` |

### Not completed by the previous agent (carried forward)

1. A confirmed full regression on the final commit — **now closed by this audit** (819 passed / 0 failed).
2. PostgreSQL lane — still **BLOCKED** (no docker/psql on this host).
3. Worker / Jenkins real-cluster execution — still **NOT RUN**.
4. Requirement → Coverage chain and Site Discovery chain independent re-verification — **open**.
5. Final live-browser acceptance of the Graph / Studio / Result / Discovery UI — **open**.

## 2. Process defect this audit fixes

The previous agent lost its last evidence because raw logs lived only in an untracked, undocumented
directory. Mitigation applied: `docs/agent-handoff.md` is now a committed, version-controlled handoff,
and every milestone in `.ai-runs/enterprise-continuation/` is written to Markdown (not just logs), so a
future agent can always reconstruct state from Git alone.
