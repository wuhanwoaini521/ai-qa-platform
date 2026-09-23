from __future__ import annotations

import pytest
from app.repositories.run_history_repo import RunHistoryRepository
from httpx import AsyncClient
from project_model.models import FlakyClassification
from qa_core.failure.models import FailureCategory


@pytest.mark.asyncio
@pytest.mark.unit
async def test_flaky_algorithm_synthetic_patterns():
    repo = RunHistoryRepository(min_samples_threshold=3)

    # 1. Low sample guard (<3 samples)
    low_sample_score = repo.calculate_flaky_score([])
    assert low_sample_score.classification == FlakyClassification.INSUFFICIENT_DATA
    assert low_sample_score.score == 0.0

    class MockExec:
        def __init__(
            self, status: str, retry_count: int = 0, failure_category: str | None = None, duration_ms: float = 100.0
        ):
            self.status = status
            self.retry_count = retry_count
            self.failure_category = failure_category
            self.duration_ms = duration_ms
            self.started_at = None

    # 2. Always Pass -> STABLE
    always_pass = [MockExec("PASSED") for _ in range(6)]
    stable_score = repo.calculate_flaky_score(always_pass)
    assert stable_score.classification == FlakyClassification.STABLE
    assert stable_score.score == 0.0

    # 3. Always Fail -> PERSISTENT_FAILURE
    always_fail = [MockExec("FAILED", failure_category=FailureCategory.ASSERTION_FAILURE.value) for _ in range(6)]
    fail_score = repo.calculate_flaky_score(always_fail)
    assert fail_score.classification == FlakyClassification.PERSISTENT_FAILURE
    assert fail_score.failure_rate == 1.0

    # 4. Alternating: PASS -> FAIL -> PASS -> FAIL -> PASS -> LIKELY_FLAKY
    alternating = [
        MockExec("PASSED"),
        MockExec("FAILED", failure_category=FailureCategory.TIMING_ISSUE.value),
        MockExec("PASSED"),
        MockExec("FAILED", failure_category=FailureCategory.TIMING_ISSUE.value),
        MockExec("PASSED"),
    ]
    flaky_score = repo.calculate_flaky_score(alternating)
    assert flaky_score.classification == FlakyClassification.LIKELY_FLAKY
    assert flaky_score.score > 0.3
    assert flaky_score.alternation_rate > 0.5
    assert flaky_score.main_failure_category == FailureCategory.TIMING_ISSUE.value

    # 5. Fail then rerun recovered -> LIKELY_FLAKY
    rerun_recovered = [
        MockExec("PASSED", retry_count=1),
        MockExec("FAILED", failure_category=FailureCategory.LOCATOR_CHANGED.value),
        MockExec("PASSED", retry_count=1),
        MockExec("PASSED"),
    ]
    rerun_score = repo.calculate_flaky_score(rerun_recovered)
    assert rerun_score.rerun_recovery_rate > 0.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_flaky_and_history_api_endpoints(client: AsyncClient):
    # 1. Create project
    proj_res = await client.post("/api/projects", json={"name": "History Intelligence Suite"})
    proj_id = proj_res.json()["id"]

    # 2. Query Flaky list
    flaky_res = await client.get(f"/api/flaky?project_id={proj_id}")
    assert flaky_res.status_code == 200
    assert isinstance(flaky_res.json(), list)

    # 3. Query specific test history
    hist_res = await client.get(f"/api/flaky/history?nodeid=tests/test_cart.py::test_add_to_cart&project_id={proj_id}")
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert "nodeid" in hist
    assert "trend" in hist
    assert "flaky_score" in hist
    assert hist["flaky_score"]["classification"] in [
        "STABLE",
        "LIKELY_FLAKY",
        "PERSISTENT_FAILURE",
        "INSUFFICIENT_DATA",
    ]

    # 4. Query Dashboard Intelligence
    dash_res = await client.get("/api/dashboard/stats")
    assert dash_res.status_code == 200
    dash = dash_res.json()
    assert "flaky_tests_count" in dash
    assert "rerun_recovery_count" in dash
    assert "pass_rate_today" in dash
