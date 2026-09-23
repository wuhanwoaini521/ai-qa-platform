# AI QA Platform — Complete Architecture Reference

The AI QA Platform is a deterministic, enterprise-grade AI QA Engineering Platform built on a Modular Monolith architecture.

---

## 1. System Context & Component Architecture

```
                                    ┌─────────────────────────────────────────────────────────────┐
                                    │                     USER & INTEGRATIONS                     │
                                    │  [Web SPA]   [Jira Sync]   [GitHub Webhooks]   [TestRail]   │
                                    └──────────────────────────────┬──────────────────────────────┘
                                                                   │ HTTP / SSE / REST
┌──────────────────────────────────────────────────────────────────▼──────────────────────────────────────────────────────────────────┐
│                                                      AI QA PLATFORM CORE API                                                        │
├──────────────────────────┬──────────────────────────┬──────────────────────────┬──────────────────────────┬─────────────────────────┤
│  PHASE 1-3: QA CORE      │  PHASE 4-7: EXECUTION    │  PHASE 8-9: WORKFLOWS    │  PHASE 10: QUALITY INTEL │  PHASE 11-13: ENTERPRISE│
│  - Requirement & Design  │  - Pytest / Runner API   │  - GitHub PR Workflow    │  - Coverage Matrix       │  - RBAC & API Keys      │
│  - Test Case & Bindings  │  - SSE Live Output       │  - Jira Bi-directional   │  - Change Impact Analyz  │  - Immutable Audit Log  │
│  - Automation Studio V2  │  - Flaky Intelligence    │  - TestRail Sync         │  - Release Gating        │  - Distributed Workers  │
│  - Real Pytest Migration │  - Failure Diagnostician │  - Jenkins Webhooks      │  - Quality Risk Radar    │  - Docker / Prometheus  │
└────────────┬─────────────┴────────────┬─────────────┴────────────┬─────────────┴────────────┬─────────────┴────────────┬────────────┘
             │                          │                          │                          │                          │
┌────────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼─────────────┐ ┌──────────▼────────────┐
│      PostgreSQL DB       │ │   MinIO / S3 Storage   │ │   Distributed Workers  │ │  Multi-LLM AI Gateways │ │  External CI & Tools   │
│ (Relational Data & RBAC) │ │ (Traces, DOM, Videos)  │ │ (Playwright Multi-Node)│ │ (OpenAI/Claude/Gemini) │ │ (GitHub/Jira/Jenkins)  │
└──────────────────────────┘ └────────────────────────┘ └────────────────────────┘ └────────────────────────┘ └────────────────────────┘
```

---

## 2. Phase-by-Phase Platform Capability Matrix

| Phase | Subsystem | Key Capabilities |
|---|---|---|
| **Phase 1** | Platform Foundation | Project models, Test Design, Test Case, Automation code bindings |
| **Phase 2** | Automation Studio V2 | Monaco Code Editor, Test Explorer tree, Problems panel, Git Diff view |
| **Phase 3** | Real QA Core Migration | Seamless replacement of mock orchestrators with real Pytest runner |
| **Phase 4** | Test Execution Platform | Real-time SSE live stream output, Execution Run records, Step telemetry |
| **Phase 5** | Production AI Provider | Multi-provider router (OpenAI, Anthropic, Gemini, Mock), monthly budget limits, audit log |
| **Phase 6** | Flaky & Failure Intelligence | Heuristic & AI root cause diagnosis, locator repair proposal, human review & apply |
| **Phase 7** | Multi-Runner CI Platform | Jenkins CI build triggering, webhook callback listeners, runner dispatch |
| **Phase 8** | GitHub / PR Workflow | PR test summary publisher, checks aggregator, GitHub PR auto-diagnostics |
| **Phase 9** | Jira & TestRail Integration | Bi-directional requirement sync, preview-first bug creation, TestRail result sync |
| **Phase 10** | Quality Intelligence & Gating | Multi-dimensional coverage score, risk radar matrix, change impact analysis, release gates |
| **Phase 11** | Identity, RBAC & Security | 4-tier Role Based Access Control (`ADMIN`, `QA_LEAD`, `QA_ENGINEER`, `VIEWER`), API Key generator, secret masking |
| **Phase 12** | Distributed Execution Grid | Scalable worker nodes, heartbeat liveness, browser capability matching, S3 artifact storage |
| **Phase 13** | Production Deployment & Ops | Multi-stage Dockerfiles, Docker Compose stack, Prometheus metrics, backup/restore runbooks |

---

## 3. Guiding Architectural Principles

1. **Deterministic Test Oracles**: AI assists with test generation, locator repair proposals, and root cause analysis, but never fakes or overrides test execution results.
2. **Preview-First Philosophy**: External modifications (Jira tickets, TestRail updates, locator modifications) require deterministic preview and human approval prior to mutation.
3. **Modular Monolith**: Clean separation of packages (`qa-core`, `project-model`, `integrations`) ensuring high testability, local development speed, and ease of horizontal worker scaling.
