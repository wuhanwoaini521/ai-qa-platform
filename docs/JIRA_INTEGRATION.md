# Jira Integration Guide

## 1. Overview
The **AI QA Platform** provides bidirectional integration with Atlassian Jira (Cloud & Server / Data Center) to synchronize requirements and automate defect reporting.

```text
    Atlassian Jira
    (User Stories)
          ↓ [Import]
    Platform Requirements
          ↓ [Test Design & Cases]
    Automated Test Runs
          ↓ [Failure Detection & AI Diagnostics]
    Jira Bug Draft (Dry-run Validation)
          ↓ [Confirmed Publish]
    Atlassian Jira
    (Defect / Bug Ticket)
```

---

## 2. Core Capabilities

### 2.1 Requirement & User Story Import
- Search Jira issues via JQL / keyword search (`/api/jira/issues`).
- Import Jira user stories into Platform Requirements (`/api/jira/import`).
- Automatically preserves Jira issue keys, descriptions, acceptance criteria, and direct hyperlinks.

### 2.2 Automated Bug Ticket Drafting & Creation
- When an automated test execution fails, the platform generates a structured bug report containing:
  - **Summary**: `[Defect] Automated Test Failure: <Test Name>`
  - **Environment**: Platform Run ID, execution node ID, and runner type
  - **Classification**: Root-cause category (e.g. `APPLICATION_BUG`, `LOCATOR_CHANGED`)
  - **Reproduction Steps**: Step-by-step sequence leading to failure
  - **Artifacts**: Linked failure screenshots and execution traces
- **Preview-First / Dry-Run Safe**: `confirm_publish=False` by default; users can review and validate draft before pushing live.

### 2.3 Audit Logging
- Every external write or import action is logged to `integration_audits` (`/api/audit/integrations?system=JIRA`).

---

## 3. Configuration
Configure Jira integration via environment variables:

```bash
JIRA_BASE_URL="https://your-domain.atlassian.net"
JIRA_EMAIL="qa-bot@example.com"
JIRA_API_TOKEN="your-jira-api-token"
```

When unconfigured, the platform automatically activates `FakeJiraAdapter` for offline and local development.
