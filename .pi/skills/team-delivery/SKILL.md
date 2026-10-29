---
name: team-delivery
description: "Run ai-qa-platform's engineering team workflow for an approved feature, bug fix, UX improvement, research, knowledge curation, architecture debate, refactor, QA acceptance, security/runtime change, or technical-debt task. Trigger when the user asks to follow the team process, implement end-to-end, independently review/QA, research technologies, curate knowledge, challenge architecture, or route work to product, design, scout, curator, architecture, engineering, QA, reviewer, or release roles. This skill explicitly authorizes bounded real Pi subagent delegation when it adds evidence or independent review; it does not authorize product decisions, unapproved code changes, external writes, commits, pushes, deployments, or unattended work."
---

# Team Delivery

The parent Pi is Engineering Director / Orchestrator and owns the final handoff. This skill is an executable workflow entry, not a simulated company conversation.

## Restore the actual state first

1. Read root `AGENTS.md`, `.pi/team/README.md`, `.pi/team/OPERATING_MODEL.md`, `.pi/team/QUALITY_GATES.md`, the relevant backlog/decision entries, and the newest `docs/agent-handoff.md` section.
2. Check `pwd`, `git rev-parse HEAD`, `git status --short`, and actual test evidence. Preserve every pre-existing change; never reset, clean, stash, merge, or deploy. Commits/pushes require explicit authorization for the exact mission and an inspected external-write preview.
3. For research or architecture work, first read `engineering-knowledge/README.md` and `engineering-knowledge/index.md`; reuse records and distinguish source metadata, vendor claims, inference, and executed evidence. Read relevant source, callers, tests, API/runtime boundaries and design docs before proposing behavior. If repository code disagrees with a historical report, use code and fresh evidence and note the discrepancy.
4. Classify the task and risk. Establish the user/problem/value, existing capability, measurable acceptance criteria, explicit exclusions, and status before assigning work.

## Choose the smallest team

Use `.pi/team/OPERATING_MODEL.md` role contracts. Assign only roles required by risk:

- Product change: Product Manager.
- Technology/release/license/compatibility research: Technology Scout; record curation: Knowledge Curator.
- Material architecture proposal: Architect plus fresh independent Architecture Critic; cap at 2 formal debate rounds. Agents do not pass the human-owned Architecture Gate.
- Architecture/API/data/runtime/security impact: Architect.
- UI/workflow change: Design Director and Frontend Engineer.
- Backend/API/runtime: Backend Engineer.
- Every code change: independent Code Reviewer; QA Engineer for acceptance.
- Final changed-file/test/recovery check: Release Engineer.

For the UI / API / runtime pilots, separate product-visual acceptance from functional/engineering acceptance. Do not start all roles for a trivial read-only question.

## Real delegation and ownership

- This invocation is the user's/project's explicit authorization to delegate where appropriate. Use the actual `subagent` runtime when callable; call `subagents_enable` if that is the visible loader. Start children with fresh context, the repository cwd, current ref, exact acceptance, evidence, owner/file boundary, validation command and stop condition.
- For a direct child, pass `async:false` as an actual `subagent` call parameter and `options:{context:"fresh"}`; do not merely put `async:false` in task prose. Project settings disable async-by-default, auto-resume, missions, schedules, and workflow scripts, so omit those arguments/features. Never schedule, detach, auto-resume or continue after the Pi process exits. Do not let child agents recursively delegate unless the parent has explicitly planned and bounded that fanout.
- Maximum 3 concurrent high-cost children. One writer per file; parallelize only independent read-only tasks or isolated seams. Keep at most 2 formal architecture-debate rounds and 3 implementation → review → repair rounds. Every PoC needs a stop condition, timeout, disposable environment/cleanup boundary, and explicit spend cap before execution.
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
- Never modify production data/config or issue external writes without a preview and explicit confirmation. No unattended loops, schedules, deployments or automatic Git operations. `.pi/settings.json` disables automatic subagent preflight; this does not waive the manual changed-file/secrets/tests/target/rollback preview before a push or PR.
- Use isolated test database/project/site for write-capable runtime tests. Browser screenshot success alone is not a functional pass. A mock provider result is not real AI success.
- Do not mark `DONE` until all applicable QA/review/design/integration criteria pass. If evidence is unavailable, mark `PARTIAL`/`BLOCKED`, not complete.

### Missing local test infrastructure

A missing local database/container binary is a discovery result, not by itself the end of an explicitly authorized test task. Inspect the project test harness and available local/container tools. When the request authorizes temporary setup, use a pinned project-compatible server/container in a unique temporary directory, bind only to loopback, and use a throwaway test database. Check whether fixtures drop schemas/tables before connecting; never use shared or valuable data. Do not use `sudo`, install system-wide services, change global configuration or dependency locks, or reuse a non-disposable developer database. Record the exact version, setup/test/cleanup commands and exit codes. Mark the gate BLOCKED only after bounded authorized options are unavailable or fail.

### GitHub delivery preview (no separate delivery skill required)

If the user explicitly authorizes a development-branch push and/or Draft PR, this existing workflow owns the bounded delivery; the authorization does not imply merge, force-push, deployment or unrelated branch changes.

1. Read-only inspect repository visibility, target/base branch and protection, branch ancestry/upstream/remote head, existing PRs and required project checks.
2. Select only task-authorized paths; never use blanket `git add -A` in a dirty worktree. Review the complete staged diff and exact file list, run relevant checks and a credential/data review, and record a preview of branch, commit, target, PR title/body, visibility and rollback. Obtain any missing target/visibility authorization before writing.
3. Commit only the reviewed staged paths. Push normally to the explicitly authorized development branch; if the remote ref is divergent or cannot be advanced without force, stop and report it. Create or update a **Draft** PR only after its base/head/body preview. Never merge, force-push, alter protection or deploy.
4. Record exact commit, push result, Draft PR URL, unresolved CI/review gates and recovery steps in the handoff.

## Usage

- `按团队流程分析这个需求：…`
- `按团队流程实现这个功能：…`
- `让 QA 独立验收 …（不要改代码）`
- `让设计负责人审查 Graphite UI …`
- `让架构师审查 …`
