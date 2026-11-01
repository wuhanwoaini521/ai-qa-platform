---
name: team-delivery
description: "Run ai-qa-platform's engineering team workflow for an approved feature, bug fix, UX improvement, refactor, QA acceptance, security/runtime change, or technical-debt task. Trigger when the user asks to follow the team process, implement end-to-end, independently review/QA, or route work to the product, design, architecture, engineering, QA, reviewer, or release roles. This skill explicitly authorizes bounded real Pi subagent delegation when it adds evidence or independent review; it does not authorize product decisions, unapproved code changes, external writes, commits, pushes, deployments, or unattended work."
---

# Team Delivery

The parent Pi is Engineering Director / Orchestrator and owns the final handoff. This skill is an executable workflow entry, not a simulated company conversation.

## Restore the actual state first

1. Read root `AGENTS.md`, `.pi/team/README.md`, `.pi/team/OPERATING_MODEL.md`, `.pi/team/QUALITY_GATES.md`, the relevant backlog/decision entries, and the newest `docs/agent-handoff.md` section.
2. Check `pwd`, `git rev-parse HEAD`, `git status --short`, and actual test evidence. Preserve every pre-existing change; never reset, clean, stash, commit, push, merge, or deploy.
3. Read the relevant source, callers, tests, API/runtime boundary and existing design docs before proposing files or behavior. If repository code disagrees with a historical report, use code and fresh evidence and note the discrepancy.
4. Classify the task and risk. Establish the user/problem/value, existing capability, measurable acceptance criteria, explicit exclusions, and status before assigning work.

## Choose the smallest team

Use `.pi/team/OPERATING_MODEL.md` role contracts. Assign only roles required by risk:

- Product change: Product Manager.
- Architecture/API/data/runtime/security impact: Architect.
- UI/workflow change: Design Director and Frontend Engineer.
- Backend/API/runtime: Backend Engineer.
- Every code change: independent Code Reviewer; QA Engineer for acceptance.
- Final changed-file/test/recovery check: Release Engineer.

For the UI / API / runtime pilots, separate product-visual acceptance from functional/engineering acceptance. Do not start all roles for a trivial read-only question.

## Real delegation and ownership

- This invocation is the user's/project's explicit authorization to delegate where appropriate. Use the actual `subagent` runtime when callable; call `subagents_enable` if that is the visible loader. Start children with fresh context, the repository cwd, current ref, exact acceptance, evidence, owner/file boundary, validation command and stop condition.
- For a direct child, pass `async:false` as an actual `subagent` call parameter and `options:{context:"fresh"}`; do not merely put `async:false` in task prose. Project settings disable async-by-default, auto-resume, missions, schedules, and workflow scripts, so omit those arguments/features. Never schedule, detach, auto-resume or continue after the Pi process exits. Do not let child agents recursively delegate unless the parent has explicitly planned and bounded that fanout.
- Maximum 3 concurrent high-cost children. One writer per file; parallelize only independent read-only tasks or isolated seams. Keep a maximum of 3 implementation → review → repair rounds.
- If the tool is missing or fails, record the exact error and perform clearly labeled serial role steps. Never simulate or claim a real child result.
- Role tools are allowlists, not OS sandboxes. Treat bash-capable roles as capable of side effects and brief them accordingly.

## Lifecycle

1. **Intake:** choose task type and risk; product brief and non-goals; inspect existing state and acceptance.
2. **Plan:** Architect determines code/API/runtime/data boundaries; Design Director determines UX impact; Orchestrator creates a minimal dependency DAG and one-writer file map. Write ADR only for a material architecture decision.
3. **Design / contract:** use existing route, component, service, repository, `DecisionService`, Task Runtime and `BrowserRuntime`; define exact API/state contract where applicable.
4. **Implementation:** developer changes only the approved scope. Every new button must do real work; no static demo in place of product behavior.
5. **Review:** fresh, separate `reviewer` sees original task, acceptance, actual diff and test results. Report Blocker/Major/Minor/Suggestion with file/line evidence; fix blocking correctness, security, compatibility and regression findings.
6. **QA:** QA independently runs applicable commands and real API/browser/runtime behavior. Record exact command, environment, exit status, PASS/FAIL/SKIP/BLOCKED, evidence path and untested scope. Do not call synthetic fixtures or mock AI real execution/provider success.
7. **Design gate:** Design Director reviews provided live-browser desktop screenshots and interactions; only 1280×800, 1440×900 and 1920×1080 are in scope. Graphite is locked on implemented Graphite surfaces; no mobile-specific work.
8. **Integration / acceptance:** Release Engineer checks scope, status, tests, rollback and user-change preservation. Orchestrator derives `PASS`, `PARTIAL`, `FAIL`, or `BLOCKED` against criteria/evidence. Test verdict itself remains deterministic and cannot be changed by AI.
9. **Handoff:** update the current backlog state and existing `docs/agent-handoff.md` at verified milestones with commit, changes, evidence, unresolved risks/blockers and next command. Read-only requests do not create `.ai-runs` logs.

## Compose existing skills

- Use `project-delivery` for implementation lifecycle and review/regression gates.
- Use `ui-ux-review` for UX-led review or improvement; add `project-delivery` for implementation.
- Use `full-project-validation` only when the user asks for whole-application validation.
- Use existing `orchestration` only when its actual Orca runtime is callable; it is not a substitute for Pi subagents. Use `agent-browser` for real browser interaction and the current local CLI workflow.
- Do not duplicate or overwrite these skills.

## Safety and release

- Code changes require explicit user authorization. The task request authorizes only its stated bounded scope. An AI patch stays a proposal until the human explicitly approves it.
- Never modify production data/config or issue external writes without preview and explicit confirmation. No unattended loops, schedule, deployment or automatic Git operation.
- Use isolated test database/project/site for write-capable runtime tests. Browser screenshot success alone is not a functional pass. A mock provider result is not real AI success.
- Do not mark `DONE` until all applicable QA/review/design/integration criteria pass. If evidence is unavailable, mark `PARTIAL`/`BLOCKED`, not complete.

## Usage

- `按团队流程分析这个需求：…`
- `按团队流程实现这个功能：…`
- `让 QA 独立验收 …（不要改代码）`
- `让设计负责人审查 Graphite UI …`
- `让架构师审查 …`
