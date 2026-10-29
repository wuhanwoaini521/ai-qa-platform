# Bounded Autonomous R&D — continuation evidence (2026-10-28)

- **Status:** PARTIAL; Architecture Gate **DEFERRED / NOT PASSED**.
- **Scope:** Continue the authorized R&D mission in the isolated worktree; add bounded PostgreSQL/Worker evidence, test cross-agent knowledge reuse, update workflow/roadmap/handoff records, and prepare a preview-first development-branch/Draft PR delivery. No framework adoption, production write, merge, deployment, or duplicate runtime was authorized.

## Worktree and process boundary

- Mission worktree: `/Users/hans/Code/github/ai-qa-platform-autonomous-rd`, branch `agent/autonomous-rd-2026-10-28`, HEAD `245c00cacd946c8dea59991807af6b873fcdaf1d` (no mission commit yet).
- The original `/Users/hans/Code/github/ai-qa-platform` tree is heavily dirty. Early test invocations briefly used its CWD before the mismatch was noticed; no source edit in this continuation targeted it. All final backend and Node evidence cited below was rerun from the isolated mission worktree. The API harness defaults to per-test SQLite; explicit PostgreSQL runs pointed only at the disposable test database. The original tree must remain untouched by cleanup or delivery operations.
- User authorization covers only a normal push to `agent/autonomous-rd-2026-10-28` and creation of a **Draft** PR against `main`, subject to exact-file, remote-state, and external-write preview. No push/PR/merge/deploy has occurred.

## Disposable PostgreSQL 18.6

- Server: PostgreSQL **18.6** via `embedded-postgres==18.6.3`, installed only in `/tmp/aiqa-rd-postgres-20261028-venv`; data/socket under `/tmp/aiqa-rd-postgres-20261028`; loopback-only `127.0.0.1:55432`; disposable database `aiqa_test`.
- The live version was checked with `psql ... -Atc 'SHOW server_version'`; `pg_ctl status` confirmed the server process listens only on `127.0.0.1`. The existing test fixture drops/recreates `public`, so the database was created for this test run, not shared/valuable data. No system service, project dependency, or lockfile changed.
- Exact focused tests from the mission worktree:
  - `../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_discovery_task_runtime.py -q` — **15 passed** on per-test SQLite (5.92s).
  - `AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test ../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_discovery_task_runtime.py -q` — **15 passed** on PostgreSQL 18.6 (6.61s).
  - `../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_worker_process_integration.py -q` — post-fix **5 passed, 3 warnings in 60.20s** on SQLite.
  - `AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/aiqa_test ../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_worker_process_integration.py -q` — post-fix **5 passed in 57.86s** on PostgreSQL 18.6.
  - Reviewer found the initial eventual-ID assertion insufficient to prove simultaneous ownership. The fixed focused `test_concurrent_worker_processes_claim_distinct_jobs` selection requires both Worker IDs among `ASSIGNED`/`RUNNING` jobs in the same poll snapshot; it passed on SQLite (**1 passed, 4 deselected, 21.60s**) and PostgreSQL 18.6 (**1 passed, 4 deselected, 19.81s**). Fresh follow-up Reviewer confirmed P2 **CLOSED**, found no new issue, and returned **OK** (reviewer did not run tests).
  - Additional focused `test_quality_discovery.py` concurrent-write/restart cases — **2 passed**; `test_job_reliability.py` — **4 passed**. The retained summary does not preserve each selection's database target, so these counts are not treated as additional PostgreSQL proof. Cancellation/late-result selections were run on SQLite and PostgreSQL, but one PostgreSQL output was truncated; no aggregate is claimed.
- These tests prove only the exercised paths. They do not establish production PostgreSQL 16 compatibility, multiple API-process Recovery ownership, a durable lease/fencing generation, or full Sprint A–C acceptance.
- At initial report creation the PostgreSQL process was still running. After the final tests, it was stopped and only the verified run-owned data, dedicated venv, and scratch script were removed:

```bash
/private/tmp/aiqa-rd-postgres-20261028-venv/lib/python3.13/site-packages/embedded_postgres/pginstall/bin/pg_ctl \
  -D /tmp/aiqa-rd-postgres-20261028/pgdata -m fast -w stop
rm -rf /tmp/aiqa-rd-postgres-20261028 /tmp/aiqa-rd-postgres-20261028-venv
rm -f /tmp/aiqa-rd-kb-reuse-20261028.py
```

- Cleanup outcome: `pg_ctl` reported `server stopped` / `no server running`; `127.0.0.1:55432` returned `connect_ex=61`; both exact temporary directories and the scratch script were confirmed absent. The cleanup command exited 0. No other `/tmp` paths were removed.

## Worker, frontend, and knowledge evidence

- `apps/api/tests/test_worker_process_integration.py` now covers two real concurrent Worker subprocesses, distinct job claims, crash recovery, cancellation, timeout, and rejection of late results after cancellation without mutating the cancelled run or creating extra executions. Ruff check/format and a code diff whitespace check passed for the changed Python test/code files before the latest documentation-only edits.
- With Node `v24.21.0`, `node --test apps/web/tests/runtime-model.test.mjs apps/web/tests/workspace-run-dock-model.test.mjs` — **17 passed**. No frontend source changed; full Web and desktop/browser acceptance are not implied.
- Cross-agent reuse used a bounded `/tmp/aiqa-rd-kb-reuse-20261028.py` experiment against the exact SQLAlchemy **2.0.54** resolved in `uv.lock`, using in-memory SQLite: stale ORM flush raised `StaleDataError`; a bare bulk `UPDATE` bypassed the ORM version guard; an explicit version predicate rejected a stale bulk update. Scout source-check, Curator record/index update, and an independent backend consumer experiment are recorded in `engineering-knowledge/patterns/conditional-recovery.md` and `engineering-knowledge/index.md`. Status remains **EXPERIMENTAL**; this does not prove platform-wide concurrency guarantees.
- Updated `.pi/team/QUALITY_GATES.md`, `.pi/team/OPERATING_MODEL.md`, `.pi/skills/team-delivery/SKILL.md`, `.pi/team/DECISIONS.md` (EORG-010), mission backlog/roadmaps, and `docs/agent-handoff.md`. Guidance now requires considering a safe pinned temporary environment before declaring a gate blocked and documenting exact-file/remote/write previews before authorized Draft PR delivery. No second GitHub skill or agent runtime was added.
- Normalized 12 Markdown hard-break trailing spaces to explicit `<br>` tags in seven untracked architecture-review evidence files so the final staged diff can pass whitespace checks without losing line breaks.

## Current mission status

| Workstream | Status | Boundary |
|---|---|---|
| Sprint A — lifecycle | PARTIAL | Focused Discovery/Task recovery cases pass; full state matrix/API-wide semantics remain incomplete. |
| Sprint B — events/evidence | PARTIAL | Recovery status/pause-event transaction is tested; no general contract or cross-process order guarantee. |
| Sprint C — Worker reliability | PARTIAL | Focused crash/cancel/timeout/concurrent-worker tests pass; no general lease/fencing/reassignment proof. |
| Sprint D — frontend consistency | PARTIAL | 17 focused runtime/workspace model tests pass; no UI change or full Web/desktop acceptance. |
| Sprint E — browser-agent comparison | BLOCKED / NOT RUN | No local model endpoint or explicit provider cap; Browser Use/Skyvern remain uninstalled, and legal/compatibility review is incomplete. |
| Architecture Gate | DEFERRED / NOT PASSED | No adoption decision; retain existing Task Runtime, BrowserRuntime, DecisionService, Provider, and Worker boundaries. |

Full repository/API suites, Web lint/typecheck/build, browser/desktop acceptance, candidate POC, paid provider use, legal review, and comprehensive secret scanning were not rerun in this mission continuation. Historical project-wide results elsewhere in the handoff are separate evidence.

## Read-only GitHub preflight (2026-10-28)

- `git ls-remote --heads origin main agent/autonomous-rd-2026-10-28` returned only `main` at `245c00cacd946c8dea59991807af6b873fcdaf1d`; the remote mission branch does not exist yet.
- `gh repo view`: `wuhanwoaini521/ai-qa-platform`, **PUBLIC**, default branch `main`.
- `gh pr list --head agent/autonomous-rd-2026-10-28 --state all`: no existing PR.
- GitHub API reports `main` is not protected (protection endpoint returns 404); no branch-protection required-check list is configured. CI workflow results still need to run on the eventual PR.
- Local branch has no upstream and no mission commit. The refreshed 67-path stage matches the allowlist; no unstaged or untracked files remain. Follow-up Code Review is **OK** with P2 closed. Release Engineer verdict is **PARTIAL / not release-ready for merge**: exact scope and staged whitespace passed, but its review did not rerun tests and the credential/data scan is not comprehensive. Parent separately checked the public repo, default branch, branch protection and PR state. No GitHub write was issued.

## Final local checks before staging

- `../ai-qa-platform/.venv/bin/ruff check` and `ruff format --check` on the four modified API/service/test Python files — **PASS**; 4 files already formatted.
- `git diff --check` — **PASS** for the tracked diff.
- Additional bounded scan of all **67** current changed/untracked non-ignored paths: **61 Markdown files**, **46** relative links checked / 0 missing targets, 0 trailing-whitespace lines, and 0 matches for credential-pattern heuristics.
- `.pi/settings.json` parsed as JSON; it retains exact `npm:pi-subagents@0.82.1`, foreground-only mode, and disabled autonomous/preflight features. The new and existing Pi role profiles are present.
- No `gitleaks`, `trufflehog`, or `detect-secrets` executable was available; pattern checks are **not** a comprehensive secret scan. After refreshing staging, all 67 paths matched the allowlist and `git diff --cached --check` passed.
- The 12 earlier Markdown hard-break trailing spaces were converted to explicit `<br>` tags; rendered line breaks are preserved.
