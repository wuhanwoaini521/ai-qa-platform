from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class IssueReport(BaseModel):
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)


class PRContext(BaseModel):
    repo_url: str
    branch: str
    title: str
    body: str


@runtime_checkable
class GitHubIntegration(Protocol):
    async def create_pull_request(self, context: PRContext) -> str: ...

    async def create_issue(self, repo: str, issue: IssueReport) -> str: ...


@runtime_checkable
class TestRailIntegration(Protocol):
    async def sync_test_cases(self, suite_id: int, cases: list[dict[str, Any]]) -> int: ...

    async def push_run_results(self, run_id: int, results: list[dict[str, Any]]) -> bool: ...


class FakeGitHubIntegration(GitHubIntegration):
    async def create_pull_request(self, context: PRContext) -> str:
        return "https://github.com/fake-org/fake-repo/pull/123"

    async def create_issue(self, repo: str, issue: IssueReport) -> str:
        return f"https://github.com/{repo}/issues/456"


class FakeTestRailIntegration(TestRailIntegration):
    async def sync_test_cases(self, suite_id: int, cases: list[dict[str, Any]]) -> int:
        return len(cases)

    async def push_run_results(self, run_id: int, results: list[dict[str, Any]]) -> bool:
        return True
