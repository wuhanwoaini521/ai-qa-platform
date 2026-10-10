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

For these provider fields, process environment (including repository-root `.env` in local development)
overrides YAML; YAML values override safe schema defaults. Compose forwards the same variables to the API.
Unset overrides leave the committed YAML provider/model policy in place. Credential values are never
included in effective-config or health responses.

Health is reported independently from provider response provenance: `READY` requires a successful
real streamed response; `DEGRADED` means simulation or fallback is in use; `UNCONFIGURED` means a
required API key is absent; `DISABLED` means the provider is switched off; `UNAVAILABLE` means a
configured provider could not complete its real probe. A Fake provider can never report `READY`.

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
