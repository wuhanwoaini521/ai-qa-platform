# Initial GitHub delivery preview — superseded snapshot

> This preview predates the user's explicit normal development-branch push/Draft PR authorization and the later PostgreSQL/Worker evidence. Read `12-final-delivery-preview.md` for the current preflight and exact final file/body preview. No remote write had occurred when this snapshot was prepared.

- run-date: 2026-10-28
- branch: `agent/autonomous-rd-2026-10-28`
- base commit: `245c00cacd946c8dea59991807af6b873fcdaf1d`
- upstream: none configured
- remote: `origin` configured; remote state/freshness not checked or contacted
- current state: no staged files, no mission commit, no push, no PR

## Proposed PR

**Title:** `feat(r&d): establish bounded research workflow and fix recovery race`

**Type:** Draft PR / partial acceptance only, if explicitly authorized. No merge, release, deployment, or architecture approval.

**Summary:**

- Extend the existing Pi team with bounded Scout, Knowledge Curator, and Architecture Critic roles and a tool-independent team/research contract.
- Add source-linked Markdown knowledge records and official P0 release/license/manifest verification for LangGraph 1.2.18, Browser Use 0.13.14, and Skyvern v1.0.56. Candidates remain uninstalled and unbenchmarked.
- Record an independent architecture challenge; retain existing Task Runtime, BrowserRuntime, DecisionService, providers and deterministic Pytest. Architecture Gate stays **DEFERRED / NOT PASSED**.
- Prevent Quality Discovery startup recovery from overwriting a newer terminal status and persist the pause event atomically with that transition.

**Verification to state in PR:**

- Focused SQLite test file: 15 passed (parent 3.37s; independent QA 3.40s).
- Ruff check and format check: passed for 3 changed Python files; `git diff --check` passed.
- Independent fresh-context code review: no issues found, OK with notes; reviewer did not run tests.
- PostgreSQL/multi-process recovery: **BLOCKED / NOT TESTED** (no local DB/container runtime/service).
- Browser Use/Skyvern comparison, provider spend, legal review, full API/frontend suite: **NOT RUN**.
- Overall Mission: **PARTIAL**, not complete; no framework adoption.

## Preflight still required before remote write

1. The user has since authorized a normal push of `agent/autonomous-rd-2026-10-28` and Draft PR against `main`; this is conditional on exact final-path review and remote/write preview. The authorization excludes force-push, merge, deployment, and unrelated changes.
2. Refresh/read current remote base and branch state; inspect the exact complete diff, including all untracked files selected for the PR and ignored local artifacts excluded from it. Re-run staged `git diff --check`; five copied architecture-review docs currently contain 12 intentional Markdown hard-break trailing spaces, which may need normalization if included.
3. Run a full secret/data scan on the exact staged set; the Release Engineer's prior scan was targeted to `.ai-runs` and is not comprehensive.
4. Re-run required final tests/checks against the frozen exact commit; retain the PostgreSQL block as explicit partial status unless a disposable DB becomes available.
5. Preview final PR body/visibility/base/head and rollback plan; ask before push/create if authorization is not explicit.

This is a historical local preview only. Current authorization/preflight and the exact proposed write are recorded in `12-final-delivery-preview.md`; no merge, force-push, or deployment is authorized.
