# Bounded autonomous R&D workflow

- run-date: 2026-10-28
- task-type: maintenance
- scale: standard

## Milestones and acceptance

1. **Isolate and inspect:** create a new worktree/branch from observed HEAD; keep original worktree untouched; read safety and team rules.
2. **Bound the team:** extend only existing Pi adapter; add read-only Scout/Critic and restricted Curator; add reusable non-Pi team/research definitions; retain async/background disabled and human authority.
3. **Research and debate:** use official tagged source/release/license/manifests; separate metadata from runtime/compatibility; one independent critic round; no candidate install, spend or adoption. Architecture Gate remains deferred.
4. **Local Execution Core fix:** reproduce a state-change race; use existing versioned ORM and same transaction; no API/schema or duplicate owners; add concurrent terminal-state and transaction-failure regressions.
5. **Validate:** focused SQLite tests, Ruff, independent reviewer; attempt PostgreSQL only if disposable local environment already exists (do not install/start external services without authorization). Report exact blocked/not-run checks.
6. **Docs/handoff:** reconcile roadmap/backlog/ADR/research/handoff; update `.ai-runs` with evidence and open gates.
7. **GitHub delivery:** review status/diff/secrets/branch/remote/test evidence; only then commit/push/open requested PR if permitted and quality gates sufficiently complete. No merge/deploy.

## Acceptance criteria

- No change to the original dirty worktree.
- Existing runtime/provider/decision/test-verdict ownership preserved.
- Framework facts pinned to sources and unknowns explicit; no candidate execution claim.
- Architecture Gate explicitly DEFERRED / NOT PASSED.
- Focused recovery tests and lint/format checks pass; independent review has no unresolved blocker/major finding, or remains honestly blocked.
- PostgreSQL/multi-process limitation recorded; do not claim full Mission/Sprint completion.
