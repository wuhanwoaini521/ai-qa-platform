from __future__ import annotations

from integrations.jira_adapter import FakeJiraAdapter, JiraAdapter, RequirementManagementAdapter
from project_model.models import JiraBugDraft


def test_fake_jira_adapter_implements_protocol():
    adapter = FakeJiraAdapter()
    assert isinstance(adapter, RequirementManagementAdapter)


def test_fake_jira_adapter_search_and_get():
    adapter = FakeJiraAdapter()
    issues = adapter.search_issues("login")
    assert len(issues) >= 1
    assert issues[0].key == "PROJ-101"

    issue = adapter.get_issue("proj-101")
    assert issue is not None
    assert issue.key == "PROJ-101"
    assert "OAuth" in issue.summary

    missing = adapter.get_issue("NONEXISTENT-999")
    assert missing is None


def test_fake_jira_adapter_create_bug_dry_run():
    adapter = FakeJiraAdapter()
    draft = JiraBugDraft(
        summary="[Defect] Login button 500 error",
        project_key="PROJ",
        issue_type="Bug",
        description="Stack trace info...",
        priority="High",
        steps_to_reproduce=["1. Click login", "2. See 500 error"],
        failure_id="fail_1",
        run_id="run_1",
    )

    # Dry-run
    resp = adapter.create_bug(draft, confirm_publish=False)
    assert resp.published is False
    assert resp.status == "DRY_RUN_VALIDATED"
    assert "PROJ-501" in resp.key

    # Confirm publish
    resp_pub = adapter.create_bug(draft, confirm_publish=True)
    assert resp_pub.published is True
    assert resp_pub.status == "CREATED"
    assert resp_pub.key == "PROJ-501"

    created = adapter.get_issue("PROJ-501")
    assert created is not None
    assert created.summary == draft.summary


def test_jira_adapter_dry_run_without_credentials():
    adapter = JiraAdapter(base_url="", email="", api_token="")
    draft = JiraBugDraft(
        summary="[Defect] Offline bug",
        project_key="SEC",
        issue_type="Bug",
        description="details",
        failure_id="f1",
        run_id="r1",
    )
    resp = adapter.create_bug(draft, confirm_publish=False)
    assert resp.published is False
    assert resp.status == "DRY_RUN_VALIDATED"
