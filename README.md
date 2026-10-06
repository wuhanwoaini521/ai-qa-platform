# AI QA Platform

> An Enterprise-Grade, Browser-Based AI Quality Engineering Platform covering the complete QA lifecycle.

[![CI](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/wuhanwoaini521/ai-qa-platform)

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
Live Test Outcomes & Execution Evidence
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

## 🚀 Current Platform Capabilities

- Manage requirements, test cases, automation bindings, and execution history in a unified workspace.
- Author and review automation in the Monaco-based Automation Studio, with browser recording and test exploration.
- Run isolated pytest projects and stream execution events and test results to the web application.
- Use configured AI providers for assistance, diagnosis, and repair proposals while keeping test verdicts tied to actual execution.
- Review failure evidence and proposed changes before applying repairs.
- Connect external workflows through Jira, TestRail, GitHub, and Jenkins integrations.
- Operate the platform with role-based access, health checks, metrics, and backup/restore procedures.

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

These are the default development URLs. If a port is occupied, `pnpm dev` chooses the next free
localhost port and prints the actual URLs; `AI_QA_API_PORT` and `AI_QA_WEB_PORT` set the preferred
ports.

Windows notes:

- Install [`mise`](https://mise.jdx.dev) (`winget install jdx.mise`), then `mise install`.
- `pnpm setup` prints a clear error if `uv` or `pnpm` is missing from `PATH`.
- The dev server binds `127.0.0.1` explicitly. Browsing to `localhost` may resolve to IPv6 `::1`
  on Windows and fail to connect.

### Run the included QA examples

After `pnpm setup`, run the checked-in, browser-free Pytest examples on macOS or Windows:

```bash
mise exec -- uv run pytest -c examples/quickstart/pytest.ini examples/quickstart/tests
```

The [example workspace](examples/quickstart/README.md) contains six passing tests for an in-memory
login flow and cart. Creating a project with **Create runnable QA examples** enabled copies the same
files into its workspace. In Automation Studio, run one test from Test Explorer or start a run with
no selection to execute all six. No browser install, live website, or external credentials are needed.



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

## 📚 Documentation

- [Developer Guide](docs/DEVELOPMENT.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Production Deployment Guide](docs/DEPLOYMENT.md)
- [Operations & Monitoring Guide](docs/OPERATIONS.md)
- [Backup & Disaster Recovery](docs/BACKUP_RESTORE.md)
- [Security](docs/SECURITY.md)
- [AI Providers](docs/AI_PROVIDER.md)
- [Production AI Architecture](docs/PRODUCTION_AI.md)
- [Platform Runtime Guide](docs/PLATFORM_RUNTIME_GUIDE.md)
- [Browser Recorder](docs/BROWSER_RECORDER.md)
- [Automation Studio](docs/AUTOMATION_STUDIO.md)
- [Failure Intelligence](docs/FAILURE_INTELLIGENCE.md)
- [Platform Roadmap](docs/ROADMAP.md)
- [Quality Intelligence & Coverage](docs/QUALITY_INTELLIGENCE.md)
- [Distributed Execution Architecture](docs/DISTRIBUTED_EXECUTION.md)
- [Enterprise RBAC & Security](docs/RBAC.md)
- [Jira & TestRail Integration](docs/JIRA_INTEGRATION.md)
- [TestRail Integration](docs/TESTRAIL_INTEGRATION.md)
- [GitHub PR Engineering Workflow](docs/GITHUB_INTEGRATION.md)
- [Complete QA Lifecycle Workflow Guide](docs/PLATFORM_WORKFLOW.md)
