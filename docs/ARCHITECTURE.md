# AI QA Platform — Complete Architecture Reference

The AI QA Platform is a deterministic, enterprise-grade AI QA Engineering Platform built on a **Modular Monolith** architecture.

> **Architecture Overview**:
> - **Technical Architecture**: Detailed in this document (application layers, packages, data stores, worker nodes, and security boundaries).
> - **Product Architecture**: Described in [platform-v3-product-architecture.md](platform-v3-product-architecture.md) (Workspace, Live Workflow, Automation Studio, Library, and URL Context routing).
> - **Domain Entity Model**: Described in [PRODUCT_MODEL.md](PRODUCT_MODEL.md) (Project, Requirement, TestDesign, TestCase, Workspace, Run, Failure).

---

## 1. System Context & Component Architecture

```text
                                    ┌─────────────────────────────────────────────────────────────┐
                                    │                     USER & INTEGRATIONS                     │
                                    │  [Web SPA]   [Jira Sync]   [GitHub Webhooks]   [TestRail]   │
                                    └──────────────────────────────┬──────────────────────────────┘
                                                                   │ HTTP / SSE / REST
┌──────────────────────────────────────────────────────────────────▼──────────────────────────────────────────────────────────────────┐
│                                                      AI QA PLATFORM CORE API                                                        │
├──────────────────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────┬─────────────────────────┤
│  QA CORE                 │  EXECUTION RUNTIME       │  INTEGRATIONS            │  QUALITY INTELLIGENCE    │  ENTERPRISE & SECURITY  │
│  - Requirement & Design  │  - Pytest / Runner API   │  - GitHub PR Workflow    │  - Coverage Matrix       │  - RBAC & API Keys      │
│  - Test Case & Bindings  │  - SSE Live Output       │  - Jira Bi-directional   │  - Change Impact Analyz  │  - Immutable Audit Log  │
│  - Automation Studio V2  │  - Flaky Intelligence    │  - TestRail Sync         │  - Release Gating        │  - Distributed Workers  │
│  - Real Pytest Migration │  - Failure Diagnostician │  - Jenkins Webhooks      │  - Quality Risk Radar    │  - Docker / Prometheus  │
└────────────┬─────────────┴────────────┬─────────────┴────────────┬─────────────┴────────────┬─────────────┴────────────┬────────────┘
             │                          │                          │                          │                          │
┌────────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼────────────┐
│      PostgreSQL DB       │ │  Local Artifact Store  │ │   Distributed Workers  │ │  Multi-LLM AI Gateways │ │  External CI & Tools   │
│ (Relational Data & RBAC) │ │ (Traces, DOM, Videos)  │ │ (Playwright Multi-Node)│ │ (OpenAI/Claude/Gemini) │ │ (GitHub/Jira/Jenkins)  │
└──────────────────────────┘ └────────────────────────┘ └────────────────────────┘ └────────────────────────┘ └────────────────────────┘
```

---

## 2. Codebase Structure & Package Boundaries

The platform is structured into decoupled apps and packages:

- `apps/web`: React 19 + TypeScript + Vite frontend with Monaco Editor, Live Browser CDP stream, and deep link URL Context.
- `apps/api`: FastAPI domain services, REST endpoints, WebSocket transports, and SQLAlchemy async persistence.
- `apps/worker`: Daemon worker processes (`worker/daemon.py`) for distributed test execution and job claiming.
- `packages/qa-core`: Core testing contracts, `PytestRunner`, sensitive redaction, grounding verification, and failure evidence extraction. Free from FastAPI and DB dependencies.
- `packages/project-model`: Shared Pydantic domain models, SQLAlchemy ORM entities, and `TaskType` definitions.
- `packages/integrations`: Connectors and integration adapters (GitHub, Jira, TestRail, Jenkins).
- `packages/platform-config`: Central configuration loader for `config/config.yaml` with typed schemas and secret redaction.
- `runtime/`: Editable project workspaces (`runtime/workspaces/`) and test run artifacts (`runtime/artifacts/`). Never committed to Git.

---

## 3. Guiding Architectural Principles

1. **Deterministic Test Oracles**: Test verdicts (`PASSED`, `FAILED`, `SKIPPED`) are determined solely by pytest exit codes and runtime assertions. AI assists with analysis, diagnosis, and repair proposals, but never decides verdicts or masks regressions.
2. **Preview-First Philosophy**: All external modifications (Jira tickets, TestRail results, code repairs) require preview and explicit human approval prior to mutation.
3. **No Unattended Agent Loops**: Automation is bounded, reviewable, and reversible. No unattended loops modify code or execute against customer systems.
4. **Single Source of Truth**: Code in the workspace is the authority for automation; database models store business entities and metadata.

---

## 4. Historical Roadmap & Phase Capabilities (v0.1.0 - v1.0.0)

For historical reference and milestone tracing, capabilities were delivered across numbered phases:

| Phase | Subsystem | Key Capabilities |
|---|---|---|
| **Phase 1** | Platform Foundation | Project models, Test Design, Test Case, Automation code bindings |
| **Phase 2** | Automation Studio V2 | Monaco Code Editor, Test Explorer tree, Problems panel, Git Diff view |
| **Phase 3** | Real QA Core Migration | Replacement of mock orchestrators with real Pytest runner |
| **Phase 4** | Test Execution Platform | Real-time SSE live stream output, Execution Run records, Step telemetry |
| **Phase 5** | Production AI Provider | Multi-provider router, budget limits, invocation auditing |
| **Phase 6** | Flaky & Failure Intelligence | Heuristic & AI root cause diagnosis, locator repair proposal, human review & apply |
| **Phase 7** | Multi-Runner CI Platform | Jenkins CI build triggering, webhook callback listeners, runner dispatch |
| **Phase 8** | GitHub / PR Workflow | PR test summary publisher, checks aggregator, GitHub PR auto-diagnostics |
| **Phase 9** | Jira & TestRail Integration | Bi-directional requirement sync, preview-first bug creation, TestRail result sync |
| **Phase 10** | Quality Intelligence & Gating | Multi-dimensional coverage score, risk radar matrix, change impact analysis, release gates |
| **Phase 11** | Identity, RBAC & Security | 4-tier Role Based Access Control (`ADMIN`, `QA_LEAD`, `QA_ENGINEER`, `VIEWER`), API Key generator, secret masking |
| **Phase 12** | Distributed Execution Grid | Scalable worker nodes, heartbeat liveness, browser capability matching, local artifact storage |
| **Phase 13** | Production Deployment & Ops | Multi-stage Dockerfiles, Docker Compose stack, Prometheus metrics, backup/restore runbooks |
| **Phase 13.5/14** | Architecture Stabilization | Central authorization guard, real project onboarding, bounded AI grounding context, routed UI |
