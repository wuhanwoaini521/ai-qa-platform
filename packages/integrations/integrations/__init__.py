from __future__ import annotations

from integrations.contracts import (
    FakeGitHubIntegration,
    FakeTestRailIntegration,
    GitHubIntegration,
    IssueReport,
    PRContext,
    TestRailIntegration,
)
from integrations.git_repository import (
    GitRepository,
    GitRepositoryProtocol,
    GitSecurityError,
)
from integrations.github_adapter import (
    FakePullRequestAdapter,
    GitHubPullRequestAdapter,
    PullRequestAdapter,
)
from integrations.jenkins_runner import (
    FakeJenkinsServer,
    JenkinsConfig,
    JenkinsRunnerBackend,
)
from integrations.jira_adapter import (
    FakeJiraAdapter,
    JiraAdapter,
    RequirementManagementAdapter,
)
from integrations.testrail_adapter import (
    FakeTestRailAdapter,
    TestManagementAdapter,
    TestRailAdapter,
)

__all__ = [
    "GitHubIntegration",
    "FakeGitHubIntegration",
    "TestRailIntegration",
    "FakeTestRailIntegration",
    "IssueReport",
    "PRContext",
    "JenkinsConfig",
    "JenkinsRunnerBackend",
    "FakeJenkinsServer",
    "GitRepository",
    "GitRepositoryProtocol",
    "GitSecurityError",
    "PullRequestAdapter",
    "FakePullRequestAdapter",
    "GitHubPullRequestAdapter",
    "RequirementManagementAdapter",
    "FakeJiraAdapter",
    "JiraAdapter",
    "TestManagementAdapter",
    "FakeTestRailAdapter",
    "TestRailAdapter",
]
