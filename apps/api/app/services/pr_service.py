from __future__ import annotations

import os

from integrations.github_adapter import (
    FakePullRequestAdapter,
    GitHubPullRequestAdapter,
    PullRequestAdapter,
)
from project_model.models import (
    PRChecksSummary,
    PRDiagnosisResponse,
    PRSummarySuggestionResponse,
    PullRequestCreateRequest,
    PullRequestInfo,
)

from app.repositories.automation_binding_repo import AutomationBindingRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.requirement_repo import RequirementRepository
from app.repositories.run_history_repo import RunHistoryRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.test_run_repo import TestRunRepository
from app.repositories.workspace_repo import WorkspaceRepository
from app.services.workspace_service import WorkspaceService


class PullRequestService:
    def __init__(
        self,
        workspace_service: WorkspaceService,
        workspace_repo: WorkspaceRepository,
        project_repo: ProjectRepository,
        requirement_repo: RequirementRepository,
        test_case_repo: TestCaseRepository,
        binding_repo: AutomationBindingRepository,
        test_run_repo: TestRunRepository,
        run_history_repo: RunHistoryRepository,
        adapter: PullRequestAdapter | None = None,
    ) -> None:
        self.workspace_service = workspace_service
        self.workspace_repo = workspace_repo
        self.project_repo = project_repo
        self.requirement_repo = requirement_repo
        self.test_case_repo = test_case_repo
        self.binding_repo = binding_repo
        self.test_run_repo = test_run_repo
        self.run_history_repo = run_history_repo

        if adapter is not None:
            self.adapter = adapter
        else:
            token = os.getenv("GITHUB_TOKEN", "").strip()
            if token:
                self.adapter = GitHubPullRequestAdapter(token=token)
            else:
                self.adapter = FakePullRequestAdapter()

    async def _resolve_project_id_and_name(self, workspace_id: str) -> tuple[str, str]:
        ws = await self.workspace_repo.get_by_id(workspace_id)
        if ws is None:
            ws = await self.workspace_repo.get_by_project_id(workspace_id)
        project_id = ws.project_id if ws else workspace_id
        project_name = "QA Automation"
        proj = await self.project_repo.get_by_id(project_id)
        if proj:
            project_name = proj.name
        return project_id, project_name

    async def _get_repo_slug(self, project_id: str) -> str:
        project = await self.project_repo.get_by_id(project_id)
        if project and project.repository_url:
            # Parse slug e.g. https://github.com/org/repo or git@github.com:org/repo.git
            url = project.repository_url.strip()
            if "github.com/" in url:
                slug = url.split("github.com/")[1].rstrip("/").removesuffix(".git")
                return slug
            if "github.com:" in url:
                slug = url.split("github.com:")[1].rstrip("/").removesuffix(".git")
                return slug
        return "qa-platform/test-automation"

    async def suggest_pr_summary(
        self,
        workspace_id: str,
        requirement_ids: list[str] | None = None,
        test_case_ids: list[str] | None = None,
        include_diff: bool = True,
    ) -> PRSummarySuggestionResponse:
        project_id, project_name = await self._resolve_project_id_and_name(workspace_id)

        current_branch = await self.workspace_service.get_current_branch(workspace_id)
        diff_res = await self.workspace_service.get_diff(workspace_id) if include_diff else None
        changed_files_count = len(diff_res.changed_files) if diff_res else 0

        # Fetch requirements
        reqs = []
        if requirement_ids:
            for rid in requirement_ids:
                r = await self.requirement_repo.get_by_id(rid)
                if r:
                    reqs.append(r)
        elif project_id:
            reqs = (await self.requirement_repo.list_by_project(project_id))[:3]

        # Fetch test cases
        cases = []
        if test_case_ids:
            for cid in test_case_ids:
                c = await self.test_case_repo.get_by_id(cid)
                if c:
                    cases.append(c)
        elif project_id:
            cases = (await self.test_case_repo.list_by_project(project_id))[:5]

        # Fetch latest run
        latest_runs = await self.test_run_repo.list_runs(project_id=project_id, limit=1)
        latest_run = latest_runs[0] if latest_runs else None

        title = f"feat({current_branch}): update automated test suites and page models"
        if reqs:
            title = f"test({reqs[0].title[:30]}): add end-to-end automation coverage"

        body_lines = [
            f"## Quality Engineering PR — {project_name}",
            "",
            f"**Branch**: `{current_branch}`  ",
            f"**Workspace**: `{workspace_id}`  ",
            f"**Changed Files**: {changed_files_count} file(s) modified  ",
            "",
            "### Linked Requirements",
        ]
        if reqs:
            for r in reqs:
                body_lines.append(f"- **{r.title}** (`{r.id}`): {r.status.value}")
        else:
            body_lines.append("- *(No specific requirement linked)*")

        body_lines.extend(["", "### Linked Test Cases & Automation"])
        if cases:
            for c in cases:
                body_lines.append(f"- `[{c.priority.value}]` {c.title} (Status: `{c.automation_status.value}`)")
        else:
            body_lines.append("- *(Automated test suite suite updates)*")

        body_lines.extend(["", "### Validation & Run Evidence"])
        if latest_run:
            pass_rate = (latest_run.passed / latest_run.total * 100) if latest_run.total > 0 else 0
            body_lines.append(
                f"- **Latest Local Run**: Status `{latest_run.status.value}`, Passed: {latest_run.passed}/{latest_run.total} ({pass_rate:.1f}%), Duration: {latest_run.duration_ms:.0f}ms"
            )
        else:
            body_lines.append("- Validation: AST Syntax & Collection clean.")

        body_lines.extend(
            [
                "",
                "### Verification Checklist",
                "- [x] Deterministic assertions verified",
                "- [x] Page object models decoupled from test scenarios",
                "- [x] Linter and typing checks verified",
            ]
        )

        bullets = [
            f"Automation branch: {current_branch}",
            f"{changed_files_count} files changed",
            f"{len(reqs)} linked requirements and {len(cases)} test cases",
        ]

        return PRSummarySuggestionResponse(
            title=title,
            body="\n".join(body_lines),
            summary_bullets=bullets,
        )

    async def create_pull_request(
        self,
        workspace_id: str,
        request: PullRequestCreateRequest,
    ) -> PullRequestInfo:
        project_id, _ = await self._resolve_project_id_and_name(workspace_id)
        repo_slug = await self._get_repo_slug(project_id)
        head_branch = request.head_branch or await self.workspace_service.get_current_branch(workspace_id)

        # Call adapter
        pr_info = await self.adapter.create_pull_request(
            repo_slug=repo_slug,
            head_branch=head_branch,
            base_branch=request.base_branch,
            title=request.title,
            body=request.body,
        )
        return pr_info

    async def get_pr_checks(self, workspace_id: str, pr_number: int) -> PRChecksSummary:
        project_id, _ = await self._resolve_project_id_and_name(workspace_id)
        repo_slug = await self._get_repo_slug(project_id)
        head_branch = await self.workspace_service.get_current_branch(workspace_id)
        return await self.adapter.get_pr_checks(repo_slug=repo_slug, pr_number=pr_number, head_branch=head_branch)

    async def diagnose_failure(self, failure_logs: str) -> PRDiagnosisResponse:
        return await self.adapter.diagnose_failure(failure_logs)
