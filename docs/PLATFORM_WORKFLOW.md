# Complete QA Lifecycle Workflow Guide

This guide walks through the end-to-end engineering workflow supported by the AI QA Platform, structured around the primary **Workspace Pipeline**:

$$\text{Workspace} \longrightarrow \text{Case} \longrightarrow \text{Automation} \longrightarrow \text{Run} \longrightarrow \text{Failure} \longrightarrow \text{AI / Jev Repair}$$

---

## 1. The End-to-End QA Pipeline Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. WORKSPACE & REQUIREMENTS                                                │
│    Import/Define Requirement → ANALYZE_REQUIREMENT Task → Test Designs     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 2. TEST CASE STRUCTURING                                                    │
│    Business Test Cases (P0-P3) → Parameters & Expected Results Matrix      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 3. AUTOMATION & STUDIO                                                      │
│    Scaffold Generation / Browser Recorder → Monaco Editor → debugpy DAP     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 4. DETERMINISTIC EXECUTION                                                  │
│    TestRunService (Local / Worker) → SSE Live Stream → Live Browser CDP     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 5. FAILURE INTELLIGENCE                                                     │
│    Deterministic Classifier → AI Root-Cause Diagnosis → Sanitized Evidence │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 6. AI / JEV REPAIR & VERIFICATION                                           │
│    Jev Candidate Selection → Playwright Verification → Human Apply → Rerun  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Step-by-Step Workflow

### Stage 1: Workspace & Requirement Analysis
1. Open the project workspace at `/workspace/:projectId`.
2. Inspect the **Context Panel** displaying current requirements, associated test cases, and recent execution runs.
3. Select or import a requirement (e.g. from Jira via `POST /api/jira/import`).
4. Click **Analyze Requirement**:
   - Triggers an `ANALYZE_REQUIREMENT` task in the Task Runtime.
   - Loads the requirement, project context, and up to 20 existing test cases.
   - AI evaluates acceptance criteria, edge cases, business rules, and coverage gaps; Jev selects priority test scenarios.
   - Authoritative analysis results are saved in `qa_model.history`, and sub-stage events stream live to the Runtime Mini Bar and Workflow.
5. Decompose the requirement into structured **Test Designs** across `FUNCTIONAL`, `BOUNDARY`, `NEGATIVE`, `API`, or `UI` categories.

---

### Stage 2: Test Case Structuring
1. Transition to the **Cases** stage within the workspace.
2. Review or materialize test cases from the approved Test Designs.
3. Define preconditions, business execution steps, expected results, priority (`P0`–`P3`), and suite tags.
4. *Key Concept*: `TestCase` represents the business requirement entity, while automation code in the workspace represents its implementation.

---

### Stage 3: Automation Authoring & Automation Studio
1. Transition to the **Automation** stage or launch **Automation Studio** (`/studio`) carrying the URL Context:
   - **AI Scaffold Generation**: Synthesizes executable Playwright/pytest code grounded in workspace Page Objects (`pages/`) and rules (`knowledge/`).
   - **Browser Recorder**: Record real user flows via WebSocket and Playwright Chromium, producing structured steps and element evidence bundles.
2. In Automation Studio:
   - Work across multi-tab Monaco editor (`tests/`, `pages/`, `knowledge/`).
   - Real-time Python AST validation flags syntax and lint errors in the **Problems Panel**.
   - Inspect collected tests in the **Pytest Explorer** sidebar.
   - Run interactive step-by-step debugging via real **`debugpy` DAP** sessions with full breakpoint support.

---

### Stage 4: Deterministic Pytest Execution
1. Trigger test execution:
   - Run a single test case from the workspace or editor tab.
   - Or dispatch a full regression run via `POST /api/runs`.
2. Execution Engine (`PytestRunner` / `LocalRunnerBackend` / Worker):
   - Launches an isolated pytest subprocess (`asyncio.create_subprocess_exec`).
   - Streams line-by-line terminal logs and status updates over SSE (`GET /api/runs/{id}/events`).
   - Captures real Chromium frames via CDP screencasting, streaming live UI telemetries into the **Live Browser** tab.
3. **Deterministic Verdict Guarantee**: Pytest exit codes determine `PASSED` or `FAILED`. AI is strictly forbidden from altering verdicts.

---

### Stage 5: Failure Intelligence & Taxonomy
1. When a test fails, navigate to the **Failure** stage or inspect the failure record in the workspace.
2. `FailureClassifier` deterministically categorizes the failure:
   - `LOCATOR_CHANGED`: Element selector broken or target moved.
   - `TIMING_ISSUE`: Async timeout or race condition.
   - `ASSERTION_FAILURE`: Business logic regression (`assert actual == expected`).
   - `ENVIRONMENT_ERROR`: Network, database, or server dependency failure.
3. All stack traces, HTTP payloads, and DOM captures are sanitized by `SensitiveRedactor` to strip passwords, tokens, and secrets.
4. AI diagnoses root causes, separating hard execution evidence from speculative hypotheses.

---

### Stage 6: AI / Jev Locator Repair & Verification
1. For eligible `LOCATOR_CHANGED` failures with captured DOM snapshots:
   - Candidate locator elements are discovered from the page snapshot and element evidence bundles.
   - **Jev Decision**: `DecisionService.choose()` evaluates candidates and selects the most resilient locator.
   - **Playwright Verification**: A headless verification browser tests the candidate locator against the live page before any proposal is shown.
2. **Human-in-the-Loop Review**:
   - Platform presents an AST-bounded code diff preview showing exact changes to the Page Object.
   - **Human Approval Required**: User inspects the proposal and clicks **Apply Repair to Code** (`POST /api/failures/{id}/apply-repair`).
   - The platform safely updates the workspace file, tracking the baseline file hash for rollback safety.
3. **Targeted Verification Rerun**:
   - The platform triggers a fresh execution strictly targeted at the failed `nodeid`.
   - Only when this run produces a real `PASSED` exit code is the failure analysis marked as `VERIFIED`.
