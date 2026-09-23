from __future__ import annotations

import os

from integrations.jira_adapter import FakeJiraAdapter, JiraAdapter, RequirementManagementAdapter
from project_model.models import (
    JiraBugDraft,
    JiraBugDraftRequest,
    JiraCreateBugRequest,
    JiraCreateBugResponse,
    JiraIssue,
    Requirement,
    RequirementCreate,
    RequirementStatus,
)

from app.repositories.integration_audit_repo import IntegrationAuditRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.test_run_repo import TestRunRepository


class JiraService:
    """Service orchestrating bidirectional Jira workflows: Requirement import and Bug ticket creation."""

    def __init__(
        self,
        requirement_repo: RequirementRepository,
        audit_repo: IntegrationAuditRepository,
        test_run_repo: TestRunRepository,
        adapter: RequirementManagementAdapter | None = None,
    ) -> None:
        self.requirement_repo = requirement_repo
        self.audit_repo = audit_repo
        self.test_run_repo = test_run_repo

        if adapter is not None:
            self.adapter = adapter
        elif os.environ.get("JIRA_API_TOKEN") and os.environ.get("JIRA_BASE_URL"):
            self.adapter = JiraAdapter()
        else:
            self.adapter = FakeJiraAdapter()

    def search_issues(self, query: str = "", limit: int = 20) -> list[JiraIssue]:
        return self.adapter.search_issues(query=query, limit=limit)

    def get_issue(self, issue_key: str) -> JiraIssue | None:
        return self.adapter.get_issue(issue_key=issue_key)

    async def import_requirements(
        self,
        issue_keys: list[str],
        project_id: str,
        user_id: str = "user",
    ) -> list[Requirement]:
        imported_requirements: list[Requirement] = []

        for key in issue_keys:
            issue = self.adapter.get_issue(key)
            if not issue:
                continue

            create_dto = RequirementCreate(
                project_id=project_id,
                title=f"[{issue.key}] {issue.summary}",
                description=issue.description or f"Imported from Jira issue {issue.key}",
                acceptance_criteria=issue.acceptance_criteria or "Imported from Jira",
                status=RequirementStatus.DRAFT,
                external_system="JIRA",
                external_id=issue.key,
                external_url=issue.url,
            )
            orm = await self.requirement_repo.create(create_dto)

            imported_requirements.append(
                Requirement(
                    id=orm.id,
                    project_id=orm.project_id,
                    title=orm.title,
                    description=orm.description or "",
                    acceptance_criteria=orm.acceptance_criteria or "",
                    status=RequirementStatus(orm.status),
                    external_system=orm.external_system,
                    external_id=orm.external_id,
                    external_url=orm.external_url,
                    created_at=orm.created_at,
                    updated_at=orm.updated_at,
                )
            )

            await self.audit_repo.record(
                system="JIRA",
                action="IMPORT_REQUIREMENT",
                target_id=issue.key,
                user_id=user_id,
                status="SUCCESS",
                details={
                    "requirement_id": orm.id,
                    "project_id": project_id,
                    "summary": issue.summary,
                },
            )

        return imported_requirements

    async def create_bug_draft(self, req: JiraBugDraftRequest) -> JiraBugDraft:
        failure = await self.test_run_repo.get_failure_by_id(req.failure_id)
        if not failure:
            raise ValueError(f"Failure record not found: {req.failure_id}")

        summary = f"[Defect] Automated Test Failure: {failure.test_name}"
        steps = [
            f"1. Run automated test suite node: `{failure.test_nodeid}`",
            "2. Observe test execution failure during step interaction.",
        ]
        if failure.failing_locator:
            steps.append(f"3. Failure occurred on locator: `{failure.failing_locator}`")

        description = (
            f"Automated test failed during execution run `{failure.run_id}`.\n\n"
            f"*Test Node*: `{failure.test_nodeid}`\n"
            f"*Classification*: `{failure.classification}`\n"
            f"*Exception*: `{failure.exception_type}`\n"
            f"*Error Message*: {failure.error_message}\n\n"
            f"*Suggested Action*: {failure.suggested_action or 'Investigate failure logs and trace.'}\n"
        )

        artifact_urls = []
        if failure.screenshot_path:
            artifact_urls.append(failure.screenshot_path)
        if failure.trace_path:
            artifact_urls.append(failure.trace_path)

        return JiraBugDraft(
            summary=summary,
            project_key=req.project_key,
            issue_type=req.issue_type,
            description=description,
            priority="High" if failure.classification in ("APPLICATION_BUG", "ENVIRONMENT_ISSUE") else "Medium",
            environment={"run_id": failure.run_id, "execution_id": failure.execution_id},
            steps_to_reproduce=steps,
            expected_result="Test passes with all assertions and locator matches succeeding.",
            actual_result=failure.error_message or "Test execution failed.",
            error_trace=failure.stack_trace or "",
            failure_id=failure.id,
            run_id=failure.run_id,
            artifact_urls=artifact_urls,
        )

    async def create_bug(
        self,
        request: JiraCreateBugRequest,
        user_id: str = "user",
    ) -> JiraCreateBugResponse:
        resp = self.adapter.create_bug(draft=request.draft, confirm_publish=request.confirm_publish)

        status_str = "SUCCESS" if resp.published else ("DRY_RUN" if resp.status == "DRY_RUN_VALIDATED" else "FAILED")
        await self.audit_repo.record(
            system="JIRA",
            action="CREATE_BUG",
            target_id=resp.key or request.draft.summary,
            user_id=user_id,
            status=status_str,
            details={
                "failure_id": request.draft.failure_id,
                "run_id": request.draft.run_id,
                "confirm_publish": request.confirm_publish,
                "url": resp.url,
                "message": resp.message,
            },
        )
        return resp
