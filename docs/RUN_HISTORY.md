# Run History Architecture & Stable Test Identity

## 1. Overview
The platform tracks persistent test execution outcomes across runs to support stability analytics, regression detection, and duration trends.

---

## 2. Stable Test Identity
Tests are uniquely identified using a deterministic pair:
- **`nodeid`**: The canonical pytest node identifier (e.g. `tests/test_cart.py::test_coupon_discount`).
- **`project_id`**: The QA project UUID owning the test workspace.

---

## 3. Data Model & Repositories
- **`TestRunORM`**: Root record of a batch execution run.
- **`TestExecutionORM`**: Individual pytest test result inside a run.
- **`RunHistoryRepository`**: Provides queries for:
  - Last $N$ executions of a specific `nodeid`.
  - Pass/Fail/Skip trends and P95 latency distributions.
  - Failure signature recurrence queries across runs.
