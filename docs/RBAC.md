# Role-Based Access Control (RBAC) Specification

## 1. User Roles

The platform enforces four hierarchical and capability-defined roles:

| Role | Description | Core Capabilities |
|---|---|---|
| **ADMIN** | Platform Superuser & Security Administrator | Full platform control, User management, Team assignment, API Key lifecycle, Security audits, Global settings |
| **QA_LEAD** | QA Lead & Release Gatekeeper | Test authoring, Execution, Jira/TestRail publishing, Release Gate approvals, Team management |
| **QA_ENGINEER** | Test Automation Engineer | Test Case creation, Automation Studio editing, Local/Jenkins test execution |
| **VIEWER** | Stakeholder / Product Manager | Read-only inspection of reports, runs, coverage, and release gates |

---

## 2. Granular Permissions Matrix

| Permission Key | Description | ADMIN | QA_LEAD | QA_ENGINEER | VIEWER |
|---|---|:---:|:---:|:---:|:---:|
| `project:read` | View project metadata, tests, and runs | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `project:write` | Create / edit / delete projects | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `requirement:write`| Create / edit / import Jira requirements | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `test_case:write` | Design and author test cases | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `automation:edit` | Generate & edit test scripts in Monaco | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `run:execute` | Launch test execution suites | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `release:gate` | Evaluate and approve release gates | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `integration:manage`| Configure Jira, TestRail, Jenkins endpoints | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `security:admin` | Manage users, roles, and view audit trail | :white_check_mark: | :x: | :x: | :x: |

---

## 3. Team & Squad Organization

Users can be organized into squads (e.g., *Frontend QA Squad*, *Payments Automation Squad*) with assigned squad roles (`LEAD`, `MEMBER`) for domain test ownership.
