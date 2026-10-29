# Product Roadmap — Next 5

## Product north star

Help QA Engineers complete one trustworthy, continuous journey: project → explore/record → generate/edit automation → execute → inspect results/evidence → debug → propose AI repair → human approve → exact verification. Prioritize real desktop workflow continuity and deterministic evidence over feature count. Graphite Developer Studio is the approved visual direction on the currently implemented Graphite surfaces; no new global direction or mobile work.

## Autonomous R&D Mission — bounded status (2026-10-28)

| Workstream | Status | Evidence / stop condition |
|---|---|---|
| Existing Pi team audit and role upgrade | PARTIAL | Scout/Curator/Critic profiles and portable team model added; validate Pi discovery/config and independent review before claiming ready. |
| Portable Engineering Knowledge Base | PARTIAL | Markdown index and source-linked records are present. Scout → Curator → independent consumer reuse experiment succeeded on the pinned SQLAlchemy versioning topic; broader portability and review remain pending. |
| LangGraph / Browser Use / Skyvern research | SOURCE VERIFIED / POC NOT RUN | Release/license/manifest facts at pinned tags are recorded. No candidate installed, compatibility-tested, or benchmarked; Skyvern legal applicability unknown. |
| Architecture debate / ADR | DEFERRED | One independent challenge round; current Architecture Gate remains DEFERRED / NOT PASSED. |
| Execution Core recovery fix | PARTIAL | The 15-case focused suite passed on SQLite and disposable PostgreSQL 18.6 for the narrow recovery state/event path. Production PostgreSQL 16 and multi-process API ownership remain unverified. |
| Sprint A — lifecycle semantics | PARTIAL | Targeted Discovery/Task recovery tests pass on SQLite and PostgreSQL 18.6; the complete lifecycle matrix and API-wide unification remain incomplete. |
| Sprint B — event/evidence | PARTIAL | Recovery status/event atomicity and rollback tests pass on both databases; no general event/evidence contract or cross-process ordering guarantee. |
| Sprint C — worker reliability | PARTIAL | SQLite/PostgreSQL 18.6 Worker tests cover crash recovery, cancellation, timeout, late/duplicate result rejection and two concurrent subprocesses. No lease/fencing generation or stale reassignment guarantee. |
| Sprint D — frontend consistency | PARTIAL | 17 targeted Node status/live-model tests pass; no UI source changed. Full Web and desktop browser gates were not run. |
| Sprint E — browser comparison | BLOCKED / NOT RUN | No local model endpoint or provider cost cap. Candidates remain uninstalled; legal/runtime/compatibility gates remain open. |

Continue only within the authorized Mission and existing architecture. PostgreSQL 18.6 evidence does not substitute for production PG16 or multi-process Discovery ownership; it does not pass the Architecture Gate or authorize widening the architecture.

## Active user-requested delivery

| Backlog ID | Scope | Status | Evidence / next gate |
|---|---|---|---|
| UI-001 | Direction A Graphite fidelity across Dashboard, Workspace Debug/Explore/Requirements/Test Explorer/Write Tests/Results/AI Repair, Projects, and Quality at the three approved desktop sizes | DONE (WITH NOTES) | `.ai-runs/2026-10-27-graphite-fidelity-recovery/`; 30 actual React captures and frontend gates passed; Code Review OK, Design PASS WITH NOTES, Release PASS WITH NOTES; QA PARTIAL caveats recorded in plan and handoff |
| UI-002 | Improve Results layout, Results/Debug/AI Repair continuity, Write Tests context, and verify Quality metric semantics on the same Graphite desktop baseline | DONE (WITH NOTES) | `.ai-runs/2026-10-28-ui-002-workspace-journey/`; 15 actual React after captures, final frontend/i18n/API gates pass; Code Review OK, Design PASS WITH NOTES, Release recommends closure. QA marks Results/context/Write Tests/Quality PASS; AI Repair PARTIAL because live proposal/approval execution was explicitly out of scope. Debug runtime/LSP untested; synthetic fixtures only. QA-003 Apply/Verify remains BLOCKED. |

## Prioritized work and current status

| Order | Backlog ID | Priority | User value / risk | Status | Next gate |
|---|---|---|---|---|---|
| 1 | QA-001 | P0 | Proves run evidence and failure context survive the key Dashboard → Results → Debug path using a real execution | DONE | Independent review/QA/design/release gates passed; evidence in `.ai-runs/qa-001-real-runtime/` |
| 2 | QA-002 | P0 | Makes browser exploration/recording a trustworthy starting point for editable automation, not a static demo | DONE | Historical workflow evidence retained; desktop/browser/frontend and independent architect/code/QA/Design/Release gates pass; see `.ai-runs/qa-002-recorder-workflow/evidence/remediation/03-release-gate-and-closeout.md` |
| 3 | QA-003 | P0 | Completes the high-risk human-approved AI repair loop without misrepresenting provider availability | BLOCKED | Real providers READY, but isolated failed Run yielded no BrowserRuntime page controls; proposal analysis did not start. Needs explicitly authorized evidence-setup remediation before another attempt. |
| 4 | QA-004 | P1 | Improves real failure diagnosis through Locator, logs, browser evidence and a coherent Graphite desktop workspace | READY | Populated real failure fixture |
| 5 | QA-005 | P1 | Reduces lost/stale BrowserRuntime work across API restart/cancel/recovery | READY | Runtime lifecycle contract and isolated process test |

No completion percentage is assigned. The separate `docs/ROADMAP.md` includes longer-term product/technical milestones; the backlog above identifies immediate user-facing evidence gaps and must not rewrite its approved invariants.

## Sequencing and constraints

- QA-001 is DONE and supplies verified execution/failure evidence for QA-003 and QA-004.
- QA-002's isolated controlled-site workflow passed on retained historical evidence. User-authorized desktop remediation and all fresh browser/frontend, architect/code, QA, Design, and Release gates pass; QA-002 is DONE. It does not replace QA-001.
- QA-003 provider readiness passed, but the one proposal-only integration attempt stopped before analysis because the isolated failed Run had no BrowserRuntime page-session controls. Status is BLOCKED; do not fabricate session evidence, retry unattended, apply, or verify. If a future authorized attempt produces a real proposal, stop at Awaiting Approval until the user approves that exact patch.
- QA-005 can be designed in parallel as read-only contract work but implementation waits for Architect review and explicit user direction.
- QA-002 is DONE with its final gate matrix in `.ai-runs/qa-002-recorder-workflow/evidence/remediation/03-release-gate-and-closeout.md`; prior Design FAIL/Release PARTIAL remain historical. QA-003 is BLOCKED by missing real BrowserRuntime page evidence after provider readiness PASS; first attempt is recorded in `.ai-runs/2026-10-28-qa-003-real-ai-failure-repair/05-qa-report.md`. Do not auto-retry or proceed to approval/verification.
