# QA Core Migration Audit Report

## 1. Migration Overview

This document audits the legacy QA framework located at `../playwright-test` and establishes the migration blueprint for `packages/qa-core`.

---

## 2. Capability Audit & Refactoring Strategy

| Module | Legacy Location | Target in `packages/qa-core` | Refactoring & Decoupling Strategy |
| ------ | --------------- | ----------------------------- | --------------------------------- |
| **Execution Engine** | `tests/` + `allure-results/` | `qa_core/execution/` | Safe `asyncio.subprocess` execution of pytest with structured event parsing (no `shell=True`, isolated working directory). |
| **Failure Classification & Redactor** | `failure/` | `qa_core/failure/` | Extract `SensitiveRedactor` to strip passwords, tokens, API keys; build `FailureClassifier` taxonomy (`LOCATOR_CHANGED`, `TIMING_ISSUE`, `ASSERTION_FAILURE`, `ENVIRONMENT_ERROR`). |
| **Knowledge Engine** | `knowledge/` | `qa_core/knowledge/` | Make knowledge paths workspace-relative (`<workspace_id>/knowledge/`) instead of hardcoded paths. Support Page, Flow, and Component rule parsing. |
| **Test Authoring** | `author/` | `qa_core/author/` | Ground requirements and test cases in domain knowledge; generate idiomatic Playwright test scripts. |
| **Locator Healing** | `healing/` | `qa_core/healing/` | Keep proposal-only architecture (`LocatorRepairProposal`). Never alter workspace code silently; provide candidate ranking and AST diffs. |
| **Browser Explorer** | `explorer/` | `qa_core/explorer/` | Bound browser actions with `max_steps`, domain allowlists, and destructive action guards. |
| **AI Provider Abstraction** | `ai/` | `qa_core/ai/` | Pure protocol abstraction with `FakeAIProvider` for offline development and future OpenAI/Anthropic/Gemini compatibility. |
| **QA Orchestrator** | `orchestrator/` | `qa_core/orchestrator/` | Unified router coordinating authoring, failure diagnosis, healing proposals, and exploratory sessions. |

---

## 3. What Was NOT Copied Directly

- Hardcoded file paths and environment variables from the legacy repo.
- Legacy Allure result parsing coupling.
- Framework-level dependencies that would pollute FastAPI backend endpoints.
