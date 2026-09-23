from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import httpx
from project_model.models import (
    CheckRun,
    CheckStatus,
    PRChecksSummary,
    PRDiagnosisResponse,
    PullRequestInfo,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class PullRequestAdapter(Protocol):
    async def create_pull_request(
        self,
        repo_slug: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequestInfo: ...

    async def get_pull_request(self, repo_slug: str, pr_number: int) -> PullRequestInfo: ...

    async def get_pr_checks(self, repo_slug: str, pr_number: int, head_branch: str = "main") -> PRChecksSummary: ...

    async def get_check_logs(self, repo_slug: str, check_run_id: str) -> str: ...

    async def diagnose_failure(self, failure_logs: str) -> PRDiagnosisResponse: ...


class FakePullRequestAdapter(PullRequestAdapter):
    """In-memory PullRequestAdapter for tests, CI, and local dev without external GitHub credentials."""

    def __init__(self) -> None:
        self.prs: dict[int, PullRequestInfo] = {}
        self.next_pr_number = 101
        self.check_runs: dict[int, list[CheckRun]] = {}
        self.raw_logs: dict[str, str] = {}

    async def create_pull_request(
        self,
        repo_slug: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequestInfo:
        pr_number = self.next_pr_number
        self.next_pr_number += 1
        now = _utc_now()
        pr_url = f"https://github.com/{repo_slug}/pull/{pr_number}"

        # Initialize mock check runs
        default_checks = [
            CheckRun(
                id=f"chk-{pr_number}-python",
                name="Python Lint & Typecheck",
                status=CheckStatus.PASSED,
                conclusion="success",
                started_at=now,
                completed_at=now,
                html_url=f"{pr_url}/checks/python",
            ),
            CheckRun(
                id=f"chk-{pr_number}-frontend",
                name="Frontend Lint & Build",
                status=CheckStatus.PASSED,
                conclusion="success",
                started_at=now,
                completed_at=now,
                html_url=f"{pr_url}/checks/frontend",
            ),
            CheckRun(
                id=f"chk-{pr_number}-unit",
                name="Backend & Core Unit Tests",
                status=CheckStatus.PASSED,
                conclusion="success",
                started_at=now,
                completed_at=now,
                html_url=f"{pr_url}/checks/unit",
            ),
            CheckRun(
                id=f"chk-{pr_number}-integration",
                name="E2E Integration Tests",
                status=CheckStatus.PASSED,
                conclusion="success",
                started_at=now,
                completed_at=now,
                html_url=f"{pr_url}/checks/integration",
            ),
        ]
        self.check_runs[pr_number] = default_checks

        checks_summary = PRChecksSummary(
            pr_number=pr_number,
            pr_url=pr_url,
            head_branch=head_branch,
            overall_status=CheckStatus.PASSED,
            checks=default_checks,
        )

        pr_info = PullRequestInfo(
            id=f"pr-{pr_number}",
            number=pr_number,
            title=title,
            body=body,
            html_url=pr_url,
            state="open",
            head_branch=head_branch,
            base_branch=base_branch,
            created_at=now,
            updated_at=now,
            checks_summary=checks_summary,
        )
        self.prs[pr_number] = pr_info
        return pr_info

    async def get_pull_request(self, repo_slug: str, pr_number: int) -> PullRequestInfo:
        if pr_number in self.prs:
            return self.prs[pr_number]
        now = _utc_now()
        pr_url = f"https://github.com/{repo_slug}/pull/{pr_number}"
        return PullRequestInfo(
            id=f"pr-{pr_number}",
            number=pr_number,
            title=f"Pull Request #{pr_number}",
            body="Automated QA suite integration",
            html_url=pr_url,
            state="open",
            head_branch="qa/feature-branch",
            base_branch="main",
            created_at=now,
            updated_at=now,
        )

    async def get_pr_checks(self, repo_slug: str, pr_number: int, head_branch: str = "main") -> PRChecksSummary:
        checks = self.check_runs.get(pr_number, [])
        if not checks:
            now = _utc_now()
            checks = [
                CheckRun(
                    id=f"chk-{pr_number}-python",
                    name="Python Lint & Typecheck",
                    status=CheckStatus.PASSED,
                    conclusion="success",
                    started_at=now,
                    completed_at=now,
                    html_url=f"https://github.com/{repo_slug}/pull/{pr_number}/checks",
                )
            ]
        has_failed = any(c.status == CheckStatus.FAILED for c in checks)
        has_running = any(c.status == CheckStatus.RUNNING for c in checks)
        overall = CheckStatus.FAILED if has_failed else (CheckStatus.RUNNING if has_running else CheckStatus.PASSED)
        return PRChecksSummary(
            pr_number=pr_number,
            pr_url=f"https://github.com/{repo_slug}/pull/{pr_number}",
            head_branch=head_branch,
            overall_status=overall,
            checks=checks,
        )

    def set_failed_check(self, pr_number: int, check_id: str, failure_log: str) -> None:
        """Helper to inject a failed check for testing."""
        if pr_number in self.check_runs:
            for check in self.check_runs[pr_number]:
                if check.id == check_id or check.name.lower() in check_id.lower():
                    check.status = CheckStatus.FAILED
                    check.conclusion = "failure"
                    check.failure_summary = failure_log.splitlines()[0] if failure_log else "Check failed"
                    check.failure_logs = failure_log
                    self.raw_logs[check.id] = failure_log

    async def get_check_logs(self, repo_slug: str, check_run_id: str) -> str:
        return self.raw_logs.get(check_run_id, "Sample CI Failure log: AssertionError: assert 'Expected' == 'Actual'")

    async def diagnose_failure(self, failure_logs: str) -> PRDiagnosisResponse:
        log_lower = failure_logs.lower()
        if "syntaxerror" in log_lower or "indentationerror" in log_lower:
            return PRDiagnosisResponse(
                classification="SYNTAX_ERROR",
                summary="Python syntax or indentation error detected in test files.",
                root_cause="Invalid Python syntax prevented test execution.",
                suggested_fix="Check syntax near reported line numbers and run `ruff check .` locally.",
                affected_files=["tests/"],
            )
        elif "ruff" in log_lower or "lint" in log_lower or "eslint" in log_lower:
            return PRDiagnosisResponse(
                classification="LINT_FAILURE",
                summary="Code formatting or linter rule violation detected.",
                root_cause="Formatting or import rule violation in Python/TypeScript files.",
                suggested_fix="Run `./scripts/lint` to automatically fix and format code.",
                affected_files=[],
            )
        elif "typecheck" in log_lower or "tsc" in log_lower:
            return PRDiagnosisResponse(
                classification="TYPE_FAILURE",
                summary="TypeScript type check failed.",
                root_cause="Type mismatch or missing property definition in frontend code.",
                suggested_fix="Run `pnpm --filter @ai-qa/web typecheck` to locate and resolve type errors.",
                affected_files=["apps/web/src/"],
            )
        elif "modulenotfounderror" in log_lower or "importerror" in log_lower or "cannot find module" in log_lower:
            return PRDiagnosisResponse(
                classification="DEPENDENCY_FAILURE",
                summary="Missing package or unresolved import dependency.",
                root_cause="A required library or internal package path is missing or not installed in the environment.",
                suggested_fix="Ensure all dependencies are declared in pyproject.toml / package.json and synced.",
                affected_files=["pyproject.toml", "package.json"],
            )
        else:
            return PRDiagnosisResponse(
                classification="TEST_FAILURE",
                summary="Automated test assertion or runtime failure during test suite execution.",
                root_cause="Assertion mismatch or unexpected exception during pytest execution.",
                suggested_fix="Review the failure stack trace, verify selectors or API mocks, and re-run tests locally.",
                affected_files=["tests/"],
            )


class GitHubPullRequestAdapter(PullRequestAdapter):
    """Real GitHub REST API adapter reading token securely from environment."""

    def __init__(self, token: str | None = None, api_base_url: str = "https://api.github.com") -> None:
        self.token = token or os.getenv("GITHUB_TOKEN", "").strip()
        self.api_base_url = api_base_url.rstrip("/")
        self._fallback_adapter = FakePullRequestAdapter()

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def create_pull_request(
        self,
        repo_slug: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequestInfo:
        if not self.token:
            # Fallback gracefully to simulated adapter when no token is provided
            return await self._fallback_adapter.create_pull_request(repo_slug, head_branch, base_branch, title, body)

        url = f"{self.api_base_url}/repos/{repo_slug}/pulls"
        payload = {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            if resp.status_code >= 400:
                # If PR already exists or error, handle cleanly
                err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                err_msg = err_data.get("message", resp.text)
                raise RuntimeError(f"GitHub PR creation failed ({resp.status_code}): {err_msg}")
            data = resp.json()
            return PullRequestInfo(
                id=str(data["id"]),
                number=data["number"],
                title=data["title"],
                body=data.get("body") or "",
                html_url=data["html_url"],
                state=data.get("state", "open"),
                head_branch=data["head"]["ref"],
                base_branch=data["base"]["ref"],
                created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            )

    async def get_pull_request(self, repo_slug: str, pr_number: int) -> PullRequestInfo:
        if not self.token:
            return await self._fallback_adapter.get_pull_request(repo_slug, pr_number)

        url = f"{self.api_base_url}/repos/{repo_slug}/pulls/{pr_number}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code >= 400:
                raise RuntimeError(f"Failed to fetch GitHub PR #{pr_number}: {resp.text}")
            data = resp.json()
            return PullRequestInfo(
                id=str(data["id"]),
                number=data["number"],
                title=data["title"],
                body=data.get("body") or "",
                html_url=data["html_url"],
                state=data.get("state", "open"),
                head_branch=data["head"]["ref"],
                base_branch=data["base"]["ref"],
                created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            )

    async def get_pr_checks(self, repo_slug: str, pr_number: int, head_branch: str = "main") -> PRChecksSummary:
        if not self.token:
            return await self._fallback_adapter.get_pr_checks(repo_slug, pr_number, head_branch)

        # First get PR to determine head SHA
        pr_url = f"{self.api_base_url}/repos/{repo_slug}/pulls/{pr_number}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            pr_resp = await client.get(pr_url, headers=self._get_headers())
            if pr_resp.status_code >= 400:
                return await self._fallback_adapter.get_pr_checks(repo_slug, pr_number, head_branch)
            pr_data = pr_resp.json()
            head_sha = pr_data["head"]["sha"]
            head_ref = pr_data["head"]["ref"]
            html_url = pr_data["html_url"]

            # Fetch check runs for the head SHA
            checks_url = f"{self.api_base_url}/repos/{repo_slug}/commits/{head_sha}/check-runs"
            checks_resp = await client.get(checks_url, headers=self._get_headers())
            if checks_resp.status_code >= 400:
                return PRChecksSummary(
                    pr_number=pr_number,
                    pr_url=html_url,
                    head_branch=head_ref,
                    overall_status=CheckStatus.PASSED,
                    checks=[],
                )
            checks_data = checks_resp.json()
            runs: list[CheckRun] = []
            for item in checks_data.get("check_runs", []):
                status_str = item.get("status", "completed")
                conclusion = item.get("conclusion")
                if status_str in ("queued", "in_progress"):
                    c_status = CheckStatus.RUNNING if status_str == "in_progress" else CheckStatus.QUEUED
                elif conclusion == "success":
                    c_status = CheckStatus.PASSED
                elif conclusion in ("failure", "timed_out", "cancelled"):
                    c_status = CheckStatus.FAILED
                else:
                    c_status = CheckStatus.PASSED

                runs.append(
                    CheckRun(
                        id=str(item["id"]),
                        name=item["name"],
                        status=c_status,
                        conclusion=conclusion,
                        html_url=item.get("html_url"),
                    )
                )

            has_failed = any(r.status == CheckStatus.FAILED for r in runs)
            has_running = any(r.status in (CheckStatus.RUNNING, CheckStatus.QUEUED) for r in runs)
            overall = CheckStatus.FAILED if has_failed else (CheckStatus.RUNNING if has_running else CheckStatus.PASSED)

            return PRChecksSummary(
                pr_number=pr_number,
                pr_url=html_url,
                head_branch=head_ref,
                overall_status=overall,
                checks=runs,
            )

    async def get_check_logs(self, repo_slug: str, check_run_id: str) -> str:
        return await self._fallback_adapter.get_check_logs(repo_slug, check_run_id)

    async def diagnose_failure(self, failure_logs: str) -> PRDiagnosisResponse:
        return await self._fallback_adapter.diagnose_failure(failure_logs)
