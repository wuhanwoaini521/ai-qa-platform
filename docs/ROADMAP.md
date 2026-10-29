# AI QA Platform — Engineering Roadmap

This document outlines platform safety invariants, shipped capabilities, in-progress work, planned milestones, and explicitly rejected anti-patterns.

---

## 0. Platform Safety Invariants (non-negotiable)

Every capability — shipped, in-progress, or planned — must respect these invariants. An item that violates them is a bug in the roadmap.

1. **AI never decides PASS / FAIL.** Test verdicts come from real test execution exit codes only. AI may summarize, classify, and explain; it may never override a verdict or declare a failing test passing.
2. **AI never mutates code without explicit human approval.** Repair flows end in a *proposal* + *diff*; a human applies it. There is no confidence threshold high enough to skip review.
3. **Determinism over autonomy.** Test selection, gating, and coverage are computed from recorded execution data, not from model judgement. Model output is advisory metadata.
4. **Preview before external mutation.** Jira, TestRail, GitHub, and Jenkins writes are preview-first and require explicit confirmation flags.
5. **No unattended agent loops** against customer systems. Automation is bounded, reviewable, and reversible.
6. **No secondary Runtime / Agent / Provider layers.** New capabilities must compose the existing `DecisionService`, `TaskRuntimeService`, and `BrowserRuntime`.

---

## 1. Shipped Capabilities (v0.1.0 – v1.0.0 & V3/V3.1)

- [x] **Automation Studio V2**: In-browser Monaco IDE, AST syntax validation, Problems panel, test tree explorer, and `debugpy` DAP debugger.
- [x] **Deterministic Pytest Execution Engine**: Subprocess execution, real-time SSE log chunk streaming, and exit-code verdict enforcement.
- [x] **Live Browser Telemetry**: Chromium CDP screencast event streaming over SSE, per-worker telemetry tabs, and stream ticket authentication.
- [x] **Failure Intelligence & Human-in-the-Loop Healing**: Structured taxonomy classification, SensitiveRedactor sanitization, Jev candidate selection, Playwright verification, diff preview, and exact-nodeid rerun verification.
- [x] **Autonomous QA Agent & Browser Action Orchestration**: `QA_GOAL` preview token flow, `EXPLORE_PAGE` browser observation loop, action safety classification, pause/resume, and result contract.
- [x] **Workspace & Live Workflow (V3/V3.1)**: Unified `Workspace → Case → Automation → Run → Failure → AI/Jev Repair` lifecycle with deep-link URL Context and Live Workflow DAG.
- [x] **Decision Layer (Jev / System One)**: Decoupled structured decision service, Fernet encryption of secrets, runtime health checks, and advisory signal evaluation.
- [x] **Quality Intelligence & Flaky Scoring**: Multi-dimensional coverage calculation (Requirement, Automation, Execution), deterministic flaky scoring formula, risk radar matrix, and release gating.
- [x] **Enterprise Integrations**: Bidirectional Jira requirement import & bug drafting, TestRail result sync, GitHub PR check runs, Jenkins remote runner.
- [x] **Enterprise RBAC & Security**: 4-tier role hierarchy, API key generator, path traversal prevention, and immutable `security_audits` / `integration_audits`.
- [x] **Distributed Worker Daemon**: Scalable worker nodes, heartbeat telemetry, job queue claiming, and capability matching.
- [x] **Production Operations**: Multi-stage Docker Compose, Prometheus `/api/metrics`, and backup/restore automation scripts.

---

## 2. In-Progress & Partial Capabilities

- [ ] **PostgreSQL Production Lane Validation**: SQLite runtime is 100% verified locally; PostgreSQL migrations and schemas are implemented, but live PostgreSQL CI lane requires dedicated environment provisioning.
- [ ] **Cross-Process Browser Session Takeover**: Recorder drafts persist in local storage; resuming live browser instances across API server restarts remains in progress.
- [ ] **S3 / MinIO Object Storage Client**: Storage schemas and Docker MinIO provisioning exist; native S3 upload/download client implementation is pending.

---

## 3. Planned Milestones (v1.1 – v2.0)

### Near-Term (v1.1 - v1.2)
- [ ] **Visual Regression with Explicit Review**: Computer-vision diffing for Playwright screenshot comparisons, with deterministic region masking (ignore timestamps, dynamic banners) and a human-approved baseline update step.
- [ ] **Assisted Locator Repair — Batch Review**: Bulk review of repair candidates across multiple test failures, side-by-side diff previews, and a one-click human-approved patch. *No auto-apply.*
- [ ] **Multi-Tenant Organization Support**: Data partitioning per organization, custom domains, and SAML 2.0 / Okta SSO.
- [ ] **Deterministic Regression Selection**: Expand change-impact analysis so regression scope is derived from recorded executions, bindings, and git changed files — never from model judgement.

### Mid-Term (v1.3 - v2.0)
- [ ] **AI Test Case Drafting from Figma & Storybook**: Ingest design tokens and UI mockups to produce draft Gherkin scenarios and Playwright skeletons for human adoption.
- [ ] **Multi-Region Runner Mesh**: Geo-distributed worker clusters with latency-aware scheduling of already-defined jobs (scheduling only; verdicts stay deterministic).
- [ ] **Flaky Root-Cause Mining**: Statistical analysis over execution history to attribute flakiness to environment, timing, or locator instability.

---

## 4. Explicitly Rejected & Prohibited Anti-Patterns

- **Unattended Code Modification**: Bypassing human approval for code edits under any confidence threshold is strictly forbidden.
- **AI-Determined Test Verdicts**: AI overriding pytest exit codes, masking failures, or declaring broken tests as passing is strictly forbidden.
- **Duplicate Runtime / Agent Frameworks**: Creating secondary planner agents, shadow event streams, or unpersisted execution loops outside `TaskRuntimeService` is strictly forbidden.

---

## 5. Autonomous R&D Mission Status (2026-10-28)

This status supplements the product roadmap; it does **not** alter §0 invariants or pass the Architecture Gate.

| Workstream | Status | Evidence / remaining gate |
|---|---|---|
| Pi team and portability | PARTIAL | Existing `pi-subagents@0.82.1` team and portable role contracts retained; new Scout/Curator/Critic adapters and workflow guidance added. Independent final configuration review remains pending. |
| Engineering Knowledge Base | PARTIAL | Markdown index and source-linked records added. Scout → Curator → independent consumer reuse experiment succeeded on the pinned SQLAlchemy versioning topic; broader portability remains pending. |
| P0 official framework research | SOURCE VERIFIED / EXECUTION NOT VERIFIED | LangGraph 1.2.18 (MIT), Browser Use 0.13.14 (MIT), Skyvern v1.0.56 (AGPL-3.0) tag/license/manifest facts recorded. No compatibility run, installation, browser comparison, provider call or legal assessment. |
| Architecture debate | DEFERRED | One independent challenge round; keep current runtime owners and Candidate A as operating baseline. Candidate B remains provisional. **Architecture Gate DEFERRED / NOT PASSED.** |
| Execution Core — Discovery recovery | PARTIAL | The 15-case focused suite passed on SQLite and disposable PostgreSQL 18.6 for this narrow state/event path. This does not validate production PostgreSQL 16 or multi-process API ownership. |
| Sprint A — lifecycle | PARTIAL | Targeted Discovery/Task mapping and stale-scan recovery tests pass on SQLite and PostgreSQL 18.6; the full Task/TestRun/Discovery state matrix and API-wide unification remain incomplete. |
| Sprint B — events/evidence | PARTIAL | Recovery pause event commits atomically with its local state transition; rollback/failure cases pass on both tested databases. No general event/evidence contract or cross-process order guarantee is established. |
| Sprint C — Worker reliability | PARTIAL | SQLite/PostgreSQL 18.6 tests cover crash recovery, cancellation, timeout, late/duplicate result rejection and two concurrent Worker subprocesses. No lease/fencing generation or stale-worker reassignment guarantee is established. |
| Sprint D — Frontend consistency | PARTIAL | 17 targeted Node status/live-model tests pass; no UI source changed. Full Web suite/build/lint/typecheck and desktop browser acceptance were not run. |
| Sprint E — browser-agent comparison | BLOCKED / NOT RUN | No local model endpoint or explicit provider cost cap was available. Browser Use/Skyvern remain uninstalled and unexecuted; Skyvern legal review and candidate compatibility gates remain open. |

See `docs/architecture-review/architecture-debate-2026-10-28.md`, `docs/architecture-review/framework-p0-verification-2026-10-28.md`, `engineering-knowledge/index.md`, and the current Mission entry in `docs/agent-handoff.md`. Local PostgreSQL 18.6 checks do not validate production PostgreSQL 16 or multi-API recovery. Do not report the overall mission as complete until all required gates pass; an unavailable legal/runtime environment is BLOCKED, not PASS.
