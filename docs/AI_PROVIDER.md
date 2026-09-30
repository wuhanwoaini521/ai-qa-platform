# AI Provider Integration & Configuration

## 1. Provider System Architecture
The platform supports pluggable AI providers implementing the `AIProvider` Protocol:

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
# Provider Selection
AI_PROVIDER_TYPE=openai_compatible  # or fake, fallback

# OpenAI / Compatible API Settings
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
AI_REQUEST_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=3

# Budget Guards
AI_MAX_REQUESTS_PER_RUN=25
AI_MAX_TOKENS_PER_RUN=50000
```

### OpenCode-compatible gateways

The OpenAI-compatible provider identifies itself as `ai-qa-platform` and sends
`x-opencode-session` on every completion request. Each `AICompletionRequest` gets
an opaque session ID by default; retries keep the same ID. Callers that make
multiple related completions can pass the same `session_id` to keep those calls
on one OpenCode session route. See the [OpenCode Go client requirements](https://opencode.ai/docs/go/#where-can-i-use-it).

---

## 3. Telemetry & Auditing
Every invocation creates an `AIInvocationORM` record in the database:
- `task`: E.g., `requirement_analysis`, `failure_diagnosis`, `locator_review`.
- `provider`: E.g., `openai`, `fake`.
- `model`: E.g., `gpt-4o-mini`.
- `duration_ms`: Execution latency in milliseconds.
- `input_tokens` / `output_tokens`: Token consumption.
- `retry_count`: Retries before success.
- `fallback_used`: Boolean indicating if fallback provider took over.
- `prompt_version`: Prompt template key used.
