# Product Roadmap — Next 5

## Product north star

Help QA Engineers complete one trustworthy, continuous journey: project → explore/record → generate/edit automation → execute → inspect results/evidence → debug → propose AI repair → human approve → exact verification. Prioritize real desktop workflow continuity and deterministic evidence over feature count. Graphite Developer Studio is the approved visual direction on the currently implemented Graphite surfaces; no new global direction or mobile work.

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
