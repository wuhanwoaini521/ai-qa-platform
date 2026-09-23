# AI QA Platform — Architecture

## System Overview

The **AI QA Platform** is a browser-based engineering platform designed to support the complete Quality Engineering lifecycle—from requirements analysis, test design, and test case management, to an integrated Automation Studio, execution orchestration, and failure intelligence.

```mermaid
flowchart TD
    subgraph UI ["Platform UI (React 19 + TypeScript + Vite)"]
        Dashboard["Dashboard & Stats"]
        Projects["Project Management"]
        Reqs["Requirements & Test Design"]
        Cases["Test Case Repository"]
        Studio["Automation Studio (Monaco Editor + Git Diff)"]
    end

    subgraph API ["Platform API (FastAPI + Pydantic)"]
        Routes["REST Endpoints (/api/...)"]
        Services["Domain Services (Project, Requirement, TestCase, Workspace)"]
        Repos["Repositories (SQLAlchemy Async)"]
    end

    subgraph Core ["QA Core & Engine (packages/qa-core)"]
        Runner["TestRunner (Playwright / Pytest / Fake)"]
        Analyzer["FailureAnalyzer (Root Cause Taxonomy)"]
        Author["TestAuthor (AI Code Generation)"]
        Healer["LocatorHealer (Self-healing Selectors)"]
        Explorer["BrowserExplorer (AI Sessions)"]
        Orchestrator["QAOrchestrator"]
    end

    subgraph Storage ["Persistence & Workspace Storage"]
        DB[(SQLite / PostgreSQL DB)]
        WorkspaceFS["runtime/workspaces/ (Git Workspaces)"]
        ArtifactStore["runtime/artifacts/ (Screenshots / Traces)"]
    end

    subgraph Worker ["Execution Worker (apps/worker)"]
        JobQueue["Job Queue & Dispatcher"]
        JobExecutor["Background Job Runner"]
    end

    UI -->|HTTP / JSON| API
    Routes --> Services
    Services --> Repos
    Services --> WorkspaceFS
    Repos --> DB
    Services --> Core
    Worker --> JobQueue
    Worker --> Core
    Worker --> ArtifactStore
```

---

## Architectural Boundaries

1. **Frontend (`apps/web`)**:
   - Single Page Application built on React, TypeScript, and Vite.
   - Monaco Editor for in-browser editing of test automation suites, page object models, flows, and knowledge definitions.
   - Desktop-first, engineering-focused UX with zero promotional bloat.

2. **Backend API (`apps/api`)**:
   - FastAPI modular monolith structure adhering strictly to the **Route → Service → Repository / QA Core** dependency layer.
   - Direct database access and shell executions from route handlers are prohibited.
   - SQLite as default local dev/test database with PostgreSQL compatibility through standard SQLAlchemy ORM.

3. **Workspace Subsystem (`runtime/workspaces/`)**:
   - Isolates code checkouts per project.
   - Built-in path traversal safeguards rejecting any `..` or absolute escape vectors.
   - Integrated Git status and unified diff generation for studio source control visibility.

4. **QA Core (`packages/qa-core`)**:
   - Protocol-driven abstractions defining the future migration boundary for execution engines, AI authors, locator healers, and failure analyzers.
   - Deterministic fake implementations enabled out-of-the-box for offline integration testing.

5. **Execution Worker (`apps/worker`)**:
   - Asynchronous background worker foundation for test runs and AI diagnostic tasks.
