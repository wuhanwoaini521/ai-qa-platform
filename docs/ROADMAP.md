# Platform Roadmap

## Phase 1 — Platform Bootstrap (Current)
- [x] Monorepo architecture & workspace isolation
- [x] FastAPI modular domain services (Projects, Requirements, Test Designs, Test Cases)
- [x] React 19 + TypeScript + Vite web platform shell
- [x] Automation Studio with Monaco Editor, file tree, file edit/save, and Git diff inspection
- [x] Safe WorkspaceService with path traversal prevention
- [x] QA Core contracts and deterministic fake adapters
- [x] GitHub repository setup and CI pipelines

---

## Phase 2 — Automation Studio V2
- Monaco Editor polish (multi-tab support, mini terminal output)
- Interactive AI coding assistant panel
- File search & fuzzy switcher (`Cmd+P`)
- Selected test file / function execution trigger
- In-browser test case to code linker

---

## Phase 3 — QA Core Migration
- Playwright runner integration
- FailureArtifact ingestion (traces, videos, screenshots)
- Live AI diagnosis with OpenAI / Gemini API adapters
- Automated DOM locator healing
- Autonomous browser explorer session viewer

---

## Phase 4 — Distributed Execution Platform
- Celery / Async job worker scaling
- Containerized execution runners (Docker)
- CI triggers & webhook dispatchers
- Real-time SSE streaming logs

---

## Phase 5 — Failure & Quality Intelligence
- Historical test execution telemetry
- Flaky test detection algorithms & score cards
- Automated regression risk analysis
- PR test impact analysis

---

## Phase 6 — Enterprise Integrations
- Role-based Access Control (RBAC) & SSO
- TestRail two-way test case and result synchronization
- GitHub Pull Request check suites & automated comments
- Slack & Microsoft Teams notification webhooks
