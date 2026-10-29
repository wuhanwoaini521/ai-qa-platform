# Bounded autonomous R&D workflow

- run-date: 2026-10-28
- task-type: maintenance
- scale: standard

## Current architecture and findings

- Root `AGENTS.md`, `docs/ROADMAP.md` §0, `.pi/team/*`, project-delivery workflow, existing Pi profiles/settings, APIs, execution services, persistence models, tests, and architecture-review docs were inspected.
- Existing owners remain `TaskRuntimeService`, `BrowserRuntime`, `DecisionService`, provider registry and deterministic Pytest. `QualityDiscoveryRunORM` already has SQLAlchemy optimistic `version_id_col` behavior.
- Existing project already pins `pi-subagents@0.82.1`; Pi settings default async/background/mission/schedule features off. Three missing logical roles were added as adapters, with generic role authority in `engineering-knowledge/team-definition.md`.
- P0 metadata found at official tags: LangGraph 1.2.18/MIT, Browser Use 0.13.14/MIT, Skyvern v1.0.56/AGPL-3.0. No candidate dependencies installed/run. Skyvern manifest FastAPI `<0.137` conflicts with project-resolved 0.141.1. Browser Use's manifest does not establish Playwright compatibility.
- Independent architecture challenge preferred retaining current owners and deferring Candidate B until comparative PostgreSQL, lifecycle and legal evidence. One debate round only; gate stays DEFERRED / NOT PASSED.
- Reproduced Discovery startup recovery race: an initially nonterminal row could become terminal after scan and be overwritten PAUSED; state update and pause event were separate commits/publications.
- Local fix uses exact scanned-status precondition through existing versioned ORM, stores pause event in same transaction as state, and publishes live state/event only after commit.

## Constraints and risks

- Original dirty `main` worktree must remain unchanged.
- Local test evidence is SQLite only; PostgreSQL client/server, Docker and Podman are absent, and localhost:5432 refused connections. Mark PostgreSQL gate BLOCKED, not passed.
- No Browser Use/Skyvern benchmark, provider/key spend, legal review, full framework compatibility, full suite, frontend change, worker lease/fencing work, or multi-process test.
- Independent code review and final GitHub preview remain pending at analysis time.
