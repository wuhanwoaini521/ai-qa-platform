from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from typing import Any, Protocol, runtime_checkable

from project_model.models import (
    JiraBugDraft,
    JiraCreateBugResponse,
    JiraIssue,
)


@runtime_checkable
class RequirementManagementAdapter(Protocol):
    """Adapter interface for Requirement and Issue Management systems (e.g. Jira)."""

    def get_issue(self, issue_key: str) -> JiraIssue | None:
        """Fetch a single issue by key."""
        ...

    def search_issues(self, query: str = "", limit: int = 20) -> list[JiraIssue]:
        """Search issues matching a query/JQL."""
        ...

    def create_bug(self, draft: JiraBugDraft, confirm_publish: bool = False) -> JiraCreateBugResponse:
        """Create a bug ticket from a draft. If confirm_publish is False, performs a dry-run validation."""
        ...


class FakeJiraAdapter:
    """In-memory Jira adapter for testing, development, and offline operation."""

    def __init__(self, initial_issues: list[JiraIssue] | None = None) -> None:
        self.issues: dict[str, JiraIssue] = {}
        self.created_bugs: list[dict[str, Any]] = []
        self._next_bug_id = 501

        defaults = initial_issues or [
            JiraIssue(
                key="PROJ-101",
                summary="User Login via OAuth and Password",
                description="As a registered user, I want to log in using Google OAuth or email/password.",
                acceptance_criteria="1. Valid email/password redirects to dashboard.\n2. Invalid password shows error banner.\n3. Locked accounts are prevented from logging in.",
                status="In Progress",
                priority="High",
                labels=["auth", "security", "core"],
                url="https://jira.example.com/browse/PROJ-101",
            ),
            JiraIssue(
                key="PROJ-102",
                summary="Checkout Shopping Cart with Coupon",
                description="As a shopper, I want to apply discount coupons at checkout.",
                acceptance_criteria="1. Valid coupons apply discount.\n2. Expired coupons show clear error.\n3. Total cannot fall below 0.",
                status="Ready for QA",
                priority="Critical",
                labels=["checkout", "payment"],
                url="https://jira.example.com/browse/PROJ-102",
            ),
            JiraIssue(
                key="PROJ-103",
                summary="Export Test Execution Reports to CSV",
                description="As a QA Lead, I want to export test execution history for audits.",
                acceptance_criteria="1. CSV contains run timestamp, test name, status, duration.\n2. Supports filtering by date range.",
                status="Open",
                priority="Medium",
                labels=["reporting", "export"],
                url="https://jira.example.com/browse/PROJ-103",
            ),
        ]
        for issue in defaults:
            self.issues[issue.key.upper()] = issue

    def get_issue(self, issue_key: str) -> JiraIssue | None:
        return self.issues.get(issue_key.strip().upper())

    def search_issues(self, query: str = "", limit: int = 20) -> list[JiraIssue]:
        q = query.strip().lower()
        results: list[JiraIssue] = []
        for issue in self.issues.values():
            if not q or q in issue.key.lower() or q in issue.summary.lower() or q in issue.description.lower():
                results.append(issue)
            if len(results) >= limit:
                break
        return results

    def create_bug(self, draft: JiraBugDraft, confirm_publish: bool = False) -> JiraCreateBugResponse:
        key = f"{draft.project_key.upper()}-{self._next_bug_id}"
        url = f"https://jira.example.com/browse/{key}"

        if not confirm_publish:
            return JiraCreateBugResponse(
                key=key,
                url=url,
                status="DRY_RUN_VALIDATED",
                published=False,
                message=f"Dry-run passed for draft: '{draft.summary}'. Ready to publish.",
            )

        self._next_bug_id += 1
        created_issue = JiraIssue(
            key=key,
            summary=draft.summary,
            description=draft.description,
            acceptance_criteria=draft.expected_result,
            status="Open",
            priority=draft.priority,
            labels=["automated-qa-defect"],
            url=url,
        )
        self.issues[key] = created_issue
        self.created_bugs.append({"key": key, "draft": draft.model_dump(), "url": url})

        return JiraCreateBugResponse(
            key=key,
            url=url,
            status="CREATED",
            published=True,
            message=f"Successfully created Jira issue {key}",
        )


class JiraAdapter:
    """Production REST API adapter for Atlassian Jira Cloud and Server."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        self.timeout = timeout_seconds

    def _get_headers(self) -> dict[str, str]:
        auth_pair = f"{self.email}:{self.api_token}".encode("utf-8")
        auth_b64 = base64.b64encode(auth_pair).decode("utf-8")
        return {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_issue(self, issue_key: str) -> JiraIssue | None:
        if not self.base_url or not self.api_token:
            return None
        url = f"{self.base_url}/rest/api/3/issue/{urllib.parse.quote(issue_key)}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                fields = data.get("fields", {})
                summary = fields.get("summary", "")
                desc_obj = fields.get("description", "")
                desc_text = str(desc_obj) if isinstance(desc_obj, str) else json.dumps(desc_obj)
                status = fields.get("status", {}).get("name", "Open")
                priority = fields.get("priority", {}).get("name", "Medium")
                labels = fields.get("labels", [])
                return JiraIssue(
                    key=data.get("key", issue_key),
                    summary=summary,
                    description=desc_text,
                    acceptance_criteria="",
                    status=status,
                    priority=priority,
                    labels=labels,
                    url=f"{self.base_url}/browse/{data.get('key', issue_key)}",
                )
        except Exception:
            return None

    def search_issues(self, query: str = "", limit: int = 20) -> list[JiraIssue]:
        if not self.base_url or not self.api_token:
            return []
        jql = f'text ~ "{query}" ORDER BY updated DESC' if query else "ORDER BY updated DESC"
        url = f"{self.base_url}/rest/api/3/search?jql={urllib.parse.quote(jql)}&maxResults={limit}"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                issues = []
                for item in data.get("issues", []):
                    fields = item.get("fields", {})
                    issues.append(
                        JiraIssue(
                            key=item.get("key", ""),
                            summary=fields.get("summary", ""),
                            description=str(fields.get("description", "")),
                            acceptance_criteria="",
                            status=fields.get("status", {}).get("name", "Open"),
                            priority=fields.get("priority", {}).get("name", "Medium"),
                            labels=fields.get("labels", []),
                            url=f"{self.base_url}/browse/{item.get('key', '')}",
                        )
                    )
                return issues
        except Exception:
            return []

    def create_bug(self, draft: JiraBugDraft, confirm_publish: bool = False) -> JiraCreateBugResponse:
        if not confirm_publish:
            return JiraCreateBugResponse(
                key=f"{draft.project_key}-PREVIEW",
                url=f"{self.base_url}/browse/{draft.project_key}-PREVIEW" if self.base_url else "",
                status="DRY_RUN_VALIDATED",
                published=False,
                message=f"Dry-run passed for '{draft.summary}'. Ready to publish to Jira.",
            )

        if not self.base_url or not self.api_token:
            return JiraCreateBugResponse(
                key="",
                url="",
                status="ERROR",
                published=False,
                message="Jira credentials not configured.",
            )

        url = f"{self.base_url}/rest/api/3/issue"
        payload = {
            "fields": {
                "project": {"key": draft.project_key},
                "summary": draft.summary,
                "issuetype": {"name": draft.issue_type},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": draft.description}],
                        }
                    ],
                },
                "priority": {"name": draft.priority},
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._get_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                created_key = data.get("key", "")
                return JiraCreateBugResponse(
                    key=created_key,
                    url=f"{self.base_url}/browse/{created_key}",
                    status="CREATED",
                    published=True,
                    message=f"Created Jira issue {created_key}",
                )
        except Exception as exc:
            return JiraCreateBugResponse(
                key="",
                url="",
                status="ERROR",
                published=False,
                message=f"Jira API call failed: {exc}",
            )
