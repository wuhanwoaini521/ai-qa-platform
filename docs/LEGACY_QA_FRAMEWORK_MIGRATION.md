# Legacy QA Framework Migration Map

This document defines how mature concepts, abstractions, and tools from existing Playwright frameworks will be migrated into `qa-core` and platform services across upcoming phases.

## Capability Mapping Matrix

| Legacy Framework Capability | QA Platform Target Location | Target Phase | Migration Approach |
| --------------------------- | --------------------------- | ------------ | ------------------ |
| **Component & Page Objects** | `runtime/workspaces/*/pages`, `components/` | Phase 1 & 2 | Standardized Python class scaffolding with Monaco code editing |
| **User Flows** | `runtime/workspaces/*/flows/` | Phase 1 & 2 | Modular flow abstractions combining multiple component interactions |
| **Knowledge Rules** | `runtime/workspaces/*/knowledge/` | Phase 2 & 3 | Markdown and YAML domain rules consumed by `TestAuthor` & `LocatorHealer` |
| **FailureArtifact & Classification** | `packages/qa-core/qa_core/contracts.py` → `FailureAnalyzer` | Phase 3 | Extract screenshot / trace extractor into pluggable `FailureContext` analyzer |
| **AIProvider & TestAuthor** | `packages/qa-core/qa_core/adapters/ai_author.py` | Phase 3 | Wrap OpenAI / Gemini client behind `TestAuthor` protocol |
| **LocatorHealing** | `packages/qa-core/qa_core/adapters/healer.py` | Phase 3 | Port DOM tree diffing and semantic selector recovery algorithms |
| **BrowserExplorer** | `packages/qa-core/qa_core/adapters/explorer.py` | Phase 3 | Port the bounded exploration loop into structured `ExplorationSession` |
| **Test Execution & Pytest Runner** | `apps/worker` + `qa_core/runner.py` | Phase 4 | Subprocess / containerized Playwright runner with streaming JSON output |
| **History & Flaky Analytics** | `apps/api/app/domain/analytics.py` | Phase 5 | Store test run metrics and flaky frequency scores in PostgreSQL |
| **TestRail & GitHub CI Integration**| `packages/integrations` | Phase 6 | Turn webhook stubs into live bidirectional syncing adapters |

---

## Migration Guidelines

1. **Decoupled Contracts First**: Ensure all legacy modules implement protocols defined in `packages/qa-core/qa_core/contracts.py`.
2. **No Direct Framework Bleed**: Never import Playwright or Pytest internal runtime libraries directly into FastAPI web routes.
3. **Deterministic Fakes Preserved**: Keep fake adapters active for offline development and CI validation even after real adapters are introduced.
