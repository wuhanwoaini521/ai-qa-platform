from __future__ import annotations

import pytest
from app.services.quality_intelligence_service import QualityIntelligenceService
from project_model.models import FlakyClassification, FlakyScore, FlakyTestItem
from project_model.models import TestTrend as TrendModel


class EmptyTestCaseRepository:
    async def list_by_project(self, project_id: str):
        return []


class EmptyRunRepository:
    def __init__(self):
        self.project_id = None

    async def list_failures(self, limit: int = 20, project_id: str | None = None):
        self.project_id = project_id
        return []


class HistoryRepository:
    def __init__(self, items: list[FlakyTestItem]):
        self.items = items

    async def list_flaky_tests(self, project_id: str | None = None):
        return self.items


def _service(items: list[FlakyTestItem]) -> QualityIntelligenceService:
    return QualityIntelligenceService(
        requirement_repo=object(),
        test_case_repo=EmptyTestCaseRepository(),
        test_design_repo=object(),
        binding_repo=object(),
        test_run_repo=EmptyRunRepository(),
        history_repo=HistoryRepository(items),
    )


@pytest.mark.asyncio
async def test_risk_matrix_scopes_failure_reads_to_project():
    repository = EmptyRunRepository()
    service = _service([])
    service.test_run_repo = repository

    await service.calculate_risk_matrix("proj_demo")

    assert repository.project_id == "proj_demo"


@pytest.mark.asyncio
async def test_insufficient_flaky_samples_do_not_reduce_quality_score():
    item = FlakyTestItem(
        nodeid="tests/test_cart.py::test_add_to_cart",
        test_name="test_add_to_cart",
        project_id="proj_demo",
        flaky_score=FlakyScore(sample_count=1, classification=FlakyClassification.INSUFFICIENT_DATA),
        trend=TrendModel(sample_count=1),
    )

    result = await _service([item]).calculate_risk_matrix("proj_demo")

    assert result.overall_quality_score == 100.0
    assert result.overall_risk_level.value == "LOW"
    assert result.flaky_test_count == 0
    assert result.risks == []


@pytest.mark.asyncio
async def test_persistent_failures_are_reported_as_high_risk():
    item = FlakyTestItem(
        nodeid="tests/test_cart.py::test_add_to_cart",
        test_name="test_add_to_cart",
        project_id="proj_demo",
        flaky_score=FlakyScore(sample_count=6, classification=FlakyClassification.PERSISTENT_FAILURE),
        trend=TrendModel(sample_count=6),
    )

    result = await _service([item]).calculate_risk_matrix("proj_demo")

    assert result.overall_quality_score == 90.0
    assert result.overall_risk_level.value == "HIGH"
    assert result.flaky_test_count == 0
    assert result.risks[0].risk_level.value == "HIGH"
