# Engineering Decisions

## EORG-001 — Use project-local Pi Subagents, pinned

- **Status:** Accepted for this repository only.
- **Decision:** Install `npm:pi-subagents@0.82.1` in project `.pi/settings.json`, not in user settings. Pi 1.4.0 satisfies the package's declared Pi ≥1.2.0 requirement. NPM tarball metadata/source, entry point, manifest, dependencies, optional installer, and relevant runtime setup were inspected; tarball integrity was obtained from npm and `npm audit` reported 0 vulnerabilities. No lifecycle scripts were declared; the package's optional `install.mjs` bin was not executed.
- **Reason:** No subagent runtime was registered in the current parent session, while the candidate supports the installed Pi and successfully completed a real isolated `scout` child invocation.
- **Boundaries:** Project package only; no global settings/credentials changes. Project `.pi/settings.json` defaults to foreground execution, disables auto-resume, durable schedules and mission/workflow features; normal calls still pass `async:false` and fresh context explicitly. Do not use detached/background/resume loops. The current pre-install parent process must be restarted to gain the tool directly.
- **Risk:** Third-party extension code executes with Pi process privileges; a read-only role's tool allowlist is not OS sandboxing. Re-audit before upgrading.

## EORG-002 — Keep current handoff system canonical

- **Status:** Accepted.
- **Decision:** `.pi/team/` contains current organization, backlog, roadmap, decisions and quality gates; `docs/agent-handoff.md` remains the single durable checkpoint/recovery log. Do not create a second progress or release-report system.

## EORG-003 — No background company or unattended work

- **Status:** Accepted.
- **Decision:** The organization exists as project instructions, Pi profiles, skills, backlog and evidence—not an always-online service. No scheduled, detached, recursive, or post-session work is authorized. Stop after the pilot and wait for the user's next selected task.

## EORG-004 — Respect existing Graphite scope and Desktop First

- **Status:** Accepted.
- **Decision:** Keep Graphite Developer Studio as the approved direction for the currently implemented Dashboard and Workspace Debug/Explore surfaces. Preserve existing route-specific design elsewhere until approved; do not create a second global visual direction. Root `AGENTS.md` excludes mobile-specific development/testing and wins over historical mobile checklists in older docs.

## EORG-005 — Pilot is read-only unless evidence reproduces a defect

- **Status:** Accepted.
- **Decision:** Verify Dashboard execution → Run Results → Debug navigation using the current implementation and available isolated fixture. Do not modify product code just to manufacture a developer stage; if checks pass, close as a read-only validation pilot and record any missing real Runtime coverage separately.

## EORG-006 — Disable unattended Subagent behavior at project scope

- **Status:** Accepted.
- **Decision:** Set `asyncByDefault:false`, `autoResume:false`, disable durable schedules, mission/workflow-script features, and unused management/orchestration surfaces in project `.pi/settings.json`. Normal children still require an actual `async:false` call parameter and fresh context. Because mission support is disabled, no mission argument is available or needed. This reduces accidental background work while preserving bounded foreground delegation.
- **Reason:** First QA launch defaulted to detached asynchronous execution even though its task prose requested synchronous work. It completed safely, but the mismatch exposed a tool-call-level guardrail requirement. The independent review surfaced that the interim launch/status note did not retain the final QA result; durable evidence was added separately.
- **Limit:** These settings apply to new Pi sessions; they do not retrofit the already-running Pi parent or stop sessions launched before the change.


## EORG-007 — User-authorized Graphite fidelity scope extension (2026-10-27)

- **Status:** Accepted for the named fidelity task only.
- **Decision:** The current user request explicitly extends Direction A to Projects, Requirements, Test Explorer, Write Tests, Results, AI Repair, and Quality, in addition to Dashboard and Workspace Debug/Explore. This overrides EORG-004's earlier implementation-only boundary for `.ai-runs/2026-10-27-graphite-fidelity-recovery/`.
- **Constraints:** The approved Pencil frames still cover only Dashboard, Debug, and Explore. For the added views, preserve existing React structure/content/actions and use the existing Graphite shell/tokens; do not invent IA or alter runtime, deterministic verdict, human approval, API, or business semantics. The extension does not authorize unrelated routes or mobile-specific work.

## EORG-008 — Adopt self-ui-style across all desktop routes

- **Status:** Accepted by user m02786 (2026-11-05); supersedes EORG-004 and the route-scope limit in EORG-007 for the current visual direction.
- **Decision:** Extend the accepted Quality self-ui-style pilot to all desktop web routes, including Dashboard, Workspace Debug/Explore/browser modes and login. Use the cold dotted light canvas, purple emphasis, raised key controls/surfaces and compact small-radius geometry. Graphite is no longer a visual exception.
- **Boundaries:** Preserve route/query context, business layout and data, API contracts, authentication/permissions, i18n, deterministic Quality decisions, Runtime/Workspace state and keyboard/accessibility behavior. Keep dense tables/logs/editors flat and readable. Preserve the existing `light`/`dark`/`system` preference by mapping dark tokens inside `.ds-theme`; do not add a second global palette, change backend/runtime architecture, or develop mobile-specific UI. Existing `--graphite-*` names are temporary compatibility aliases for unmigrated selectors and must resolve directly to package tokens; new components must not use them and the aliases are removed after selector migration. Use official `@self/ui-style` tokens/classes/components; no global tag overrides or `!important` stack. No service management, commit, push, merge or deploy.
- **Reason:** User explicitly approved the entire system after accepting the Quality pilot. Independent Architecture and Design reviews confirmed the route contracts and recommended the shared shell → operational views → Dashboard → specialized Workspace/Canvas/Studio rollout.
- **Delivery addendum (2026-11-06, user m11894):** The user authorized categorizing the completed changes into commits and then a normal push after validation; this supersedes the commit/push boundary above for this delivery only. No merge or deploy.
