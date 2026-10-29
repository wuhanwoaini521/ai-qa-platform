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

## EORG-008 — Portable team and knowledge adapter boundary (2026-10-28)

- **Status:** Accepted for this mission's bounded team/knowledge work.
- **Decision:** Keep the existing synchronous Pi Subagents runtime and existing role profiles. Add only missing Scout, Knowledge Curator, and Architecture Critic adapters. Define tool-independent role contracts under `engineering-knowledge/team-definition.md`; keep Pi frontmatter/tool mappings under `.pi/agents/`. Store reusable factual records as Markdown in `engineering-knowledge/`; do not add a vector database, new agent platform, daemon or scheduler.
- **Safety:** All roles remain bounded by the human authority, deterministic verdict, preview-before-write, no duplicate Runtime/Agent/Provider, concurrency and stop rules. Pi tool allowlists are not sandboxes. The package remains exactly pinned at 0.82.1; automatic preflight remains disabled, so manual release preview is mandatory.

## EORG-009 — Keep Candidate A as current baseline; defer broad architecture gate

- **Status:** Proposed operational disposition; architecture gate remains DEFERRED / NOT PASSED.
- **Decision:** Keep existing Task Runtime, BrowserRuntime, DecisionService, providers and deterministic Pytest. Apply only the reproduced local Quality Discovery recovery state/event correction using the existing versioned ORM. Do not implement a normalized cross-domain execution/event store, add a framework dependency, or replace a browser/runtime owner until a human-approved architecture gate follows comparative evidence.
- **Evidence boundary:** P0 releases/licenses/manifests have source verification; candidate compatibility and execution are not tested. The narrow recovery regression passes SQLite and isolated PostgreSQL 18.6; production PG16/multi-process guarantees remain unverified. See `docs/architecture-review/architecture-debate-2026-10-28.md` and `engineering-knowledge/decisions/ADR-002-keep-existing-runtime.md`.

## EORG-010 — Safe fallback and preview-first delivery workflow

- **Status:** Accepted for the authorized bounded R&D mission.
- **Decision:** Before marking an applicable quality gate blocked due to unavailable infrastructure, document a safe, pinned temporary alternative and seek/confirm explicit authorization for provisioning. For approved external GitHub writes, inspect the exact staged file set and prepare a human-readable push/Draft PR preview; verify branch ancestry, remote state and existing PR status first.
- **Constraints:** No force push, merge, deployment, production write, broad dependency change, or secret-bearing artifact. Stop if the branch cannot advance by a normal fast-forward or the file preview differs from authorization. This procedure does not turn local integration tests into production equivalence or pass any architecture gate.
- **Evidence:** `.pi/team/QUALITY_GATES.md`, `.pi/team/OPERATING_MODEL.md`, `.pi/skills/team-delivery/SKILL.md`, and the current mission handoff.
