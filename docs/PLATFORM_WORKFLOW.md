# Complete QA Lifecycle Workflow Guide

This guide walks through the end-to-end engineering workflow supported by the AI QA Platform: from business requirement ingestion to human-approved locator repair and reruns.

---

## The End-to-End QA Pipeline

```text
Requirement Ingestion & Acceptance Criteria
                   ↓
Test Design & Category/Risk Decomposition
                   ↓
Test Case Definition (Business Entity)
                   ↓
AI / Manual Automation Authoring & Workspace Binding
                   ↓
Code Editing & Refactoring in Automation Studio V2
                   ↓
Workspace AST & Rule Validation
                   ↓
Deterministic Pytest Execution & SSE Streaming
                   ↓
Live Test Outcome & Failure Artifact Collection
                   ↓
Failure Classification & AI Root-Cause Diagnosis
                   ↓
Locator Repair Proposal & Diff Review
                   ↓
Human-Approved Apply & Re-run Verification
```

---

## Step-by-Step Workflow

### 1. Requirements & Test Design
1. Open **Requirements & Design** page.
2. Define requirement title, description, and acceptance criteria.
3. Decompose into structured test designs covering `FUNCTIONAL`, `BOUNDARY`, `NEGATIVE`, `API`, or `UI` categories.

### 2. Test Case & Automation Binding
1. Open **Test Cases** page.
2. Define manual test steps, preconditions, expected results, and priority (`P0`-`P3`).
3. Click **Generate Automation Scaffold**:
   - AI grounds on workspace Page Objects and knowledge rules.
   - Generates executable Playwright/Pytest code.
4. Click **Save & Bind to Workspace**:
   - Creates the test file in `tests/test_*.py`.
   - Links the business test case to the executable pytest node ID (`tests/test_x.py::test_func`).

### 3. Code Editing in Automation Studio V2
1. Open **Automation Studio**.
2. Work across multiple tabs (`tests/`, `pages/`, `knowledge/`).
3. Use `Cmd+P` to quickly jump across test files.
4. Use the **QA Assistant** sidecar for explaining code, generating test helpers, or refactoring locators into Page Objects.
5. Save changes (`Cmd+S`) and commit changes to git directly in the studio.

### 4. Validation & Test Explorer
1. Inspect the bottom **Problems Panel** for syntax errors or linting violations.
2. Jump to line directly by clicking any error row.
3. Switch sidebar to **Tests** tab to view the collected pytest suite tree.

### 5. Execution & Real-Time Streaming
1. Click **Run Test Now** from the test case, editor tab, or **Execution Platform** page.
2. Watch real-time test outcomes and line-by-line terminal logs streamed via Server-Sent Events (SSE).
3. View pass/fail status, test duration, and individual test verdicts.

### 6. Failure Intelligence & Human-Approved Repair
1. If a test fails, navigate to **Failure Intelligence** page.
2. Review categorized failure (`LOCATOR_CHANGED`, `TIMING_ISSUE`, `ASSERTION_FAILURE`).
3. Click **AI Root Cause Diagnosis** for in-depth explanation and recommendations.
4. Click **Generate Locator Repair Proposal** to inspect candidate locators and code diff preview.
5. Click **Apply Repair to Code** to patch the Page Object file.
6. Click **Re-run Test Case** to execute a fresh run and verify that the test passes!
