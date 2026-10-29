# Bounded autonomous R&D workflow

- run-date: 2026-10-28
- task-type: maintenance
- scale: standard

## Changes so far

- Added project Pi adapters: `.pi/agents/technology-scout.md`, `knowledge-curator.md`, `architecture-critic.md`; durable package pin and safety defaults are in `.pi/settings.json`. `.pi/npm/package.json`, lockfile, and installed modules are ignored local install artifacts and are not intended for delivery.
- Added portable operating model and research skill; created `engineering-knowledge/` index, templates, P0 framework records, ADR/pattern/lesson/team definition/project link/experiment protocol.
- Added official-source P0 verification and independent debate records. Architecture Gate explicitly stays deferred; candidates remain uninstalled and unbenchmarked.
- Fixed Discovery recovery in `apps/api/app/services/quality_discovery_service.py` and repository status guard in `apps/api/app/repositories/quality_discovery_repo.py`; added two regressions in `apps/api/tests/test_discovery_task_runtime.py`.
- Updated root roadmap, architecture decisions/implementation roadmap/verification, team handbook/backlog/roadmap/decisions, and `docs/agent-handoff.md` with consistent PARTIAL/DEFERRED/NOT TESTED states.

## Decisions

- Reuse existing runtime owners and exact existing ORM optimistic concurrency; no new service, provider, runtime, schema or endpoint.
- Recovery pause event now commits alongside state update; live publications occur only after persistence success.
- No third-party candidate installation, real provider call, database install or paid call.
- No UI changes; desktop visual review is not applicable.

## Team/review milestones

- Real fresh-context Technology Scout, Architecture Critic, Knowledge Curator, QA Engineer, Code Reviewer, and Release Engineer child runs were used. Scout/Curator profile smoke checks confirmed instructions are available; the Critic supplied the independent challenge; QA and Reviewer results are recorded in handoff and their stage logs.
- Independent reviewer found no code findings (OK with notes); QA independently reran the focused SQLite suite. Release Engineer marked integration PARTIAL/not release-ready because PostgreSQL is blocked and remote preview/authorization remains pending.

## Commands executed

- `../ai-qa-platform/.venv/bin/python -m pytest apps/api/tests/test_discovery_task_runtime.py -q` from the isolated worktree — PASS, 15 passed in 3.39s; final parent rerun after review: 15 passed in 3.37s. Independent QA rerun: 15 passed in 3.40s.
- `../ai-qa-platform/.venv/bin/ruff check` on the three changed Python files — PASS.
- `../ai-qa-platform/.venv/bin/ruff format --check` on the three changed Python files — PASS, all 3 already formatted.
- `git diff --check` — PASS.
- Markdown relative-link validation: first pass found one incorrect link from `engineering-knowledge/projects/ai-qa-platform/README.md`; fixed to `../../patterns/conditional-recovery.md`; final run checked 46 relative links across 49 candidate docs, all targets exist.
- Pi settings JSON/profile check — valid JSON, exact `pi-subagents@0.82.1` pin and three new role files present; fresh Scout and Curator child smoke checks succeeded.
- Targeted credential-pattern heuristic — no matches across 64 changed/untracked non-ignored files; not a comprehensive secret scanner.
- `docker`, `psql`, `pg_isready`, `podman`, `postgres` availability check — none found; historical `/tmp/pgvenv`, `/tmp/pgdata-aiqa`, `/tmp/sock-aiqa` are absent.
- Python import/socket probe — `asyncpg` present in existing test env, psycopg/psycopg2 absent; `127.0.0.1:5432` and `127.0.0.1:55432` refused (connect_ex 61).
