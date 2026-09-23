# AI QA Platform

> A Browser-based AI Quality Engineering Platform covering the complete QA lifecycle.

[![CI](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml)

---

## What It Is

**AI QA Platform** is an independent, browser-based Quality Engineering platform designed to eliminate constant context-switching between IDEs, terminals, test case managers, CI runners, and AI chat interfaces.

```text
Requirement → Test Design → Test Case Management → Automation Studio → AI Test Author → Code Editing → Validation → Test Execution → Failure Intelligence → AI Diagnosis → Locator Healing → Run History / Flaky
```

---

## Architecture

```text
ai-qa-platform/
├── apps/
│   ├── web/                     # React 19 + TypeScript + Vite + Monaco Editor
│   ├── api/                     # FastAPI + Pydantic + SQLAlchemy Async
│   └── worker/                  # Background test execution worker
├── packages/
│   ├── qa-core/                 # Core testing contracts & deterministic fakes
│   ├── project-model/           # Shared Pydantic domain models & schemas
│   └── integrations/            # Third-party connectors (TestRail, GitHub)
├── docs/                        # Full architecture & migration specifications
├── runtime/                     # Isolated project workspaces & test artifacts
└── scripts/                     # Unified dev, test, and lint commands
```

---

## Quick Start

### 1. Clone and Setup Environment

```bash
git clone git@github.com:wuhanwoaini521/ai-qa-platform.git
cd ai-qa-platform

# Install mise toolchain (Python 3.13, Node 24, uv, pnpm)
mise trust
mise install

# Install workspace dependencies
mise exec -- uv sync --all-packages
mise exec -- pnpm install
```

### 2. Start Local Development

```bash
./scripts/dev
```

- **Web Application**: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- **API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **API Health Check**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## Testing & Quality Assurance

```bash
# Run all backend unit/integration tests & frontend typecheck
./scripts/test

# Run linters (ruff for Python, eslint for TypeScript)
./scripts/lint

# Build frontend production bundle
pnpm --filter @ai-qa/web build
```

---

## Key Features in Phase 1

- **Project Management**: Initialize blank QA project scaffolds with standard `tests/`, `pages/`, `flows/`, `components/`, and `knowledge/` folders.
- **Requirements & Test Design**: Define user stories, acceptance criteria, and multi-category test designs (`FUNCTIONAL`, `BOUNDARY`, `NEGATIVE`, `API`, `UI`).
- **Test Case Management**: Structured business test cases with steps, preconditions, expected results, priority (`P0`-`P3`), and automation tracking.
- **Automation Studio**: In-browser code editing powered by Monaco Editor, project file explorer, real-time dirty status tracking, `Cmd+S` save support, and Git working tree diff inspection.
- **Safe Workspaces**: Hardened filesystem isolation preventing path traversal attacks.
- **QA Core Contracts**: Clean protocol abstractions (`TestRunner`, `FailureAnalyzer`, `TestAuthor`, `LocatorHealer`, `BrowserExplorer`, `QAOrchestrator`) with offline fake implementations.

---

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Product Domain Model](docs/PRODUCT_MODEL.md)
- [Developer Guide](docs/DEVELOPMENT.md)
- [Workspace & Storage Model](docs/WORKSPACE_MODEL.md)
- [QA Core Specification](docs/QA_CORE.md)
- [Legacy QA Framework Migration Map](docs/LEGACY_QA_FRAMEWORK_MIGRATION.md)
- [Platform Roadmap](docs/ROADMAP.md)
