# Platform Roadmap

## Phase 1 — Platform Bootstrap
- [x] Monorepo architecture & workspace isolation
- [x] FastAPI modular domain services (Projects, Requirements, Test Designs, Test Cases)
- [x] React 19 + TypeScript + Vite web platform shell
- [x] Automation Studio with Monaco Editor, file tree, file edit/save, and Git diff inspection
- [x] Safe WorkspaceService with path traversal prevention
- [x] QA Core contracts and deterministic fake adapters
- [x] GitHub repository setup and CI pipelines

---

## Phase 2 — Automation Studio V2
- [x] Monaco Editor polish (multi-tab support, mini terminal output)
- [x] Interactive AI coding assistant panel
- [x] File search & fuzzy switcher (`Cmd+P`)
- [x] Selected test file / function execution trigger
- [x] In-browser test case to code linker

---

## Phase 3 — QA Core Migration
- [x] Playwright runner integration
- [x] FailureArtifact ingestion (traces, videos, screenshots)
- [x] Live AI diagnosis with OpenAI / Gemini API adapters
- [x] Automated DOM locator healing
- [x] Autonomous browser explorer session viewer

---

## Phase 4 — Real Test Execution Platform
- [x] PytestRunner & background worker task management
- [x] SSE live streaming logs & terminal console
- [x] Duration stats, pass/fail status updates, test outcome tables

---

## Phase 5 — Production AI Intelligence
- [x] Pluggable `AIProviderRegistry`, `OpenAICompatibleProvider`, `FallbackAIProvider`, `FakeAIProvider`
- [x] Prompt template versioning in `packages/qa-core/qa_core/prompts/`
- [x] Token & request rate budgeting via `AIBudgetGuard`
- [x] Telemetry persistence in `AIInvocationORM` & AI usage dashboard
- [x] AI Assistant V2 (Explain, Draft, Refactor, Diagnose)

---

## Phase 6 — Run History & Flaky Intelligence
- [x] Stable test identity model (`nodeid` + `project_id`)
- [x] Persistent test execution history in `RunHistoryRepository`
- [x] Deterministic flaky scoring formula with minimum sample threshold guard
- [x] Flaky Intelligence UI (`/flaky`) with pass/fail/skip trends and P95 latency
- [x] Failure recurrence signature query & previous occurrences table

---

## Phase 7 — Jenkins & Multi-Runner Platform
- [x] `RunnerBackend` interface abstraction (`LocalRunnerBackend`, `JenkinsRunnerBackend`)
- [x] Parameter mapping (`PROJECT_ID`, `WORKSPACE_ID`, `TARGET_NODEIDS`, `BROWSER`)
- [x] In-memory `FakeJenkinsServer` mock transport for reliable CI testing
- [x] Runner profiles management (`RunnerProfileORM`) & health check APIs
- [x] External test artifacts linking (`ExternalArtifactReferenceORM` for Allure & HTML Reports)

---

## Phase 8 — Enterprise Integrations (Next)
- [ ] Role-based Access Control (RBAC) & SSO
- [ ] TestRail two-way test case and result synchronization
- [ ] GitHub Pull Request check suites & automated comments
- [ ] Slack & Microsoft Teams notification webhooks
