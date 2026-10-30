# Agent Guidelines — AI QA Platform

> Scope: Repository-wide instructions for Pi, Codex, Claude Code, and other coding agents.
>
> Principle: **Safety first. Deterministic execution. Evidence-based delivery. Reuse before creation.**

## 1. Non-Negotiable Invariants

Before development, read `docs/ROADMAP.md` §0.

The following rules take precedence over task instructions that conflict with project constraints:

1. **Human-controlled decisions** — AI must not independently determine authoritative test PASS/FAIL. Reuse existing deterministic evaluation and `DecisionService`.
2. **Human-authorized changes** — Modify code only within explicitly authorized task scope. Expanding scope requires additional approval. Read-only analysis does not authorize implementation.
3. **Deterministic first** — Prefer reproducible rules, explicit state transitions, and verifiable execution over probabilistic agent decisions.
4. **Preview before external writes** — External mutations require a preview and explicit authorization before execution. Never assume permission for destructive operations.
5. **No unattended agent loops** — Agent execution must have bounded scope, termination conditions, and human-controlled continuation.
6. **No duplicate execution infrastructure** — Do not introduce parallel Runtime, Agent, Provider, orchestration, or browser execution systems when existing components can be extended.

Reuse existing:

- `DecisionService`
- Task Runtime
- `BrowserRuntime`
- Existing Provider and Agent abstractions

Before modifying architecture, inspect the relevant implementation and contracts.

**Repository code is the source of truth for observed behavior.** If documentation conflicts with implementation, report the discrepancy. Do not silently reinterpret or change architectural invariants.

## 2. Repository and Environment

### Repository integrity

- Identify the current repository using `pwd` or PowerShell `Get-Location`.
- Never guess repository locations or assume a fixed operating system.
- Inspect relevant source files, tests, and documentation before editing.
- Preserve existing user changes, including uncommitted and untracked files.
- Do not modify unrelated files or introduce unnecessary dependencies.

### Development environment

| Area | Standard |
|---|---|
| Platforms | macOS, Linux, Windows |
| Python | 3.13 via `mise` |
| Node.js | 24 via `mise` |
| Python dependencies | `uv` |
| Frontend dependencies | `pnpm` |
| Browser automation | Playwright 1.62.0 |
| Cross-platform task entry | `scripts/task.py` |

Rules:

- Use existing project tooling and lockfiles.
- Prefer `scripts/task.py` for development, testing, and linting.
- `scripts/dev`, `scripts/test`, and `scripts/lint` are Bash wrappers, not universal entry points.
- Do not install or execute Playwright 1.63.0 or newer.
- Never use `sudo` for project dependency installation.
- Do not perform broad dependency upgrades without authorization.
- Do not bypass failing tests by suppressing errors or weakening assertions.

## 3. Architecture Boundaries

| Path | Responsibility |
|---|---|
| `apps/web` | React, TypeScript, Vite frontend |
| `apps/api` | FastAPI, REST endpoints, domain services |
| `apps/worker` | QA execution workers and long-running jobs |
| `packages/qa-core` | Testing contracts, runners, diagnostics |
| `packages/project-model` | Shared domain models and schemas |
| `packages/integrations` | External service integrations |
| `runtime/` | Mutable workspace data and execution artifacts |

Architecture requirements:

- Extend existing abstractions before creating new components or services.
- Keep domain decisions separate from UI presentation and AI suggestions.
- Keep execution state and lifecycle consistent with the existing Task Runtime.
- Do not create duplicate state stores or orchestration paths without architectural review.
- Respect API, worker, frontend, and shared-package boundaries.
- Never commit runtime data, credentials, browser profiles, or generated execution artifacts.

New architectural abstractions require a concrete justification, compatibility analysis, and review before implementation.

## 4. Desktop First — Product Scope

AI QA Platform is a **desktop Web Developer Tools product**, not a mobile-first application.

### Supported desktop viewports

| Viewport | Purpose | Priority |
|---|---|---|
| 1440×900 | Primary design and acceptance baseline | P0 |
| 1280×800 | Compact desktop, overflow and usability | P0 |
| 1920×1080 | Large desktop, workspace density | P1 |

Prioritize workflows involving:

- Editor and Workflow Canvas
- Browser and Debug panels
- AI Copilot and Locator tools
- Execution Logs, Results, and Evidence
- Dashboard, Projects, Quality, and Workspace

### Mobile is out of scope

Unless explicitly requested:

- Do not develop mobile-specific layouts, components, navigation, or interactions.
- Do not create mobile-specific CSS or regression tests.
- Do not capture mobile screenshots or perform mobile visual acceptance.
- Do not treat mobile-only defects as desktop release blockers.
- Preserve existing mobile behavior where practical; do not proactively redesign it.

Historical mobile requirements in prompts, TODOs, and design documents are **OUT OF SCOPE** unless explicitly reactivated.

### Design consistency

Follow `docs/UI_DESIGN_SYSTEM.md`.

The active desktop design direction is **Graphite Developer Studio**.

Prefer existing design tokens, components, navigation patterns, and layout primitives. Avoid introducing competing visual systems.

Do not sacrifice functional usability, accessibility, or readability for visual fidelity.

## 5. Development Priorities and Efficiency

Default priority order:

1. Correct, functional desktop interactions
2. Continuous end-to-end workflows
3. Clear information architecture and layout
4. Visual consistency and accessibility
5. Performance optimization based on evidence

Working rules:

- Prefer minimal, complete, verifiable changes over broad rewrites.
- Fix root causes rather than adding temporary UI workarounds.
- Do not repeatedly redesign already-approved screens.
- Reuse relevant, still-valid test evidence.
- Run tests proportional to the affected code and risk.
- Avoid redundant screenshots, audits, speculative analysis, and unrelated investigations.
- Do not claim validation from code inspection alone.
- Stop expanding implementation when the authorized acceptance criteria are satisfied.

Optimization must never weaken required quality gates.

## 6. Agent Team Organization

The project delivery process must remain **agent-tool independent**.

The canonical project process is defined by:

- `.pi/team/README.md`
- `.pi/team/OPERATING_MODEL.md`
- `.pi/team/QUALITY_GATES.md`

Pi-specific adapter:

- `.pi/skills/team-delivery/SKILL.md`
- `.pi/agents/`

### Task classification

**Small task**

Examples: localized bug fix, documentation correction, isolated styling change.

- Use a single agent.
- Inspect affected code.
- Implement only authorized changes.
- Run focused validation.
- Report results.

A full multi-agent team is unnecessary.

**Medium task**

Examples: multi-file feature, UI workflow adjustment, API behavior change.

- Define scope and acceptance criteria.
- Review relevant architecture.
- Implement incrementally.
- Perform independent review when available.
- Validate affected behavior.
- Update handoff state.

**Large or architectural task**

Examples: Runtime changes, new execution workflows, cross-package redesigns.

- Follow the complete team delivery process.
- Establish requirements and architectural boundaries.
- Plan incremental milestones.
- Use independent Review and QA.
- Apply the defined quality gates.
- Preserve verifiable evidence and recovery instructions.

### Agent portability

- Prefer reusable repository instructions, contracts, and scripts over tool-specific behavior.
- Use real Pi subagents when available and appropriate.
- Other compatible agents may fulfill equivalent roles.
- If delegation is unavailable, explicitly operate sequentially.
- Never simulate independent reviewers or claim separate-agent verification that did not occur.
- Do not make successful delivery depend on a particular agent provider or multi-agent plugin.

Agent roles may assist development and review but cannot override platform invariants or human authorization boundaries.

## 7. Validation and Quality Gates

Use `.pi/team/QUALITY_GATES.md` as the authoritative source for project quality requirements.

For each milestone:

1. Identify affected functionality and regression risks.
2. Execute applicable focused tests, linting, and type checks.
3. Run integration or browser tests when behavior changes justify them.
4. Validate affected desktop viewports for UI changes.
5. Record actual command results and meaningful evidence.
6. Distinguish passed, failed, blocked, and not-executed checks.

### Evidence rules

- Do not fabricate test execution, screenshots, reviews, or PASS status.
- Never mark tests as passed when they were not executed.
- Do not convert a blocked or skipped verification into success.
- Existing test evidence may be reused only when relevant code and dependencies remain unchanged.
- Do not silently modify test assertions merely to obtain green results.
- Report known limitations and unverified assumptions.

Platform test outcomes remain under existing deterministic evaluation and human governance.

## 8. Git and Change Safety

Never execute without explicit authorization:

- `git push --force` or `git push --force-with-lease`
- `git reset --hard`
- `git clean -fd`
- Destructive branch operations
- Overwriting unrelated user changes
- Production deployment
- External write or destructive migration operations

Additional rules:

- Do not automatically commit, push, merge, tag, or deploy.
- Do not revert user modifications to repair unrelated failures.
- Inspect Git status before and after implementation.
- Keep changes focused, reviewable, and logically grouped.
- When commits are explicitly authorized, run relevant checks first.
- Never treat an untracked file as disposable without inspection.

## 9. Long-Running Task Handoff

For medium, large, or multi-session tasks, maintain:

`docs/agent-handoff.md`

Update the handoff after each meaningful, verifiable milestone and before anticipated context loss or interruption.

Required information:

- Current objective and authorized scope
- Git branch, HEAD commit, and relevant worktree state
- Completed changes and affected files
- Actual test commands and results
- Open issues and blockers
- Pending approvals or external dependencies
- Exact next actions and recovery commands

A newly started agent must:

1. Read this `AGENTS.md`.
2. Read the relevant project/team instructions.
3. Read `docs/agent-handoff.md` if present.
4. Verify Git status and relevant implementation.
5. Check whether recorded evidence still applies.
6. Continue from the last verified state, not from unsupported claims.

Chat history and temporary logs must not be the only source of progress.

Handoff documentation updates are allowed within an authorized development task, but must not be used to expand implementation scope.

## 10. Delivery Contract

Every completed development task must report:

**Changes**
- What changed and why.
- Key affected files.
- Any deviation from the original plan.

**Verification**
- Commands actually executed.
- Passed, failed, blocked, and unexecuted checks.
- Relevant desktop UI evidence where applicable.

**Risks**
- Known limitations, regressions, or unverified paths.
- Documentation/code discrepancies.
- Any approval required before the next step.

**Next step**
- The smallest actionable continuation, if work remains.

Do not report completion when acceptance criteria or mandatory quality gates are unmet.

---

## Instruction Precedence

When instructions conflict, apply this order:

1. Safety constraints and explicit human authorization boundaries
2. `docs/ROADMAP.md` §0 invariants
3. Repository architecture and verified code behavior
4. This `AGENTS.md`
5. Relevant project/team quality and design documents
6. Task-specific plans and agent-generated proposals

Verified code behavior determines what the system currently does; it does not automatically authorize violating documented invariants.

**Final principle:** Preserve safety and existing functionality, reuse established architecture, deliver bounded changes, and substantiate every completion claim with real evidence.
