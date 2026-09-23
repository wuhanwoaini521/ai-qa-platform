# Production AI Architecture

## 1. Overview
The AI QA Platform treats AI as an **acceleration and intelligence layer**, strictly separated from the **Deterministic Test Oracle (pytest / Playwright)**.

Key principles:
1. **AI != Test Oracle**: Test verdicts (PASS, FAIL, SKIPPED) are decided solely by test executions and runtime assertion checks. AI never declares a failing test passing or silently masks regressions.
2. **Pluggable AI Infrastructure**: AI interactions are routed through `AIProviderRegistry`, supporting `OpenAICompatibleProvider`, `FallbackAIProvider`, and `FakeAIProvider`.
3. **Structured Outputs & Schema Validation**: Prompts are version-controlled under `qa_core/prompts/` and parse strictly into Pydantic models.
4. **Budget & Rate Limit Guards**: `AIBudgetGuard` enforces per-run request and token limits. Budget exhaustion degrades gracefully and never crashes test execution.
5. **Observability & Auditing**: Every AI call records telemetry in `AIInvocationORM` (task, provider, model, latency, tokens, retry count, fallback status).

---

## 2. Prompt Versioning Architecture
All prompt templates are stored and versioned inside `packages/qa-core/qa_core/prompts/__init__.py`:

| Prompt Key | Version | Purpose |
|---|---|---|
| `requirement_analysis.v1` | 1.0.0 | Analyzes business PRD for edge cases, ambiguities, and test dimensions |
| `test_design.v1` | 1.0.0 | Proposes test designs across functional, boundary, negative, and API categories |
| `test_case_generation.v1` | 1.0.0 | Expands test designs into executable test cases with preconditions and steps |
| `test_author.v1` | 1.0.0 | Synthesizes Playwright Python automation code grounded in workspace knowledge |
| `failure_diagnosis.v1` | 1.0.0 | Dissects runtime failures, separating hard evidence from hypotheses |
| `locator_review.v1` | 1.0.0 | AST & semantic review of replacement locators for behavioral equivalence |
| `code_assistant.v1` | 1.0.0 | Code explanations, refactoring proposals, and inline diff suggestions |

---

## 3. Resilience & Secret Protection
- **Exponential Backoff**: Requests that fail with 429 or 5xx are retried with jittered exponential backoff.
- **Multi-tier Fallback**: `FallbackAIProvider` automatically switches from primary providers to fallback instances upon persistent timeout or outage.
- **Zero Secret Leakage**: All error logs, database records, prompts, and UI payloads are sanitized using `SensitiveRedactor`. Secrets like `OPENAI_API_KEY` or `JENKINS_API_TOKEN` are never exposed.
