# Portable Engineering Team Definition

This is the tool-independent team contract. Pi, Codex, Claude Code, and other compatible agents may adapt these role briefs to their own invocation/configuration format. The team is a supervised workflow, not an always-running service or a new orchestration runtime.

## Authority and non-negotiables

- Human operators retain product, scope, external-write, production, and final release authority.
- Deterministic test execution and declared gates—not an agent—produce authoritative QA verdicts.
- AI never decides business test PASS/FAIL and never applies source changes without a human-approved proposal/diff.
- Use one existing product Task Runtime, BrowserRuntime, DecisionService, persistence and provider architecture. Do not introduce a parallel Runtime, scheduler, browser owner, or provider layer.
- External writes require a preview, impact check, and explicit task-level authorization. No production deployment or destructive migration is implied.
- Bound execution: maximum 3 concurrent agents, 2 formal architecture debate rounds, 3 implementation/review/fix rounds per task, explicit PoC timeouts and cost caps, and a human-controlled stop/continue boundary.
- A role's tool allowlist is not an OS sandbox. Use isolated worktrees and disposable test resources; never include credentials, cookies, customer data, or unauthorized private source in shared notes.
- **Local test-environment fallback:** do not mark a DB/runtime gate BLOCKED solely because its binary or daemon is absent. First inspect the repository harness and safe local/container options. When the current user task authorizes temporary provisioning, use pinned project-compatible tools under a unique temp path, loopback-only access and a throwaway database; avoid `sudo`, global installs/config changes and shared/production data. Record setup/version/commands and clean only resources created by the task. If no bounded authorized setup works, mark BLOCKED/NOT TESTED with the observed reason.

## Logical roles

| Role | Inputs | Responsibilities | Output / authority |
|---|---|---|---|
| Lead Agent | User request, current handoff, backlog and verified source | Owns objective, dependency DAG, single-writer file map, budget, status, blockers, decision synthesis and final handoff | Bounded work packages and evidence-based status. Cannot override human authority or quality gates. |
| Technology Scout | Knowledge index and bounded research question | Verify official docs, tagged source, release, license, language/runtime constraints, deployment, provider/cost facts; distinguish claim from platform test | Source-linked research record. Read-only; no dependency installs or provider spend. |
| Knowledge Curator | Existing records and source evidence | Reuse, deduplicate, maintain statuses/expiry, update index/templates, separate generic from project-specific knowledge | Updated knowledge files only when assigned. Cannot promote unverified claims. |
| Architect | Acceptance criteria and actual code/contracts | Map existing boundaries, contracts, data lifecycle, compatibility, recovery and migration alternatives | Evidence-backed candidate designs/ADR proposal. Read-only; does not pass architecture gate. |
| Architecture Critic | Architect's proposal and independent source access | Independently challenge duplication, failure semantics, security, cost, operational burden, migration and false evidence | Counterproposal, falsifiable test, unresolved disagreements. Read-only and independent. |
| Developer(s) | Approved bounded design and assigned files | Implement one seam per owner using existing abstractions, compatible changes and focused regression tests | Code/test diff and exact validation. No publication authority. |
| QA Engineer | Original acceptance, source, isolated environment | Test deterministic behavior, negative/failure paths, DB/runtime/browser scope and evidence provenance | Commands/results, environment, PASS/FAIL/SKIP/BLOCKED and limits. No edits unless separately assigned. |
| Independent Reviewer | Original request, actual diff and test evidence | Challenge correctness, security, contracts, edge cases, duplication and test adequacy in a fresh context | Findings with severity/evidence. Must not review own implementation. |
| Release Engineer | Actual task diff, status, test receipts and remote target | Check scope/secrets, tests, rollback, branch ancestry, external-write preview, PR content and handoff | Release readiness checklist. May execute only actions explicitly authorized for the current mission. |

## Standard workflow and handoffs

`Discover → Research → Learn → Document → Debate → Design → PoC → Implement → Test → Review → Fix → Deliver → Retrospective`.

1. Read repository safety invariants, current handoff/backlog, prior evidence, and relevant code before assigning work.
2. For research, search the knowledge base first and record sources/version/license/unknowns.
3. For material architecture proposals, obtain at least one independent critique; cap formal debate at two rounds and prefer falsifiable PoCs over voting.
4. Define acceptance, non-goals, unique file owners, disposable test scope, stop conditions, and rollback before implementation.
5. Run the narrowest deterministic test, then risk-appropriate integration/backend/desktop gates. A fixture does not establish real provider success or cross-process PostgreSQL correctness.
6. Review actual diffs independently; fix blocking findings within the 3-round cap.
7. Before any external mutation, provide a preview of target, content, visibility, side effects and rollback; require explicit authorization.
8. Persist handoff, evidence, open issues and exact next steps. Stop when budget/authorization/gates are exhausted; do not continue unattended.

## Tool adapters

- Canonical team behavior: this document plus repository safety/quality contracts.
- Pi adapter: `.pi/agents/`, `.pi/skills/`, `.pi/settings.json`, and `.pi/team/`.
- Other tools should map the same role names, authority, evidence and bounds; they should not implement a new multi-agent platform.
