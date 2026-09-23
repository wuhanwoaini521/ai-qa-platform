from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from integrations.git_repository import GitRepository, GitSecurityError
from integrations.github_adapter import (
    FakePullRequestAdapter,
    GitHubPullRequestAdapter,
)
from project_model.models import CheckStatus


@pytest.mark.asyncio
async def test_git_repository_operations():
    repo = GitRepository()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Initialize test repo
        proc = await asyncio.create_subprocess_exec("git", "init", "-b", "main", cwd=str(tmp_path))
        await proc.communicate()

        test_file = tmp_path / "README.md"
        test_file.write_text("# Test Repo\n", encoding="utf-8")

        # Initial commit
        commit_msg = await repo.commit(tmp_path, "Initial commit", "Tester", "test@qa.local")
        assert "Initial commit" in commit_msg or "main" in commit_msg

        # Check current branch
        branch = await repo.get_current_branch(tmp_path)
        assert branch == "main"

        # Create new feature branch
        new_branch = await repo.create_branch(tmp_path, "qa/C101-auth-test")
        assert new_branch == "qa/C101-auth-test"

        cur = await repo.get_current_branch(tmp_path)
        assert cur == "qa/C101-auth-test"

        # List branches
        branches = await repo.get_branches(tmp_path)
        assert len(branches) >= 2
        branch_names = [b.name for b in branches]
        assert "main" in branch_names
        assert "qa/C101-auth-test" in branch_names

        # Switch back to main
        switched = await repo.switch_branch(tmp_path, "main")
        assert switched == "main"
        assert await repo.get_current_branch(tmp_path) == "main"

        # Status & Diff on modification
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")

        status = await repo.get_status(tmp_path)
        assert len(status) > 0

        diff = await repo.get_diff(tmp_path)
        assert len(diff.changed_files) > 0

        # Commit changes
        await repo.commit(tmp_path, "feat: add sample test")
        log = await repo.get_log(tmp_path, limit=5)
        assert len(log) >= 2
        assert any("add sample test" in c.message for c in log)

        # Test simulated push
        push_res = await repo.push(tmp_path, "main")
        assert push_res.success is True


@pytest.mark.asyncio
async def test_git_repository_security_guards():
    repo = GitRepository()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Invalid characters / path traversal in branch name
        with pytest.raises(GitSecurityError):
            await repo.create_branch(tmp_path, "feature/../../malicious")

        with pytest.raises(GitSecurityError):
            await repo.create_branch(tmp_path, "branch; rm -rf /")

        with pytest.raises(GitSecurityError):
            await repo.create_branch(tmp_path, "/leading-slash")


@pytest.mark.asyncio
async def test_fake_pull_request_adapter():
    adapter = FakePullRequestAdapter()

    # Create PR
    pr = await adapter.create_pull_request(
        repo_slug="ai-qa/platform",
        head_branch="qa/C123-cart-flow",
        base_branch="main",
        title="feat: automated cart flow tests",
        body="## PR Body\nCoverage for cart requirement.",
    )
    assert pr.number == 101
    assert "github.com/ai-qa/platform/pull/101" in pr.html_url
    assert pr.checks_summary is not None
    assert pr.checks_summary.overall_status == CheckStatus.PASSED

    # Get PR
    fetched = await adapter.get_pull_request("ai-qa/platform", 101)
    assert fetched.number == 101
    assert fetched.title == "feat: automated cart flow tests"

    # Inject failed check and verify overall status updates to FAILED
    adapter.set_failed_check(
        101,
        "chk-101-unit",
        "AssertionError: assert 'Dashboard' in page.title\n  tests/test_login.py:25",
    )
    checks = await adapter.get_pr_checks("ai-qa/platform", 101, "qa/C123-cart-flow")
    assert checks.overall_status == CheckStatus.FAILED
    failed_check = next(c for c in checks.checks if c.status == CheckStatus.FAILED)
    assert "AssertionError" in failed_check.failure_summary

    # Diagnose failure
    diag = await adapter.diagnose_failure(failed_check.failure_logs or "")
    assert diag.classification == "TEST_FAILURE"
    assert "Assertion mismatch" in diag.root_cause


@pytest.mark.asyncio
async def test_github_pull_request_adapter_fallback():
    # When no token is configured, GitHubPullRequestAdapter transparently falls back to safe mock mode
    adapter = GitHubPullRequestAdapter(token="")
    pr = await adapter.create_pull_request(
        repo_slug="org/repo",
        head_branch="qa/feature",
        base_branch="main",
        title="feat: test suite",
        body="Body",
    )
    assert pr.number >= 100
    assert "github.com/org/repo/pull/" in pr.html_url

    checks = await adapter.get_pr_checks("org/repo", pr.number)
    assert checks.overall_status in (CheckStatus.PASSED, CheckStatus.RUNNING, CheckStatus.FAILED)
