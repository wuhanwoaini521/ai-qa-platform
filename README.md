# AI QA Platform

> An Enterprise-Grade, Browser-Based AI Quality Engineering Platform covering the complete QA lifecycle.

[![CI](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/wuhanwoaini521/ai-qa-platform)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🎯 What It Is

**AI QA Platform** is an end-to-end, deterministic Quality Engineering platform that eliminates constant context-switching between IDEs, terminals, test case management systems, CI runners, and AI chat interfaces.

```text
Requirement Management (Jira / Local)
      ↓
Test Design & Scenario Generation
      ↓
Test Case Structuring & Matrix
      ↓
AI / Manual Automation Authoring & Binding
      ↓
Code Editing in Automation Studio V2 (Monaco + AST + Explorer)
      ↓
Distributed Test Runner Execution & Live SSE Streaming
      ↓
Live Test Outcome & Multi-Artifact Capture (Traces / DOM / Allure)
      ↓
Failure Classification & AI Root-Cause Diagnosis
      ↓
Locator Repair Proposal (AI) & Human-Approved Diff Patching
      ↓
Quality Intelligence, Risk Radar & Release Gate Enforcement
      ↓
Bi-directional Sync (GitHub PR Summary / Jira Bug / TestRail)
```

---

## 🚀 Key Platform Features (Phases 1 — 13)

- **Phase 1: Platform Foundation** — Requirements, Test Designs, Test Cases, and Automation Binding models.
- **Phase 2: Automation Studio V2** — Multi-tab Monaco editor with dirty tracking, AST syntax validator, Pytest explorer tree, and QA Assistant sidecar.
- **Phase 3: Real QA Core Migration** — Real Pytest execution engine, safe subprocess sandboxing, and deterministic exit code verdicts.
- **Phase 4: Test Execution Platform** — Real-time Server-Sent Events (SSE) live streaming of stdout/stderr and telemetry.
- **Phase 5: Production AI Provider** — Pluggable multi-model inference router (OpenAI, Anthropic, Gemini, Mock) with monthly budgets and audit logs.
- **Phase 6: Flaky & Failure Intelligence** — Heuristic & AI root cause diagnosis, locator repair proposal, human review & apply.
- **Phase 7: Jenkins / Multi-Runner Platform** — Trigger remote Jenkins jobs and consume asynchronous test report webhooks.
- **Phase 8: GitHub / PR Engineering Workflow** — Automated PR check run aggregation, PR test summary comments, and failure diagnosis.
- **Phase 9: Jira & TestRail Integration** — Bi-directional requirement sync, preview-first bug creation, and TestRail case result publisher.
- **Phase 10: Quality Intelligence & Gating** — Multi-dimensional coverage score, quality risk matrix, git change impact analysis, and release gates.
- **Phase 11: Enterprise RBAC, Security & Audit** — 4-tier Role Based Access Control (`ADMIN`, `QA_LEAD`, `QA_ENGINEER`, `VIEWER`), API keys, and immutable security audit trails.
- **Phase 12: Distributed Execution Platform** — Multi-node worker registry with heartbeat liveness, browser capability matching, and local artifact storage (S3/MinIO object storage is reserved, not implemented).
- **Phase 13: Production Deployment & Operations** — Multi-stage Dockerfiles, Docker Compose stack, Prometheus metrics, backup/restore runbooks, and zero-downtime health probes.
- **Phase 13.5: Architecture Stabilization** — feature-based frontend modularization, routed application shell, PostgreSQL parity in CI, central route authorization, dead-code removal, audit-driven defect fixes.
- **Phase 14: Real-Project Pilot** — detect, import and pilot an existing pytest/Playwright repository in isolation: structured collection, test identity, safety-checked execution, rerun and xdist accounting, Allure import, and failure diagnosis on real runs.

---

## 🏗 System Architecture

```text
ai-qa-platform/
├── apps/
│   ├── web/                     # React 19 + TypeScript + Vite + react-router + Monaco Editor V2 + Nginx
│   ├── api/                     # FastAPI + Pydantic + SQLAlchemy Async (Postgres/SQLite)
│   └── worker/                  # Distributed Playwright test runner daemon
├── packages/
│   ├── qa-core/                 # Core testing contracts, PytestRunner, Classifier & Healer
│   ├── project-model/           # Shared Pydantic domain models & database entities
│   └── integrations/            # Connectors (GitHub, Jira, TestRail, Jenkins)
├── docs/                        # Complete architecture, operations & workflow guides
├── runtime/                     # Isolated project workspaces & test artifacts
├── scripts/                     # Unified dev, test, lint, backup, and deploy commands
└── docker-compose.yml           # Complete containerized production stack
```

---

## ⚡️ Quick Start

### 1. Docker Compose (Production Stack)

```bash
# Clone repository
git clone git@github.com:wuhanwoaini521/ai-qa-platform.git
cd ai-qa-platform

# Copy environment template
cp .env.example .env

# Set a real APP_SECRET_KEY (openssl rand -hex 32) and keep AUTH_REQUIRED=true.

# Deploy stack with 2 distributed test runner nodes
./scripts/deploy.sh --build --scale-workers 2
```

- **Web Application**: [http://localhost:3000](http://localhost:3000) — sign in with the seeded
  administrator (`admin@ai-qa.local` / `adminpassword`; change it before exposing the platform)

- **API Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics**: [http://localhost:8000/api/metrics](http://localhost:8000/api/metrics)

### 2. Local Development

Works on **macOS, Linux and Windows** — every entry point is a cross-platform Python task, so the
same commands run in `bash`, PowerShell, `cmd.exe` or `make`.

```bash
# Install the toolchain (mise pins Python 3.13, Node 24 and uv) and all dependencies
pnpm setup

# Start the backend API and the web dev server together (Ctrl+C stops both)
pnpm dev
```

Without `pnpm`, use `python scripts/task.py dev` or `make dev`. The `scripts/dev`, `scripts/test`
and `scripts/lint` shell entry points still work on macOS and Linux.

- **Web Application**: [http://127.0.0.1:5173](http://127.0.0.1:5173) — sign in with the seeded
  administrator (`admin@ai-qa.local` / `adminpassword`; change it before exposing the platform)
- **API Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Windows notes:

- Install [`mise`](https://mise.jdx.dev) (`winget install jdx.mise`), then `mise install`.
- `pnpm setup` prints a clear error if `uv` or `pnpm` is missing from `PATH`.
- The dev server binds `127.0.0.1` explicitly. Browsing to `localhost` may resolve to IPv6 `::1`
  on Windows and fail to connect.



---

## 🧪 Testing & Validation

```bash
# Run backend pytest suite & frontend typecheck, lint & build
pnpm test

# Run linters (ruff + eslint)
pnpm lint

# Build production assets
pnpm build

# Run production smoke test against running stack (POSIX shell only)
./scripts/prod_smoke_test.sh http://127.0.0.1:8000
```

---

## 📚 Complete Documentation

- [Production Deployment Guide](docs/DEPLOYMENT.md)
- [Operations & Monitoring Guide](docs/OPERATIONS.md)
- [Backup & Disaster Recovery](docs/BACKUP_RESTORE.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Platform Roadmap](docs/ROADMAP.md)
- [Quality Intelligence & Coverage](docs/QUALITY_INTELLIGENCE.md)
- [Distributed Execution Architecture](docs/DISTRIBUTED_EXECUTION.md)
- [Enterprise RBAC & Security](docs/RBAC.md)
- [Jira & TestRail Integration](docs/JIRA_INTEGRATION.md)
- [TestRail Integration](docs/TESTRAIL_INTEGRATION.md)
- [GitHub PR Engineering Workflow](docs/GITHUB_INTEGRATION.md)
- [Automation Studio V2 Guide](docs/AUTOMATION_STUDIO.md)
- [Failure Intelligence & Human-Approved Repair](docs/FAILURE_INTELLIGENCE.md)
- [Complete QA Lifecycle Workflow Guide](docs/PLATFORM_WORKFLOW.md)
- [Architecture Stabilization Audit (Phase 13.5)](docs/ARCHITECTURE_STABILIZATION_AUDIT.md)
- [Pilot Reference Project](docs/PILOT_REFERENCE_PROJECT.md)
- [Phase 14 Pilot Report](docs/PHASE_14_PILOT_REPORT.md)
- [Pilot Gap Analysis](docs/PILOT_GAP_ANALYSIS.md)
- [Release Readiness](docs/RELEASE_READINESS.md)
