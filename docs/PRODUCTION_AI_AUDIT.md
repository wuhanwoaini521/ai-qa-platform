# Production AI Architecture Audit

## 1. Executive Summary
This document audits the current AI-related capabilities in the `ai-qa-platform` codebase, evaluating provider neutrality, current reliance on fake/mock implementations, secret handling, structured output compliance, and required architectural enhancements for Phase 5.

---

## 2. Current Component State Assessment

| Component | Location | Current State | Provider Neutral? | Action Required for Phase 5 |
| :--- | :--- | :--- | :--- | :--- |
| `AIProvider` & `FakeAIProvider` | `packages/qa-core/qa_core/ai/provider.py` | Minimal protocol + hardcoded fake provider | Partially | Replace with extensible `AIProviderRegistry`, `OpenAICompatibleProvider`, retry, timeout, and fallback mechanisms |
| `QA Assistant Service` | `apps/api/app/services/qa_assistant_service.py` | Hardcoded regex / static templates | No | Connect to `ProductionQAOrchestrator` and structured AI tasks with prompt versioning |
| `FailureClassifier` | `packages/qa-core/qa_core/failure/classifier.py` | Deterministic regex taxonomy | Yes (deterministic) | Retain deterministic baseline; augment with structured `AIFailureDiagnoser` for hypothesis generation |
| `LocatorHealer` | `packages/qa-core/qa_core/healing/healer.py` | Deterministic heuristic DOM repair | Yes (deterministic) | Retain deterministic candidate discovery; augment with AI semantic review |
| `KnowledgeGrounder` & `PytestCodeGenerator` | `packages/qa-core/qa_core/author/grounder.py` | AST/template generation grounded in knowledge | Yes | Augment with AI-assisted Test Specification and Code Generation validated by AST & Ruff |
| `ProductionQAOrchestrator` | `packages/qa-core/qa_core/orchestrator/orchestrator.py` | Coordinates core modules | Partially | Inject registry, budget guard, structured task runners, and fallback handling |

---

## 3. Key Architectural Gaps Identified

1. **Lack of Provider Registry & OpenAI-Compatible Implementation**:
   - Currently only `FakeAIProvider` exists.
   - Need a pluggable registry (`AIProviderRegistry`) supporting `fake`, `openai-compatible`, and `custom` with runtime health checks.

2. **Secret Handling**:
   - API keys must strictly be ingested via environment variables or secret store adapters, never stored in DB plaintext, Git, frontend, logs, or prompt traces.

3. **Structured Outputs & Schema Validation**:
   - Need strict Pydantic schemas (`TestDesignSuggestion`, `TestSpecification`, `FailureAnalysisResponse`, `LocatorSemanticReview`, `CodeAssistantResponse`, `RequirementAnalysisResponse`) with robust fallback parsing.

4. **Resilience, Timeout, and Bounded Exponential Retry**:
   - Need configurable connect/read timeouts with bounded exponential backoff for transient 429 and 5xx errors (avoiding retries on 401, 403, and unrecoverable schema errors).

5. **Multi-tier Fallback**:
   - Primary (e.g. OpenAI/Gateway) -> Secondary -> Fake/Disabled.
   - Crucially: AI failures must **never** fail the underlying pytest test execution or platform run.

6. **Observability, Budget Guards & Prompt Versioning**:
   - Record `AIInvocation` telemetry (duration, tokens, retry count, fallback used, prompt version).
   - Enforce run-level request and token budget limits (`QA_AI_MAX_REQUESTS_PER_RUN`, `QA_AI_MAX_INPUT_TOKENS_PER_RUN`, etc.).
   - Manage prompt templates with explicit `prompt_id` and `version` metadata.

---

## 4. Phase 5 Implementation Roadmap
- **Gate 5.2 - 5.4**: `AIProviderRegistry`, `OpenAICompatibleProvider`, and Secret Management.
- **Gate 5.5 - 5.6**: Structured output schemas and AI Task implementations (Requirement Analysis, Test Design, Test Case, Author, Failure Diagnosis, Locator Semantic Review).
- **Gate 5.7 - 5.9**: Timeout, Retry, Fallback, and Provider Health monitoring (`GET /api/ai/status`).
- **Gate 5.10 - 5.12**: AI Invocation persistence, Budget Guard, and Prompt Versioning.
- **Gate 5.13**: Automation Studio AI Assistant V2 integration.
