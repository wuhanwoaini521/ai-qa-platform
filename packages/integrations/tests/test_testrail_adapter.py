from __future__ import annotations

from integrations.testrail_adapter import FakeTestRailAdapter, TestManagementAdapter, TestRailAdapter
from project_model.models import TestRailPublishRequest


def test_fake_testrail_adapter_implements_protocol():
    adapter = FakeTestRailAdapter()
    assert isinstance(adapter, TestManagementAdapter)


def test_fake_testrail_adapter_get_and_list():
    adapter = FakeTestRailAdapter()
    cases = adapter.list_cases("S101")
    assert len(cases) >= 3

    c101 = adapter.get_case("101")
    assert c101 is not None
    assert c101.id == "C101"
    assert "login" in c101.title.lower()

    missing = adapter.get_case("C999")
    assert missing is None


def test_fake_testrail_preview_and_publish():
    adapter = FakeTestRailAdapter()
    executions = [
        {
            "nodeid": "tests/test_auth.py::test_login_success",
            "test_name": "Verify successful login with valid credentials",
            "status": "PASSED",
            "duration_ms": 120,
        },
        {
            "nodeid": "tests/test_checkout.py::test_coupon_apply",
            "test_name": "test_coupon_apply",
            "status": "FAILED",
            "duration_ms": 450,
            "error_message": "AssertionError: 20 != 15",
            "external_case_id": "C102",
        },
        {
            "nodeid": "tests/test_unknown.py::test_custom",
            "test_name": "test_custom",
            "status": "PASSED",
            "duration_ms": 50,
        },
    ]

    preview = adapter.preview_publish(
        run_id="run_100",
        suite_id="S101",
        executions=executions,
    )

    assert preview.total_tests == 3
    assert preview.mapped_tests == 2  # C101 via title heuristic, C102 via external_case_id
    assert preview.unmapped_tests == 1

    # Dry-run publish
    req_dry = TestRailPublishRequest(run_id="run_100", suite_id="S101", confirm_publish=False)
    resp_dry = adapter.publish_results(req_dry, executions=executions)
    assert resp_dry.success is True
    assert resp_dry.published is False
    assert resp_dry.total_published == 2

    # Confirmed publish
    req_live = TestRailPublishRequest(run_id="run_100", suite_id="S101", confirm_publish=True)
    resp_live = adapter.publish_results(req_live, executions=executions)
    assert resp_live.success is True
    assert resp_live.published is True
    assert resp_live.testrail_run_id == "R9001"
    assert resp_live.total_published == 2


def test_testrail_adapter_dry_run():
    adapter = TestRailAdapter(base_url="", email="", api_key="")
    req = TestRailPublishRequest(run_id="run_200", confirm_publish=False)
    resp = adapter.publish_results(req, executions=[])
    assert resp.success is True
    assert resp.published is False
