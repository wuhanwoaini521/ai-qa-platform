# AI Provider Integration, Architecture & Configuration

This document outlines the architecture, principles, prompt management, configuration, and telemetry for AI and Decision providers within the AI QA Platform.

---

## 1. Core Principles & Architecture

The AI QA Platform treats AI as an **acceleration, synthesis, and intelligence layer**, strictly separated from the **Deterministic Test Oracle (pytest / Playwright)**.

1. **AI != Test Oracle**: Test verdicts (`PASSED`, `FAILED`, `SKIPPED`) are determined solely by pytest exit codes and runtime assertion checks. AI never declares a failing test passing or silently masks regressions.
2. **Pluggable Infrastructure**: All AI interactions route through `AIProviderRegistry` via the `AIProvider` protocol, supporting `OpenAICompatibleProvider`, `FallbackAIProvider`, and `FakeAIProvider`.
3. **Budget & Rate Limit Guards**: `AIBudgetGuard` enforces per-run request and token limits. Budget exhaustion degrades gracefully and never crashes test execution.
4. **Fabricated Output is Explicitly Labelled**: When a configured provider fails, `FallbackAIProvider` serves the deterministic `FakeAIProvider` and marks the response `fallback_used=true` with `provider="fake"`. The invocation record persists this flag so no consumer can mistake synthetic analysis for model output.
5. **Zero Secret Leakage**: All error logs, database records, prompts, and UI payloads are sanitized using `SensitiveRedactor`. Secrets like `QA_AI_API_KEY` or `JEV_API_KEY` are never exposed in effective configs or API responses.

```text
┌────────────────────────────────────────┐
│           AIProviderRegistry           │
└──────────────────┬─────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│ OpenAICompatible │  │  FakeAIProvider  │
└──────────────────┘  └──────────────────┘
```

### Supported Providers
1. **`OpenAICompatibleProvider`**: Connects to OpenAI, Azure OpenAI, DeepSeek, vLLM, Ollama, or any OpenAI API-compatible inference service.
2. **`FallbackAIProvider`**: Chains a primary provider with secondary/tertiary fallbacks.
3. **`FakeAIProvider`**: Deterministic mock provider for local offline development, unit tests, and CI pipelines without live LLM keys.

---

## 2. Configuration & Environment Variables

```bash
QA_AI_ENABLED=true
QA_AI_PROVIDER=openai-compatible  # or fake
QA_AI_API_KEY=                 # injected secret; never put a real value in YAML
QA_AI_BASE_URL=https://api.deepseek.com
QA_AI_MODEL=deepseek-flash
QA_AI_TIMEOUT_SECONDS=30
QA_AI_MAX_RETRIES=3

JEV_ENABLED=true
JEV_API_KEY=                   # injected secret; never put a real value in YAML
JEV_BASE_URL=https://api.typesafe.ai/v1/systemone
JEV_MODEL=jev-1.13.0
JEV_TIMEOUT_SECONDS=20
JEV_RETRIES=1
JEV_MINIMUM_CONFIDENCE=0.70
```

> **Configuration Note**: The provider is selected with `QA_AI_PROVIDER` (`fake` by default). Setting legacy `AI_PROVIDER` or plain `OPENAI_API_KEY` has no effect — see `.env.example` for the exact variable names.

For these provider fields, process environment (including repository-root `.env` in local development) overrides YAML; YAML values override safe schema defaults. Compose forwards the same variables to the API. Unset overrides leave the committed YAML provider/model policy in place. Credential values are never included in effective-config or health responses.

### Health Probe States
Health is reported independently from provider response provenance:
- `READY`: Requires a successful real streamed response probe. (A Fake provider can never report `READY`).
- `DEGRADED`: Simulation or fallback is in use.
- `UNCONFIGURED`: A required API key is absent.
- `DISABLED`: The provider is switched off.
- `UNAVAILABLE`: A configured provider could not complete its real probe.

### OpenCode-Compatible Gateways
The OpenAI-compatible provider identifies itself as `ai-qa-platform` and sends `x-opencode-session` on every completion request. Each `AICompletionRequest` gets an opaque session ID by default; retries keep the same ID. Callers that make multiple related completions can pass the same `session_id` to keep those calls on one OpenCode session route.

---

## 3. Prompt Versioning Architecture

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

## 4. Resilience & Secret Protection

- **Exponential Backoff**: Requests that fail with 429 or 5xx are retried with jittered exponential backoff.
- **Multi-tier Fallback**: `FallbackAIProvider` automatically switches from primary providers to fallback instances upon persistent timeout or outage.
- **Zero Secret Leakage**: All error logs, database records, prompts, and UI payloads are sanitized using `SensitiveRedactor`. Secrets like `QA_AI_API_KEY` or `JENKINS_API_TOKEN` are never exposed.

---

## 5. Telemetry & Auditing

Every invocation creates an `AIInvocationORM` record in the database:
- `task`: E.g., `requirement_analysis`, `failure_diagnosis`, `locator_review`.
- `provider`: E.g., `openai`, `fake`.
- `model`: E.g., `gpt-4o-mini`.
- `duration_ms`: Execution latency in milliseconds.
- `input_tokens` / `output_tokens`: Token consumption.
- `retry_count`: Retries before success.
- `fallback_used`: Boolean indicating if fallback provider took over.
- `prompt_version`: Prompt template key used.
