# TestRail Integration Guide

## 1. Overview
The **AI QA Platform** integrates with **TestRail Test Case Management** to link automated test cases and push execution runs & test results.

```text
    Platform Test Cases (C101, C102)
          ↓
    Pytest Execution Run
          ↓
    TestRail Result Mapping (Preview & Dry-Run)
          ↓
    TestRail API v2 (`add_run`, `add_results_for_cases`)
          ↓
    TestRail Test Run & Status Summary
```

---

## 2. Core Capabilities

### 2.1 Test Case Linking & Retrieval
- Test cases in the platform store `external_system="TESTRAIL"` and `external_case_id` (e.g. `C101`).
- Direct navigation links to TestRail case view (`https://testrail.example.com/index.php?/cases/view/101`).
- Endpoint `/api/testrail/cases` retrieves available test cases in a TestRail suite.

### 2.2 Execution Result Publishing & Mapping
- **Status Mapping**:
  - `PASSED` → TestRail `Passed` (ID: 1)
  - `FAILED` → TestRail `Failed` (ID: 5)
  - `BROKEN` / `ERROR` → TestRail `Blocked` (ID: 2)
  - `SKIPPED` → TestRail `Retest` (ID: 4)
- **Preview & Dry-Run Safe**: Endpoint `/api/testrail/runs/{run_id}/preview` generates an interactive preview showing mapped vs unmapped test cases before pushing.
- **Run Creation**: Creates a new TestRail run (e.g. `R9001`) and pushes test results with duration, error trace, and comments.

### 2.3 Audit Logging
- Every publish action (dry-run or real) is recorded in `integration_audits` (`/api/audit/integrations?system=TESTRAIL`).

---

## 3. Configuration
Configure TestRail credentials via environment variables:

```bash
TESTRAIL_BASE_URL="https://your-team.testrail.io"
TESTRAIL_EMAIL="qa-bot@example.com"
TESTRAIL_API_KEY="your-testrail-api-key"
```

When unconfigured, the platform automatically activates `FakeTestRailAdapter` for testing and local development.
