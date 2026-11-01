# AI Software Engineering Organization

This is the project’s durable engineering operating system. The parent Pi session remains Engineering Director / Orchestrator; the specialist files in `.pi/agents/` are real child-agent profiles provided by the pinned `pi-subagents` package, not an always-running company.

## Current readiness

- Pi CLI: 1.4.0; active project provider/model at setup: `openai-codex/gpt-6-luna` (`xhigh`), credentials checked ready without refresh.
- Project-local package: `npm:pi-subagents@0.82.1`, pinned in `.pi/settings.json`; package source inspected before install. The initial genuine `scout` child completed a read-only source inspection through a separate Pi child session. The parent Pi session that predates installation does not gain the tool retroactively; start a new Pi session (or use a fresh child Pi session) to call it directly.
- A real fresh-context `scout` child exited 0 and returned source-backed navigation notes. Its package metadata marked automatic lightweight attestation `rejected` (`Structured acceptance report not found`); this proves delegation/output, not package-gate acceptance. The role listing and `/skill:team-delivery` trigger were subsequently verified in fresh Pi sessions after safety settings were hardened.
- Pencil MCP is configured and was callable (`get_app_state` succeeded). `agent-browser` 0.39.0 is installed; the fresh isolated session reached the login page, while its bundled Chrome 155 failed on a missing macOS VideoToolbox symbol. System Chrome 150.0.7871.125 exists; the prior authenticated Chrome 150 / Playwright 1.62 screenshots are reusable evidence, not a fresh QA session. Orca is not a usable subagent runtime here: its CLI failed to resolve `/usr/local/bin/orca`.
- There is no daemon, scheduler, or online team. Child work runs only when a Pi session invokes it; this process exiting stops normal synchronous work.
- **Subagent runtime re-verified (2026-10-26):** Pi CLI 1.4.0 with repo `.pi/settings.json` and local `pi-subagents@0.82.1` at Git root. This model's fresh parent initially exposes the lazy `subagents_enable` loader; invoke it, then the real `subagent` tool is available on the next model turn. `subagent action=list` discovered seven project roles plus built-in `reviewer`; fresh synchronous Scout, Reviewer, Design Director, QA Engineer, and Release Engineer children actually completed with `async:false`. Runtime diagnosis and QA-001 proof are in `.ai-runs/qa-001-real-runtime/evidence/review-followup/14-independent-review-and-browser-followup.md`. The previous QA-001 session most likely had a stale pre-install tool set; historical session internals are unavailable, so this remains a likely cause, not certainty. No package-path/version/config defect reproduced. A simultaneous direct-call fan-out was rejected with `a subagent call is already in progress`; sequence direct synchronous calls in this harness rather than treating that as package absence. No reinstall or second multi-agent extension was needed.

## Start here in a new session

1. Read root `AGENTS.md`, then this file, `OPERATING_MODEL.md`, `QUALITY_GATES.md`, `BACKLOG.md`, `ROADMAP.md`, `DECISIONS.md`, and the latest `docs/agent-handoff.md` entry.
2. Check `git rev-parse HEAD`, `git status --short`, actual tests/evidence, and available Pi tools. Protect all pre-existing user changes.
3. Invoke `/skill:team-delivery <request>` or naturally say “按团队流程实现……” / “按团队流程分析……”. The skill chooses a small role set and composes existing `project-delivery`, `ui-ux-review`, and `full-project-validation` only when relevant.
4. If `subagent` is not callable, state that and use an explicit serial role workflow. Never present a role-play transcript as a real child run.

## Role map

| Responsibility | Runtime profile |
|---|---|
| Product Manager | `product-manager` |
| UX / Design Director | `design-director` |
| Software Architect | `architect` |
| Frontend Engineer | `frontend-engineer` |
| Backend Engineer | `backend-engineer` |
| QA Automation Engineer | `qa-engineer` |
| Code Reviewer | Pi Subagents’ built-in `reviewer` (fresh, read-only) |
| Release / Integration Engineer | `release-engineer` |

The role profiles describe authority and allowed Pi tools. A tool allowlist limits available tools but is not an OS sandbox; any role with `bash` remains bound by the project’s no-write/no-production policy.

## State and evidence

- Current task state: `.pi/team/BACKLOG.md` and `.pi/team/ROADMAP.md`. User-requested delivery `UI-001` is DONE (WITH NOTES): Graphite fidelity is implemented for the ten named desktop view states; frontend gates pass, Code Review is OK, Design and Release are PASS WITH NOTES. QA is PARTIAL for dense-but-readable 1280px Results and the pre-existing Chinese BrowserRuntime error detail in English Explore; see `.ai-runs/2026-10-27-graphite-fidelity-recovery/02-implementation-plan.md` and `docs/agent-handoff.md` §3.34. User-requested `UI-002` is DONE WITH NOTES under `.ai-runs/2026-10-28-ui-002-workspace-journey/`: Results/context/Write Tests/Quality PASS; AI Repair is PARTIAL because live proposal/approval execution was explicitly out of scope; Debug runtime/LSP is untested. Frontend, i18n, and focused API gates passed; Code Review OK, Design PASS WITH NOTES, Release recommends closure. Browser evidence is synthetic fixture only. QA-003 Apply/Verify remains BLOCKED. QA-001 and QA-002 are DONE. QA-003 is BLOCKED: real provider readiness passed, but the single isolated failure run returned no BrowserRuntime page controls, so no analysis/proposal or Awaiting Approval state was reached. See `.ai-runs/2026-10-28-qa-003-real-ai-failure-repair/05-qa-report.md`; do not auto-retry or fabricate evidence. Any future real proposal must stop for explicit approval of that exact patch.
- Approved engineering choices: `.pi/team/DECISIONS.md`.
- Durable session recovery: `docs/agent-handoff.md` (the existing handoff system remains canonical; this folder does not replace it).
- Pilot evidence and this setup’s audit trail: `.ai-runs/2026-10-25-engineering-organization/`.

No task becomes `DONE` on implementation alone. Do not commit, push, merge, deploy, run unattended loops, auto-apply AI patches, or run mobile-specific work.
