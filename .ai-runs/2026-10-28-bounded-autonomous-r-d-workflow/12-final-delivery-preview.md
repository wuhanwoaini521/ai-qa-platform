# Final GitHub delivery preview — not yet written

- **Worktree/branch:** `/Users/hans/Code/github/ai-qa-platform-autonomous-rd`, `agent/autonomous-rd-2026-10-28`
- **Current local HEAD/base:** `245c00cacd946c8dea59991807af6b873fcdaf1d`; no mission commit exists yet.
- **Destination:** `origin` → `git@github.com:wuhanwoaini521/ai-qa-platform.git`; repository is **PUBLIC**, default/base branch `main`.
- **Read-only remote check:** `origin/main` is still `245c00cacd946c8dea59991807af6b873fcdaf1d`; remote mission branch does not exist; no existing PR for this head. `main` has no branch protection/required status-check policy configured.
- **User authorization:** normal push to the named development branch and creation of a **Draft** PR against `main`, after exact-path and external-write preview. No force-push, merge, deployment, or unrelated branch operation is authorized.
- **Current action state:** 67 paths are staged and matched this allowlist at the last check; the P2 Worker-test gap is closed by fresh Reviewer (**OK**, no new issue; reviewer did not run tests). Release Engineer returned **PARTIAL / not release-ready for merge**; exact scope and hygiene passed, but tests were not independently rerun and the credential/data scan is not comprehensive. No commit, remote branch, or PR exists. This file is a preview only.

## Proposed local commit and remote actions

- **Commit message:** `feat(r&d): establish bounded research workflow and recovery evidence`
- **Push:** `git push -u origin agent/autonomous-rd-2026-10-28` (normal push only; expected to create a new remote branch).
- **Draft PR:** extract the reviewed fenced PR body verbatim to `/tmp/aiqa-rd-autonomous-rd-pr-body-20261028.md`, then run `gh pr create --draft --base main --head agent/autonomous-rd-2026-10-28 --title "feat(r&d): establish bounded research workflow and recovery evidence" --body-file /tmp/aiqa-rd-autonomous-rd-pr-body-20261028.md`. Remove only that temporary body file after creation.
- Recheck remote branch and `main` immediately before push. Stop if the target ref appears, base advances unexpectedly, authentication changes, or a normal push is not a fast-forward. Do not force.
- If push succeeds but PR creation fails, leave the branch in place and report. If a Draft PR is created and must be rolled back, close the Draft PR; do not delete the remote branch without separate authorization.

## Proposed PR body

```markdown
## Summary
- Add bounded Pi team adapters, portable research/knowledge records, and safe environment-fallback and preview-first delivery guidance.
- Preserve the existing Task Runtime, BrowserRuntime, DecisionService, Provider/Worker boundaries and deterministic test verdicts; no framework dependency/adoption.
- Fix the reproduced Quality Discovery recovery race using the existing versioned ORM and transaction boundary; add bounded recovery and Worker process regression coverage.
- Record an independent architecture challenge. Architecture Gate remains DEFERRED / NOT PASSED.

## Verification
- `test_discovery_task_runtime.py`: 15 passed on per-test SQLite and 15 passed on isolated PostgreSQL 18.6 (`aiqa_test`).
- Post-fix `test_worker_process_integration.py`: 5 passed on SQLite (3 non-failing datetime-adapter deprecation warnings) and 5 passed on isolated PostgreSQL 18.6. Its concurrency assertion now requires both Worker IDs on `ASSIGNED`/`RUNNING` jobs in the same observed snapshot.
- Additional targeted reliability selections: 2 concurrent-write/restart tests and 4 job-reliability tests passed; no aggregate PostgreSQL count is claimed for truncated output.
- Targeted Node runtime/workspace tests: 17 passed on Node 24.21.0.
- Ruff check/format passed for the four modified Python files. A bounded scan of 67 paths checked 46 Markdown links (none broken), found no trailing whitespace and no credential-pattern matches; Pi settings JSON and role configuration validated. `git diff --cached --check` passed on the refreshed 67-path staged set. No comprehensive secret scanner is installed; Release Engineer marks this credential/data review PARTIAL.
- Independent Code Reviewer: **OK**; the prior P2 concurrency-test gap is closed. Reviewer did not run tests.
- Release Engineer: **PARTIAL / not release-ready for merge**; exact scope/diff hygiene passed, but full gates and comprehensive credential/data scanning remain incomplete. A Draft PR would be partial-only.

## Limitations
- Overall R&D mission is PARTIAL: Sprint A–D remain partial; Sprint E is BLOCKED / NOT RUN.
- PostgreSQL evidence is local version 18.6 only; it does not establish production PostgreSQL 16 or multiple API-process Recovery behavior. No general lease/fencing or event/evidence contract is claimed.
- Full repository/API suites, full Web lint/typecheck/build, desktop/browser acceptance, Browser Use/Skyvern execution, provider spend and legal assessment were not run.
- Browser Use/Skyvern remain uninstalled; Architecture Gate remains DEFERRED / NOT PASSED.
- No merge, deployment, production write, or force-push is requested.
```

Initial independent review found a P2 gap in the concurrency test; the assertion was strengthened and the SQLite/PostgreSQL test runs passed. Fresh follow-up Code Review closed the P2, found no new issue, and returned OK (no tests run by the reviewer). Release Engineer returned **PARTIAL / not release-ready for merge**, confirmed the 67-path allowlist and diff hygiene, and found no obvious credentials; it did not rerun tests or perform a comprehensive scan. Parent separately confirmed the current public repo/default branch/no-PR state. Draft PR is authorized as partial-only; no merge/deploy.

## Exact proposed staged-path allowlist (67 files)

```text
.agents/skills/framework-research/SKILL.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/00-request.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/01-analysis.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/02-plan.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/03-implementation.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/04-functional-test.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/06-code-review.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/07-fixes.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/08-regression.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/09-final-report.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/10-github-delivery-preview.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/11-continuation.md
.ai-runs/2026-10-28-bounded-autonomous-r-d-workflow/12-final-delivery-preview.md
.pi/agents/architect.md
.pi/agents/architecture-critic.md
.pi/agents/backend-engineer.md
.pi/agents/design-director.md
.pi/agents/frontend-engineer.md
.pi/agents/knowledge-curator.md
.pi/agents/product-manager.md
.pi/agents/qa-engineer.md
.pi/agents/release-engineer.md
.pi/agents/technology-scout.md
.pi/npm/.gitignore
.pi/settings.json
.pi/skills/team-delivery/SKILL.md
.pi/team/BACKLOG.md
.pi/team/DECISIONS.md
.pi/team/OPERATING_MODEL.md
.pi/team/QUALITY_GATES.md
.pi/team/README.md
.pi/team/ROADMAP.md
apps/api/app/repositories/quality_discovery_repo.py
apps/api/app/services/quality_discovery_service.py
apps/api/tests/test_discovery_task_runtime.py
apps/api/tests/test_worker_process_integration.py
docs/ROADMAP.md
docs/agent-handoff.md
docs/architecture-review/architecture-debate-2026-10-28.md
docs/architecture-review/architecture-decisions.md
docs/architecture-review/current-state.md
docs/architecture-review/framework-comparison.md
docs/architecture-review/framework-p0-verification-2026-10-28.md
docs/architecture-review/implementation-roadmap.md
docs/architecture-review/migration-plan.md
docs/architecture-review/poc-results.md
docs/architecture-review/target-architecture.md
docs/architecture-review/verification-report.md
engineering-knowledge/README.md
engineering-knowledge/decisions/ADR-002-keep-existing-runtime.md
engineering-knowledge/decisions/README.md
engineering-knowledge/experiments/browser-agent-comparison.md
engineering-knowledge/frameworks/browser-use.md
engineering-knowledge/frameworks/langgraph.md
engineering-knowledge/frameworks/skyvern.md
engineering-knowledge/index.md
engineering-knowledge/lessons/README.md
engineering-knowledge/lessons/source-evidence-boundaries.md
engineering-knowledge/patterns/conditional-recovery.md
engineering-knowledge/projects/ai-qa-platform/README.md
engineering-knowledge/skills/README.md
engineering-knowledge/team-definition.md
engineering-knowledge/templates/adr.md
engineering-knowledge/templates/poc-report.md
engineering-knowledge/templates/research-record.md
experiments/architecture-review/poc/evidence-2026-10-28.md
experiments/architecture-review/poc/independent-qa-review.md
```

`apps/api` files, `docs/ROADMAP.md`, and `docs/agent-handoff.md` are modified tracked files; all other listed paths are currently untracked and mission-related. Ignored local install artifacts such as `.pi/npm/package.json`, lockfile and `node_modules` are excluded. The list will be compared byte-for-byte with the final staged path set; any mismatch requires updating/reviewing this preview before writing.

## Review and rollback gates

1. Fresh independent Code Review verified the P2 fix and returned OK. Release Engineer reviewed the complete staged diff and returned PARTIAL: exact scope/hygiene passed; full gates and comprehensive credential/data scan remain incomplete. Treat any PR as Draft/partial only.
2. Final Markdown relative-link, trailing-whitespace, Pi configuration, credential-pattern heuristic, Ruff, `git diff --check`, and refreshed staged `git diff --cached --check` ran successfully. No comprehensive credential scanner is installed.
3. The refreshed stage has 67 paths matching the allowlist and passes `git diff --cached --check`; Release Engineer independently confirmed exact path matching and clean unstaged/untracked status. Do not use `git add -A`.
4. Recheck remote refs and existing PR immediately before the normal push. Commit only after the staged set still exactly matches this preview.
5. Create the Draft PR only against public `main` with the reviewed title/body above. No merge, force-push, deployment, branch-protection change, or production write.
