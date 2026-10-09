from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from typing import Any, Protocol, runtime_checkable

from project_model.models import (
    TestRailCase,
    TestRailPublishPreview,
    TestRailPublishPreviewItem,
    TestRailPublishRequest,
    TestRailPublishResponse,
)


@runtime_checkable
class TestManagementAdapter(Protocol):
    """Adapter interface for Test Case Management systems (e.g. TestRail)."""

    __test__ = False

    def get_case(self, case_id: str) -> TestRailCase | None:
        """Fetch test case details by ID (e.g. 'C101' or '101')."""
        ...

    def list_cases(self, suite_id: str = "S1", limit: int = 50) -> list[TestRailCase]:
        """List cases in a suite."""
        ...

    def preview_publish(
        self,
        run_id: str,
        suite_id: str,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishPreview:
        """Generate a dry-run preview of test result mapping before pushing to TestRail."""
        ...

    def publish_results(
        self,
        request: TestRailPublishRequest,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishResponse:
        """Publish test run results to TestRail."""
        ...


DEFAULT_STATUS_MAPPING = {
    "PASSED": "Passed",
    "FAILED": "Failed",
    "BROKEN": "Blocked",
    "SKIPPED": "Retest",
}

# TestRail standard status IDs: 1=Passed, 2=Blocked, 3=Untested, 4=Retest, 5=Failed
TESTRAIL_STATUS_IDS = {
    "Passed": 1,
    "Blocked": 2,
    "Untested": 3,
    "Retest": 4,
    "Failed": 5,
}


class FakeTestRailAdapter:
    """In-memory TestRail adapter for testing and offline development."""

    __test__ = False

    def __init__(self, initial_cases: list[TestRailCase] | None = None) -> None:
        self.cases: dict[str, TestRailCase] = {}
        self.published_runs: list[dict[str, Any]] = []
        self._next_run_id = 9001

        defaults = initial_cases or [
            TestRailCase(
                id="C101",
                title="Verify successful login with valid credentials",
                section="Authentication",
                suite_id="S101",
                url="https://testrail.example.com/index.php?/cases/view/101",
            ),
            TestRailCase(
                id="C102",
                title="Verify shopping cart price recalculation on coupon apply",
                section="Checkout",
                suite_id="S101",
                url="https://testrail.example.com/index.php?/cases/view/102",
            ),
            TestRailCase(
                id="C103",
                title="Verify export to CSV contains all required columns",
                section="Reporting",
                suite_id="S101",
                url="https://testrail.example.com/index.php?/cases/view/103",
            ),
            TestRailCase(
                id="C104",
                title="Verify error handling when backend returns 500",
                section="Error Handling",
                suite_id="S101",
                url="https://testrail.example.com/index.php?/cases/view/104",
            ),
        ]
        for c in defaults:
            self.cases[c.id.upper()] = c

    def get_case(self, case_id: str) -> TestRailCase | None:
        norm_id = case_id.strip().upper()
        if not norm_id.startswith("C"):
            norm_id = f"C{norm_id}"
        return self.cases.get(norm_id)

    def list_cases(self, suite_id: str = "S101", limit: int = 50) -> list[TestRailCase]:
        return list(self.cases.values())[:limit]

    def preview_publish(
        self,
        run_id: str,
        suite_id: str,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishPreview:
        mappings = case_mappings or {}
        items: list[TestRailPublishPreviewItem] = []
        mapped_count = 0
        unmapped_count = 0

        for exc in executions:
            nodeid = exc.get("nodeid") or exc.get("test_name", "test")
            test_name = exc.get("test_name", nodeid)
            raw_status = (exc.get("status") or "UNKNOWN").upper()
            mapped_status = DEFAULT_STATUS_MAPPING.get(raw_status, "Untested")

            # Check if execution or mapping defines external case id
            ext_id = exc.get("external_case_id") or mappings.get(nodeid) or mappings.get(test_name)
            if not ext_id:
                # Try heuristic match against fake cases
                for c_id, case in self.cases.items():
                    if c_id.lower() in nodeid.lower() or case.title.lower() in test_name.lower():
                        ext_id = c_id
                        break

            if ext_id:
                mapped_count += 1
            else:
                unmapped_count += 1

            error_msg = exc.get("error_message", "")
            comment = f"Executed via AI QA Platform. Duration: {exc.get('duration_ms', 0)}ms. {error_msg}".strip()

            items.append(
                TestRailPublishPreviewItem(
                    test_nodeid=nodeid,
                    test_name=test_name,
                    external_case_id=ext_id,
                    pytest_status=raw_status,
                    mapped_testrail_status=mapped_status,
                    comment=comment,
                )
            )

        return TestRailPublishPreview(
            run_id=run_id,
            suite_id=suite_id,
            total_tests=len(executions),
            mapped_tests=mapped_count,
            unmapped_tests=unmapped_count,
            items=items,
        )

    def publish_results(
        self,
        request: TestRailPublishRequest,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishResponse:
        preview = self.preview_publish(
            run_id=request.run_id,
            suite_id=request.suite_id,
            executions=executions,
            case_mappings=case_mappings,
        )

        if not request.confirm_publish:
            return TestRailPublishResponse(
                success=True,
                published=False,
                testrail_run_id=None,
                total_published=preview.mapped_tests,
                message=f"Dry-run publish preview generated: {preview.mapped_tests} mapped, {preview.unmapped_tests} unmapped.",
            )

        run_id_str = f"R{self._next_run_id}"
        self._next_run_id += 1

        record = {
            "testrail_run_id": run_id_str,
            "suite_id": request.suite_id,
            "platform_run_id": request.run_id,
            "results": [item.model_dump() for item in preview.items if item.external_case_id],
        }
        self.published_runs.append(record)

        return TestRailPublishResponse(
            success=True,
            published=True,
            testrail_run_id=run_id_str,
            total_published=preview.mapped_tests,
            message=f"Successfully published {preview.mapped_tests} test results to TestRail run {run_id_str}.",
        )


class TestRailAdapter:
    """Production REST API adapter for TestRail API v2."""

    __test__ = False

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.email = email or ""
        self.api_key = api_key or ""
        self.timeout = timeout_seconds

    def _get_headers(self) -> dict[str, str]:
        auth_pair = f"{self.email}:{self.api_key}".encode("utf-8")
        auth_b64 = base64.b64encode(auth_pair).decode("utf-8")
        return {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_case(self, case_id: str) -> TestRailCase | None:
        if not self.base_url or not self.api_key:
            return None
        numeric_id = case_id.lstrip("Cc")
        url = f"{self.base_url}/index.php?/api/v2/get_case/{numeric_id}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return TestRailCase(
                    id=f"C{data.get('id')}",
                    title=data.get("title", ""),
                    section=str(data.get("section_id", "")),
                    suite_id=str(data.get("suite_id", "")),
                    url=f"{self.base_url}/index.php?/cases/view/{data.get('id')}",
                )
        except Exception:
            return None

    def list_cases(self, suite_id: str = "1", limit: int = 50) -> list[TestRailCase]:
        if not self.base_url or not self.api_key:
            return []
        numeric_suite = suite_id.lstrip("Ss")
        url = f"{self.base_url}/index.php?/api/v2/get_cases/1&suite_id={numeric_suite}&limit={limit}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cases_list = data if isinstance(data, list) else data.get("cases", [])
                return [
                    TestRailCase(
                        id=f"C{c.get('id')}",
                        title=c.get("title", ""),
                        section=str(c.get("section_id", "")),
                        suite_id=str(c.get("suite_id", "")),
                        url=f"{self.base_url}/index.php?/cases/view/{c.get('id')}",
                    )
                    for c in cases_list
                ]
        except Exception:
            return []

    def preview_publish(
        self,
        run_id: str,
        suite_id: str,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishPreview:
        mappings = case_mappings or {}
        items: list[TestRailPublishPreviewItem] = []
        mapped_count = 0
        unmapped_count = 0

        for exc in executions:
            nodeid = exc.get("nodeid") or exc.get("test_name", "test")
            test_name = exc.get("test_name", nodeid)
            raw_status = (exc.get("status") or "UNKNOWN").upper()
            mapped_status = DEFAULT_STATUS_MAPPING.get(raw_status, "Untested")
            ext_id = exc.get("external_case_id") or mappings.get(nodeid) or mappings.get(test_name)

            if ext_id:
                mapped_count += 1
            else:
                unmapped_count += 1

            error_msg = exc.get("error_message", "")
            comment = f"Executed via AI QA Platform. Duration: {exc.get('duration_ms', 0)}ms. {error_msg}".strip()

            items.append(
                TestRailPublishPreviewItem(
                    test_nodeid=nodeid,
                    test_name=test_name,
                    external_case_id=ext_id,
                    pytest_status=raw_status,
                    mapped_testrail_status=mapped_status,
                    comment=comment,
                )
            )

        return TestRailPublishPreview(
            run_id=run_id,
            suite_id=suite_id,
            total_tests=len(executions),
            mapped_tests=mapped_count,
            unmapped_tests=unmapped_count,
            items=items,
        )

    def publish_results(
        self,
        request: TestRailPublishRequest,
        executions: list[dict[str, Any]],
        case_mappings: dict[str, str] | None = None,
    ) -> TestRailPublishResponse:
        preview = self.preview_publish(
            run_id=request.run_id,
            suite_id=request.suite_id,
            executions=executions,
            case_mappings=case_mappings,
        )

        if not request.confirm_publish:
            return TestRailPublishResponse(
                success=True,
                published=False,
                testrail_run_id=None,
                total_published=preview.mapped_tests,
                message=f"Dry-run passed: {preview.mapped_tests} mapped, {preview.unmapped_tests} unmapped.",
            )

        if not self.base_url or not self.api_key:
            return TestRailPublishResponse(
                success=False,
                published=False,
                testrail_run_id=None,
                total_published=0,
                message="TestRail credentials not configured.",
            )

        # Create test run in project 1 / suite_id
        numeric_suite = int(request.suite_id.lstrip("Ss") or "1")
        url_add_run = f"{self.base_url}/index.php?/api/v2/add_run/1"
        run_payload = {
            "suite_id": numeric_suite,
            "name": f"Automated Run {request.run_id}",
            "description": f"Published from AI QA Platform for run {request.run_id}",
        }
        try:
            req = urllib.request.Request(
                url_add_run,
                data=json.dumps(run_payload).encode("utf-8"),
                headers=self._get_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                run_data = json.loads(resp.read().decode("utf-8"))
                tr_run_id = run_data.get("id")

            # Post results
            results_payload = []
            for item in preview.items:
                if not item.external_case_id:
                    continue
                cid = int(item.external_case_id.lstrip("Cc"))
                status_id = TESTRAIL_STATUS_IDS.get(item.mapped_testrail_status, 1)
                results_payload.append(
                    {
                        "case_id": cid,
                        "status_id": status_id,
                        "comment": item.comment,
                    }
                )

            if results_payload and tr_run_id:
                url_add_results = f"{self.base_url}/index.php?/api/v2/add_results_for_cases/{tr_run_id}"
                req2 = urllib.request.Request(
                    url_add_results,
                    data=json.dumps({"results": results_payload}).encode("utf-8"),
                    headers=self._get_headers(),
                    method="POST",
                )
                with urllib.request.urlopen(req2, timeout=self.timeout) as resp2:
                    resp2.read()

            return TestRailPublishResponse(
                success=True,
                published=True,
                testrail_run_id=f"R{tr_run_id}",
                total_published=len(results_payload),
                message=f"Successfully published {len(results_payload)} test results to TestRail run R{tr_run_id}.",
            )
        except Exception as exc:
            return TestRailPublishResponse(
                success=False,
                published=False,
                testrail_run_id=None,
                total_published=0,
                message=f"TestRail API call failed: {exc}",
            )
