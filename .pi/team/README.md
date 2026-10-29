# AI Software Engineering Organization

This is the project’s durable engineering operating system. The parent Pi session remains Engineering Director / Orchestrator; the specialist files in `.pi/agents/` are real child-agent profiles provided by the pinned `pi-subagents` package, not an always-running company.

## Current readiness

- Existing adapter: Pi CLI 1.4.0 with project-local `pi-subagents@0.82.1`; the durable exact version pin is `.pi/settings.json`. `.pi/npm/package.json`, lockfile, and installed modules are local ignored install artifacts, not portable team configuration. Foreground-only defaults remain: async-by-default, auto-resume, durable schedules and mission/workflow automation are disabled.
- The project is not an always-online company or background service. Agents run only when a supervised session invokes them; work stops when that session exits.
- Existing logical roles are reused. This mission adds `technology-scout`, `knowledge-curator`, and `architecture-critic`; independent code review continues to use the package's fresh-context `reviewer` role. Tool allowlists are not OS sandboxes.
- Team and cross-project portability contracts are in [`engineering-knowledge/team-definition.md`](../../engineering-knowledge/team-definition.md) and [`engineering-knowledge/README.md`](../../engineering-knowledge/README.md). Pi-specific profiles/settings are adapters only.
- Real child-agent audit, source research, and architecture challenge evidence is recorded in `docs/agent-handoff.md` and `docs/architecture-review/architecture-debate-2026-10-28.md`. These reports do not pass the architecture gate.

## Start here in a new session

1. Read root `AGENTS.md`, then this file, `OPERATING_MODEL.md`, `QUALITY_GATES.md`, `BACKLOG.md`, `ROADMAP.md`, `DECISIONS.md`, and the latest `docs/agent-handoff.md` entry.
2. Check `git rev-parse HEAD`, `git status --short`, actual tests/evidence, and available Pi tools. Protect all pre-existing user changes.
3. Invoke `/skill:team-delivery <request>` or naturally say “按团队流程实现……” / “按团队流程分析……”. The skill chooses a small role set and composes existing `project-delivery`, `ui-ux-review`, and `full-project-validation` only when relevant.
4. If `subagent` is not callable, state that and use an explicit serial role workflow. Never present a role-play transcript as a real child run.

## Role map

| Responsibility | Runtime profile |
|---|---|
| Lead Agent / Orchestrator | Parent session; no child profile or unattended service |
| Technology Scout | `technology-scout` |
| Knowledge Curator | `knowledge-curator` |
| Software Architect | `architect` |
| Architecture Critic | `architecture-critic` |
| Product Manager | `product-manager` |
| UX / Design Director | `design-director` |
| Frontend / Backend Engineers | `frontend-engineer`, `backend-engineer` |
| QA Automation Engineer | `qa-engineer` |
| Independent Code Reviewer | Pi Subagents’ built-in `reviewer` (fresh, read-only) |
| Release / Integration Engineer | `release-engineer` |

The role profiles describe authority and allowed Pi tools. A tool allowlist limits available tools but is not an OS sandbox; any role with `bash` remains bound by the project’s no-write/no-production policy.

## State and evidence

- Autonomous R&D Mission is **PARTIAL / IN_PROGRESS** (not a closed product backlog item); source research, architecture challenge, reviewer result, focused SQLite test evidence, and PostgreSQL block are in `.pi/team/BACKLOG.md` and `docs/agent-handoff.md` §3.18. Architecture Gate remains DEFERRED / NOT PASSED.
- Current task state: `.pi/team/BACKLOG.md` and `.pi/team/ROADMAP.md`. User-requested delivery `UI-001` is DONE (WITH NOTES): Graphite fidelity is implemented for the ten named desktop view states; frontend gates pass, Code Review is OK, Design and Release are PASS WITH NOTES. QA is PARTIAL for dense-but-readable 1280px Results and the pre-existing Chinese BrowserRuntime error detail in English Explore; see `.ai-runs/2026-10-27-graphite-fidelity-recovery/02-implementation-plan.md` and `docs/agent-handoff.md` §3.34. User-requested `UI-002` is DONE WITH NOTES under `.ai-runs/2026-10-28-ui-002-workspace-journey/`: Results/context/Write Tests/Quality PASS; AI Repair is PARTIAL because live proposal/approval execution was explicitly out of scope; Debug runtime/LSP is untested. Frontend, i18n, and focused API gates passed; Code Review OK, Design PASS WITH NOTES, Release recommends closure. Browser evidence is synthetic fixture only. QA-003 Apply/Verify remains BLOCKED. QA-001 and QA-002 are DONE. QA-003 is BLOCKED: real provider readiness passed, but the single isolated failure run returned no BrowserRuntime page controls, so no analysis/proposal or Awaiting Approval state was reached. See `.ai-runs/2026-10-28-qa-003-real-ai-failure-repair/05-qa-report.md`; do not auto-retry or fabricate evidence. Any future real proposal must stop for explicit approval of that exact patch.
- Approved engineering choices: `.pi/team/DECISIONS.md`.
- Durable session recovery: `docs/agent-handoff.md` (the existing handoff system remains canonical; this folder does not replace it).
- Pilot evidence and this setup’s audit trail: `.ai-runs/2026-10-25-engineering-organization/`.

No task becomes `DONE` on implementation alone. Commits and pushes require explicit authorization for that mission, a clean scope/secret/test preflight, and an external-write preview; merges, deployments, unattended loops, auto-applied AI patches, and mobile-specific work remain prohibited unless separately authorized.
