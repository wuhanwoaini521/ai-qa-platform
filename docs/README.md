# AI QA Platform — Documentation Portal

Welcome to the AI QA Platform technical documentation hub. This index is the single source of truth for platform architecture, development workflows, runtime execution, and historical audit baselines.

---

## 📌 Document Classification & Lifecycle Status

Every document in this repository belongs to one of three lifecycle categories:

- `[CURRENT]`: Active, authoritative specification or operational guide reflecting current code reality.
- `[HISTORICAL]`: Immutable audit report, historical acceptance baseline, or post-incident evidence. Retained for compliance and tracking; not to be used as current functional specification.
- `[PLANNED]`: Future roadmap milestones and design drafts not yet implemented in production.

---

## 🏛 1. Architecture & Domain Model

| Document | Status | Description |
|---|:---:|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | `[CURRENT]` | Platform technical architecture: Modular Monolith, package boundaries, API, database, and security boundaries. |
| [platform-v3-product-architecture.md](platform-v3-product-architecture.md) | `[CURRENT]` | Product architecture: Workspace (`/workspace/:id`), Live Workflow (`/workflow`), Studio (`/studio`), and URL Context routing. |
| [PRODUCT_MODEL.md](PRODUCT_MODEL.md) | `[CURRENT]` | Core domain entity model (Project, Requirement, TestDesign, TestCase, Workspace, Run, Failure) and ER diagram. |
| [WORKSPACE_MODEL.md](WORKSPACE_MODEL.md) | `[CURRENT]` | Workspace filesystem philosophy, project checkouts, directory layout (`tests/`, `pages/`), and path traversal confinement. |
| [QA_CORE.md](QA_CORE.md) | `[CURRENT]` | Domain boundary and package responsibilities for `packages/qa-core`. |

---

## 🔄 2. Workflows & Runtime Execution

| Document | Status | Description |
|---|:---:|---|
| [PLATFORM_WORKFLOW.md](PLATFORM_WORKFLOW.md) | `[CURRENT]` | The end-to-end `Workspace → Case → Automation → Run → Failure → AI/Jev Repair` primary engineering pipeline. |
| [PLATFORM_RUNTIME_GUIDE.md](PLATFORM_RUNTIME_GUIDE.md) | `[CURRENT]` | Unified test execution platform: PytestRunner, SSE streaming, CDP screencasting, cancellation, debugpy DAP debugger, and stable test identity. |
| [DISTRIBUTED_EXECUTION.md](DISTRIBUTED_EXECUTION.md) | `[CURRENT]` | Distributed runner grid: worker node lifecycle, heartbeat protocol, job claiming, and runner backends (Local/Jenkins). |
| [TASK_RUNTIME_INFORMATION_ARCHITECTURE.md](TASK_RUNTIME_INFORMATION_ARCHITECTURE.md) | `[CURRENT]` | Task Runtime information architecture, `TaskType` enum mapping, approval checkpoints, and task execution lifecycle. |

---

## 🤖 3. Autonomous QA Agent & Browser Action Orchestration

| Document | Status | Description |
|---|:---:|---|
| [autonomous-qa-agent-v1.md](autonomous-qa-agent-v1.md) | `[CURRENT]` | Autonomous QA Agent: `QA_GOAL` preview token flow, capability matrix, execution constraints, pause/resume, and result contract. |
| [jev-browser-orchestration-v1.md](jev-browser-orchestration-v1.md) | `[CURRENT]` | JEV browser action loop: observation, candidate selection, safety boundaries, and live execution. |
| [QUALITY_DISCOVERY.md](QUALITY_DISCOVERY.md) | `[CURRENT]` | Quality Discovery live engine: real-browser observation, live frames, element geometry + on-page highlights, event contract, AI degradation, and the exploration security boundary. |
| [RC_ACCEPTANCE.md](RC_ACCEPTANCE.md) | `[CURRENT]` | Release Candidate acceptance report (six phases: wind-down, real-QA-engineer UI walkthrough, stability, enterprise gate, UX fixes, final gates) with per-SHA evidence and a PASS/PARTIAL/FAIL verdict. |

---

## 🧠 4. AI & Decision Providers

| Document | Status | Description |
|---|:---:|---|
| [AI_PROVIDER.md](AI_PROVIDER.md) | `[CURRENT]` | AI provider system: OpenAI-compatible, Fallback, Fake provider, prompt registry, budget guard, and OpenCode session gateway. |
| [DECISION_LAYER.md](DECISION_LAYER.md) | `[CURRENT]` | Structured decision service: Jev / System One provider, Fernet encryption, advisory signals, offline evaluator, and sample schemas. |
| [FAILURE_INTELLIGENCE.md](FAILURE_INTELLIGENCE.md) | `[CURRENT]` | Failure taxonomy classification, SensitiveRedactor sanitization, Jev locator repair proposals, Playwright verification, and human approval. |
| [FLAKY_INTELLIGENCE.md](FLAKY_INTELLIGENCE.md) | `[CURRENT]` | Deterministic flaky scoring formula ($S \in [0.0, 1.0]$), sample protection, classification states, and no-auto-skip policy. |

---

## 🛠 5. Authoring & Recording Tools

| Document | Status | Description |
|---|:---:|---|
| [AUTOMATION_STUDIO.md](AUTOMATION_STUDIO.md) | `[CURRENT]` | In-browser Monaco IDE, AST problems panel, Pytest explorer, QA Assistant sidecar, and debugpy DAP debugging. |
| [BROWSER_RECORDER.md](BROWSER_RECORDER.md) | `[CURRENT]` | Live browser recording via WebSocket, Playwright Chromium, element evidence bundles, and network proxy configuration. |
| [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md) | `[CURRENT]` | Web UI design system: color/spacing tokens, shared components, responsive breakpoints (1050px, 760px, 520px), and accessibility. |

---

## 🔒 6. Enterprise Security, Configuration & Operations

| Document | Status | Description |
|---|:---:|---|
| [SECURITY.md](SECURITY.md) | `[CURRENT]` | Authentication (Bearer / API Keys), secret masking, path traversal protection, and immutable `security_audits` / `integration_audits`. |
| [RBAC.md](RBAC.md) | `[CURRENT]` | Role-Based Access Control: 4-tier roles (`ADMIN`, `QA_LEAD`, `QA_ENGINEER`, `VIEWER`), permissions matrix, and central `authz.py` enforcement. |
| [CONFIGURATION.md](CONFIGURATION.md) | `[CURRENT]` | Central runtime configuration: `config/config.yaml`, environment variable precedence, schema validation, and dynamic reload API. |
| [DEVELOPMENT.md](DEVELOPMENT.md) | `[CURRENT]` | Developer guide: `mise` toolchain (Python 3.13, Node 24, uv, pnpm), entry points, test commands, and i18n rules. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | `[CURRENT]` | Production deployment: Docker Compose, reverse proxy buffering rules (SSE), and Kubernetes/Helm strategy. |
| [OPERATIONS.md](OPERATIONS.md) | `[CURRENT]` | Production operations: Prometheus metrics (`/api/metrics`), alerting rules, and incident runbooks. |
| [BACKUP_RESTORE.md](BACKUP_RESTORE.md) | `[CURRENT]` | Database automated backup (`scripts/backup_db.sh`), restore runbook, and artifact storage backup. |
| [ARTIFACT_STORAGE.md](ARTIFACT_STORAGE.md) | `[CURRENT]` | Local artifact store and retrieval API. |

---

## 🔌 7. External Integrations

| Document | Status | Description |
|---|:---:|---|
| [JIRA_INTEGRATION.md](JIRA_INTEGRATION.md) | `[CURRENT]` | Bidirectional Jira integration: user story import, preview-first bug drafting, and `integration_audits`. |
| [TESTRAIL_INTEGRATION.md](TESTRAIL_INTEGRATION.md) | `[CURRENT]` | TestRail integration: test case linking, preview-first result publishing, and status code mapping. |
| [GITHUB_INTEGRATION.md](GITHUB_INTEGRATION.md) | `[CURRENT]` | GitHub PR workflow: Git safety invariants, `PullRequestAdapter`, and check run integration. |
| [JENKINS_INTEGRATION.md](JENKINS_INTEGRATION.md) | `[CURRENT]` | Jenkins CI runner backend, parameter mapping, and `FakeJenkinsServer` transport. |

---

## 🗺 8. Product Roadmap

| Document | Status | Description |
|---|:---:|---|
| [ROADMAP.md](ROADMAP.md) | `[CURRENT]` / `[PLANNED]` | Platform safety invariants, shipped capabilities, in-progress items, planned v1.1-v2.0 milestones, and explicitly rejected anti-patterns. |

---

## 📜 9. Historical Audits & Acceptance Evidence

All historical audit baselines and acceptance reports are retained to provide full auditability and traceability:

### Root & System Audits (`docs/audits/`)
- [docs/audits/ai-jev-architecture-audit.md](audits/ai-jev-architecture-audit.md) `[HISTORICAL]`: AI + Jev architecture audit & live acceptance (2026-10-07 / 2026-10-08).
- [docs/audits/runtime-hardening-baseline.md](audits/runtime-hardening-baseline.md) `[HISTORICAL]`: Runtime reliability hardening baseline (2026-10-10 at `0bed9db2`).
- [docs/audits/overnight-final-acceptance.md](audits/overnight-final-acceptance.md) `[HISTORICAL]`: Phase 0-8 overnight acceptance (2026-10-10 at `7108b08`, PARTIAL).
- [docs/audits/full-product-feature-inventory.md](audits/full-product-feature-inventory.md) `[HISTORICAL]`: Product feature inventory baseline (2026-10-11 at `cdf954a`).
- [docs/audits/full-product-final-acceptance.md](audits/full-product-final-acceptance.md) `[HISTORICAL]`: Product final acceptance (2026-10-11 at `cdf954a`, PARTIAL).
- [docs/audits/full-product-test-results.md](audits/full-product-test-results.md) `[HISTORICAL]`: Full product automated test results baseline (2026-10-11 at `cdf954a`).
- [docs/audits/full-product-ux-audit.md](audits/full-product-ux-audit.md) `[HISTORICAL]`: Full product UX & Chrome layout audit (2026-10-11).
- [docs/audits/full-product-fix-log.md](audits/full-product-fix-log.md) `[HISTORICAL]`: Full product fix log for mobile navigation (2026-10-11).
- [docs/audits/playwright-golden-journey-acceptance.md](audits/playwright-golden-journey-acceptance.md) `[HISTORICAL]`: Playwright golden journey acceptance (2026-10-11, PARTIAL).

### Nightly & Version Audits (`reports/`)
- [reports/v2/product-audit/REPORT.md](../reports/v2/product-audit/REPORT.md) `[HISTORICAL]`: V2 live product audit (2026-10-12 at `a0b4976`).
- [reports/nightly/FINAL_REPORT.md](../reports/nightly/FINAL_REPORT.md) `[HISTORICAL]`: Nightly platform improvement final report (2026-10-11, PARTIAL).
- [reports/nightly/ARCHITECTURE_AUDIT.md](../reports/nightly/ARCHITECTURE_AUDIT.md) `[HISTORICAL]`: Nightly architecture audit (2026-10-11 at `cdf954a`, PARTIAL / B).
- [reports/nightly/ACCESSIBILITY_AND_UX.md](../reports/nightly/ACCESSIBILITY_AND_UX.md) `[HISTORICAL]`: Accessibility and UI review (2026-10-11).
- [reports/nightly/HANDOFF.md](../reports/nightly/HANDOFF.md) `[HISTORICAL]`: Nightly improvement branch handoff (2026-10-11).
