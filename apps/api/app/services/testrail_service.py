from __future__ import annotations

import os
from typing import Any

from integrations.testrail_adapter import FakeTestRailAdapter, TestManagementAdapter, TestRailAdapter
from project_model.models import (
    TestRailCase,
    TestRailPublishPreview,
    TestRailPublishRequest,
    TestRailPublishResponse,
)

from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository


class TestRailService:
    """Service orchestrating TestRail test management integration: case viewing and test result publishing."""

    def __init__(
        self,
        test_run_repo: TestRunRepository,
        test_case_repo: TestCaseRepository,
        audit_repo: IntegrationAuditRepository,
        adapter: TestManagementAdapter | None = None,
    ) -> None:
        self.test_run_repo = test_run_repo
        self.test_case_repo = test_case_repo
        self.audit_repo = audit_repo

        if adapter is not None:
            self.adapter = adapter
        elif os.environ.get("TESTRAIL_API_KEY") and os.environ.get("TESTRAIL_BASE_URL"):
            self.adapter = TestRailAdapter()
        else:
            self.adapter = FakeTestRailAdapter()

    def list_cases(self, suite_id: str = "S101", limit: int = 50) -> list[TestRailCase]:
        return self.adapter.list_cases(suite_id=suite_id, limit=limit)

    def get_case(self, case_id: str) -> TestRailCase | None:
        return self.adapter.get_case(case_id=case_id)

    async def _gather_executions(self, run_id: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
        executions = await self.test_run_repo.list_executions(run_id)
        exec_dicts: list[dict[str, Any]] = []
        for exc in executions:
            exec_dicts.append(
                {
                    "nodeid": exc.nodeid,
                    "test_name": exc.test_name,
                    "status": exc.status,
                    "duration_ms": exc.duration_ms,
                    "error_message": exc.error_message or "",
                }
            )

        # Lookup platform test cases with external_case_id mappings
        all_cases = await self.test_case_repo.list_all()
        mappings: dict[str, str] = {}
        for tc in all_cases:
            if tc.external_case_id:
                mappings[tc.title] = tc.external_case_id

        return exec_dicts, mappings

    async def preview_publish(self, run_id: str, suite_id: str = "S101") -> TestRailPublishPreview:
        exec_dicts, mappings = await self._gather_executions(run_id)
        return self.adapter.preview_publish(
            run_id=run_id,
            suite_id=suite_id,
            executions=exec_dicts,
            case_mappings=mappings,
        )

    async def publish_results(
        self,
        request: TestRailPublishRequest,
        user_id: str = "user",
    ) -> TestRailPublishResponse:
        exec_dicts, mappings = await self._gather_executions(request.run_id)
        resp = self.adapter.publish_results(
            request=request,
            executions=exec_dicts,
            case_mappings=mappings,
        )

        status_str = "SUCCESS" if resp.published else ("DRY_RUN" if resp.success else "FAILED")
        await self.audit_repo.record(
            system="TESTRAIL",
            action="PUBLISH_RESULT",
            target_id=resp.testrail_run_id or request.run_id,
            user_id=user_id,
            status=status_str,
            details={
                "platform_run_id": request.run_id,
                "suite_id": request.suite_id,
                "confirm_publish": request.confirm_publish,
                "total_published": resp.total_published,
                "message": resp.message,
            },
        )
        return resp
