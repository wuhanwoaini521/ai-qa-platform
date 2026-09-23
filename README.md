# AI QA Platform

> A Browser-based AI Quality Engineering Platform covering the complete QA lifecycle.

[![CI](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/wuhanwoaini521/ai-qa-platform/actions/workflows/ci.yml)

---

## What It Is

**AI QA Platform** is an independent, browser-based Quality Engineering platform designed to eliminate constant context-switching between IDEs, terminals, test case managers, CI runners, and AI chat interfaces.

```text
Requirement
   ↓
Test Design
   ↓
Test Case
   ↓
AI / Manual Automation Authoring & Binding
   ↓
Code Editing in Automation Studio V2
   ↓
AST Syntax & Rule Validation
   ↓
Deterministic Pytest Execution & SSE Streaming
   ↓
Live Test Outcome & Failure Artifacts
   ↓
Failure Classification & AI Root-Cause Diagnosis
   ↓
Locator Repair Proposal & Diff Review
   ↓
Human-Approved Apply & Re-run Verification
```

---

## Architecture

```text
ai-qa-platform/
├── apps/
│   ├── web/                     # React 19 + TypeScript + Vite + Monaco Editor V2
│   ├── api/                     # FastAPI + Pydantic + SQLAlchemy Async + SSE Bus
│   └── worker/                  # Background test execution worker
├── packages/
│   ├── qa-core/                 # Core testing contracts, PytestRunner, Classifier & Healer
│   ├── project-model/           # Shared Pydantic domain models & database entities
│   └── integrations/            # Third-party connectors (TestRail, GitHub)
├── docs/                        # Full architecture, execution & workflow specifications
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

## Complete QA Engineering Capabilities

- **Automation Studio V2**:
  - Multi-tab Monaco editor with dirty tracking (`Cmd+S`, `Cmd+Shift+S`).
  - Quick Open fuzzy file finder (`Cmd+P`).
  - File operations: Create files/folders, rename, delete with confirmation.
  - Python AST syntax validator & collapsible Problems panel with jump-to-line navigation.
  - Pytest explorer tree with targeted single-test runner.
  - Interactive QA Assistant sidecar (Explain, Generate Test Scaffold, Refactor to Page Object, Diagnose).
  - Git working tree diff inspection & in-studio commits.
- **Test Case & Automation Binding**:
  - Bidirectional link between business test cases and executable pytest node IDs.
  - AI automation code generator grounded on workspace Page Objects and knowledge rules.
  - One-click save to workspace test files.
- **Test Execution Platform**:
  - Safe subprocess execution via `PytestRunner` (no `shell=True`).
  - Real-time Server-Sent Events (SSE) event bus streaming stdout/stderr line-by-line.
  - Test outcomes breakdown and execution duration metrics.
  - Deterministic pass/fail verdict determined strictly by pytest exit codes.
- **Failure Intelligence & Locator Self-Healing**:
  - Failure taxonomy classification (`LOCATOR_CHANGED`, `TIMING_ISSUE`, `ASSERTION_FAILURE`, `ENVIRONMENT_ERROR`).
  - Automated sensitive data redaction (passwords, tokens, API keys).
  - Multi-candidate locator ranking and visual code diff preview.
  - Proposal-only human-in-the-loop repair workflow with one-click code patching.
  - Instant re-run verification of fixed tests.

---

## Documentation

- [Complete QA Lifecycle Workflow Guide](docs/PLATFORM_WORKFLOW.md)
- [Automation Studio V2 Guide](docs/AUTOMATION_STUDIO.md)
- [Test Execution Platform Architecture](docs/EXECUTION_PLATFORM.md)
- [Failure Intelligence & Self-Healing](docs/FAILURE_INTELLIGENCE.md)
- [QA Core Migration Audit](docs/QA_CORE_MIGRATION_AUDIT.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Product Domain Model](docs/PRODUCT_MODEL.md)
- [Developer Guide](docs/DEVELOPMENT.md)
- [Workspace & Storage Model](docs/WORKSPACE_MODEL.md)
- [QA Core Specification](docs/QA_CORE.md)
- [Legacy QA Framework Migration Map](docs/LEGACY_QA_FRAMEWORK_MIGRATION.md)
- [Platform Roadmap](docs/ROADMAP.md)
